"""Low-level HID protocol for KBM! GAMING TG600/TG700 (JieLi chip, VID 0x4A4C).

Reverse engineered from the vendor Windows software (witmodSdk.dll + main exe):

* Vendor interface: usage page 0xFF1B, usage 0x91 (USB interface 2), report ID 1,
  63-byte input/output reports.
* Packet (64 bytes incl. report ID):
    [0]  report id = 0x01
    [1]  wire opcode (the app uses an enum that the SDK maps to the opcode)
    [2]  sub command / 0x01 = query / layer or macro slot
    [3]  0x00
    [4]  packet index (multi-packet transfers)
    [5]  payload length
    [6:] payload
    [62:64] low 16 bits of a millisecond timestamp (big endian, nonce)
"""
import glob
import os
import select
import time

VID = 0x4A4C
PIDS = (0xE987, 0xE988, 0xE989)

# app enum -> wire opcode, from the jump table in CWitmodHid_HidWriteBuff
_ENUM_TO_OPCODE = list(range(0x01, 0x1D)) + list(range(0x40, 0x4A)) + list(range(0x1E, 0x25))


def opcode(enum_value):
    return _ENUM_TO_OPCODE[enum_value]


# App enums (names come from the log strings next to each packet builder)
CMD_HANDSHAKE = 0x00
CMD_KEYBOARD_LED = 0x06         # Write/Inquire keyboard Led
CMD_CUSTOM_LED = 0x08           # Write custom-Led (per-key colours)
CMD_LIGHT_MODE_LIST = 0x09      # Inquire [Light Mode]
CMD_SETTINGS = 0x13             # [2]=0 reset, 1 set sleep, 2 query sleep
CMD_DEVICE_SN = 0x14
CMD_KEYMAP = 0x17               # Write keyboard Onboard-data (key bindings)
CMD_MACRO = 0x18                # Write Macro-data

MATRIX_ROWS = 6
MATRIX_COLS = 22
KEYS_PER_PACKET = 14
MACRO_SLOTS = 10
MACRO_BUFFER = 0xF8             # 248 bytes = 62 events of 4 bytes
MAX_MACRO_EVENTS = MACRO_BUFFER // 4

# Key binding entry types (first byte of each 4-byte entry)
BIND_KEY = 0x00                 # [0, hid_usage, 0, 0]
BIND_FN = 0x01                  # Fn key
BIND_MACRO = 0x10               # [0x10, macro_slot, 0, 0]
FN_CODE = -10                   # "Dec" value used by the vendor key tables for Fn

# Macro event flags (second byte of each 4-byte event)
EV_DOWN = 0x10
EV_MOUSE = 0x01
MOUSE_LEFT, MOUSE_RIGHT, MOUSE_MIDDLE = 1, 2, 4

# Light modes in the order the keyboard reports them (and the vendor UI names them)
MODE_NAMES = {
    0x02: "Estático",
    0x01: "Respiração",
    0x03: "Cintilar",
    0x09: "Ondulação automática",
    0x04: "Estrias",
    0x00: "Aurora",
    0x0E: "Ondulação",
    0x0F: "Reativo",
    0x06: "Fogos de artifício",
    0x07: "Resposta rápida",
    0x0B: "Ritmo musical",
    0x0C: "Personalizado",
    0x10: "Respiração 2",
    0x08: "Desligado",
}


def find_hidraw():
    """Return the /dev/hidrawN path of the vendor interface (usage page 0xFF1B)."""
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(os.path.join(node, "device", "uevent")) as f:
                uevent = f.read()
            with open(os.path.join(node, "device", "report_descriptor"), "rb") as f:
                desc = f.read()
        except OSError:
            continue
        hid_id = next((l.split("=", 1)[1] for l in uevent.splitlines() if l.startswith("HID_ID=")), "")
        parts = hid_id.split(":")
        if len(parts) != 3:
            continue
        vid, pid = int(parts[1], 16), int(parts[2], 16)
        if vid == VID and pid in PIDS and desc.startswith(b"\x06\x1b\xff"):
            return "/dev/" + os.path.basename(node)
    return None


class LedState:
    """Payload of CMD_KEYBOARD_LED (14 bytes)."""

    def __init__(self, mode=0x02, brightness=4, speed=2, color=(255, 0, 0),
                 background=(0, 0, 0), direction=0, color_type=0, update=0, extra=b"\0"):
        self.mode = mode
        self.brightness = brightness    # 0..4 on the wire
        self.speed = speed              # 0..4 on the wire
        self.color = tuple(color)
        self.background = tuple(background)
        self.direction = direction
        self.color_type = color_type    # ledModeType in the vendor XML
        self.update = update
        self.extra = extra

    @classmethod
    def from_payload(cls, p):
        return cls(p[0], p[1], p[2], tuple(p[3:6]), tuple(p[6:9]), p[9], p[10], p[11], bytes(p[12:14]))

    def to_payload(self):
        return bytes([self.mode, self.brightness, self.speed, *self.color, *self.background,
                      self.direction, self.color_type, self.update]) + self.extra[:2].ljust(2, b"\0")

    def __repr__(self):
        return f"LedState({self.to_payload().hex()})"


class Device:
    def __init__(self, path=None):
        self.path = path or find_hidraw()
        if not self.path:
            raise FileNotFoundError("Teclado KBM TG600/TG700 não encontrado")
        self.fd = os.open(self.path, os.O_RDWR)

    def close(self):
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @staticmethod
    def build(cmd_enum, payload=b"", sub=0, index=0):
        buf = bytearray(64)
        buf[0] = 0x01
        buf[1] = opcode(cmd_enum)
        buf[2] = sub
        buf[4] = index
        buf[5] = len(payload)
        buf[6:6 + len(payload)] = payload
        ms = int(time.time() * 1000) & 0xFFFF
        buf[62] = ms >> 8
        buf[63] = ms & 0xFF
        return bytes(buf)

    def _drain(self):
        while select.select([self.fd], [], [], 0)[0]:
            os.read(self.fd, 64)

    def send(self, packet, timeout=0.5):
        self._drain()
        os.write(self.fd, packet)
        if select.select([self.fd], [], [], timeout)[0]:
            return os.read(self.fd, 64)
        return None

    def command(self, cmd_enum, payload=b"", sub=0, index=0, timeout=0.5):
        return self.send(self.build(cmd_enum, payload, sub, index), timeout)

    def query(self, cmd_enum):
        r = self.command(cmd_enum, sub=1)
        if not r or r[1] != opcode(cmd_enum):
            raise IOError("Sem resposta do teclado")
        return r[6:6 + r[5]]

    # ---- info -------------------------------------------------------------
    def serial(self):
        return self.query(CMD_DEVICE_SN).rstrip(b"\0").decode("ascii", "replace")

    def supported_modes(self):
        """Mode ids reported by the firmware, plus max brightness / max speed."""
        data = self.query(CMD_LIGHT_MODE_LIST)
        end = data.index(0xA5) if 0xA5 in data else len(data)
        modes = list(data[:end])
        tail = data[end + 2:end + 4]
        max_bright, max_speed = (tail[0], tail[1]) if len(tail) == 2 else (4, 4)
        return modes, max_bright, max_speed

    # ---- lighting ---------------------------------------------------------
    def get_led(self):
        return LedState.from_payload(self.query(CMD_KEYBOARD_LED))

    def set_led(self, state):
        self.command(CMD_KEYBOARD_LED, state.to_payload())

    # ---- macros -----------------------------------------------------------
    def write_macro(self, slot, events, repeat_mode=1, repeat_count=1):
        """events: list of (code, down, is_mouse, delay_ms). Uploads into macro slot 0..9."""
        if not 0 <= slot < MACRO_SLOTS:
            raise ValueError("slot inválido")
        if len(events) > MAX_MACRO_EVENTS:
            raise ValueError(f"no máximo {MAX_MACRO_EVENTS} eventos por macro")
        data = bytearray()
        for code, down, is_mouse, delay in events:
            delay = max(0, min(int(delay), 0xFFFF))
            data += bytes([code & 0xFF, (EV_DOWN if down else 0) | (EV_MOUSE if is_mouse else 0),
                           delay >> 8, delay & 0xFF])
        self._write_macro_buffer(slot, bytes(data), len(events), repeat_mode, repeat_count)

    def clear_macro(self, slot):
        self._write_macro_buffer(slot, b"", 0, 1, 1, header=False)

    def _write_macro_buffer(self, slot, data, n_events, repeat_mode, repeat_count, header=True):
        data = data.ljust(MACRO_BUFFER, b"\0")
        for pkt in range(5):
            if pkt == 0:
                head = bytes([0, max(repeat_mode - 1, 0), 0, n_events * 4, 0, repeat_count & 0xFF, 0, 0])
                if not header:
                    head = bytes(8)
                payload = head + data[:50]
            elif pkt < 4:
                start = 50 + (pkt - 1) * 58
                payload = data[start:start + 58]
            else:
                payload = data[224:248]
            self.command(CMD_MACRO, payload, sub=slot, index=pkt)
            time.sleep(0.02)

    # ---- key bindings -----------------------------------------------------
    def write_keymap(self, entries, layer=0):
        """entries: list of 132 4-byte entries (row-major 6x22 matrix)."""
        if len(entries) != MATRIX_ROWS * MATRIX_COLS:
            raise ValueError("keymap precisa de 132 entradas")
        for pkt in range(0, len(entries), KEYS_PER_PACKET):
            chunk = b"".join(bytes(e) for e in entries[pkt:pkt + KEYS_PER_PACKET])
            self.command(CMD_KEYMAP, chunk, sub=layer, index=pkt // KEYS_PER_PACKET)
            time.sleep(0.02)

    # ---- misc -------------------------------------------------------------
    def factory_reset(self):
        self.command(CMD_SETTINGS, b"\x01", sub=0)
