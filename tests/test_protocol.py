"""Tests that run without the keyboard: they check the exact bytes the app would send."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kbm_tg700 import protocol  # noqa: E402
from kbm_tg700.hidinput import KeyboardReader  # noqa: E402
from kbm_tg700.keymap import LAYOUTS, build_keymap  # noqa: E402
from kbm_tg700.protocol import Device, LedState  # noqa: E402


class FakeDevice(Device):
    """Device that records packets instead of writing to /dev/hidraw."""

    def __init__(self):
        self.sent = []

    def send(self, packet, timeout=0.5):
        self.sent.append(packet)
        return None


class OpcodeTest(unittest.TestCase):
    def test_enum_to_opcode(self):
        self.assertEqual(protocol.opcode(protocol.CMD_KEYBOARD_LED), 0x07)
        self.assertEqual(protocol.opcode(protocol.CMD_LIGHT_MODE_LIST), 0x0A)
        self.assertEqual(protocol.opcode(protocol.CMD_KEYMAP), 0x18)
        self.assertEqual(protocol.opcode(protocol.CMD_MACRO), 0x19)
        self.assertEqual(protocol.opcode(28), 0x40)
        self.assertEqual(protocol.opcode(38), 0x1E)

    def test_packet_layout(self):
        p = Device.build(protocol.CMD_KEYBOARD_LED, b"\xaa\xbb", sub=1, index=3)
        self.assertEqual(len(p), 64)
        self.assertEqual(p[:8], bytes([0x01, 0x07, 0x01, 0x00, 0x03, 0x02, 0xAA, 0xBB]))
        self.assertEqual(p[8:62], bytes(54))


class LedTest(unittest.TestCase):
    def test_roundtrip(self):
        raw = bytes.fromhex("020304ff00000000000400000000")
        led = LedState.from_payload(raw)
        self.assertEqual((led.mode, led.brightness, led.speed, led.color), (2, 3, 4, (255, 0, 0)))
        self.assertEqual(led.to_payload(), raw)


class MacroTest(unittest.TestCase):
    def test_upload_split(self):
        d = FakeDevice()
        events = [(0x0E, True, False, 30), (0x0E, False, False, 300)]
        d.write_macro(2, events, repeat_count=3)
        self.assertEqual(len(d.sent), 5)
        self.assertEqual([p[4] for p in d.sent], [0, 1, 2, 3, 4])
        self.assertEqual([p[5] for p in d.sent], [58, 58, 58, 58, 24])
        self.assertTrue(all(p[1] == 0x19 and p[2] == 2 for p in d.sent))
        first = d.sent[0]
        self.assertEqual(first[6:14], bytes([0, 0, 0, 8, 0, 3, 0, 0]))
        self.assertEqual(first[14:22], bytes([0x0E, 0x10, 0, 30, 0x0E, 0x00, 0x01, 0x2C]))

    def test_too_many_events(self):
        with self.assertRaises(ValueError):
            FakeDevice().write_macro(0, [(4, True, False, 0)] * (protocol.MAX_MACRO_EVENTS + 1))


class KeymapTest(unittest.TestCase):
    def entry(self, entries, label):
        k = next(k for k in LAYOUTS["TG700"] if k["label"] == label)
        return entries[k["row"] * protocol.MATRIX_COLS + k["col"]], k

    def test_defaults(self):
        entries = build_keymap("TG700", {})
        self.assertEqual(len(entries), 132)
        self.assertEqual(self.entry(entries, "4$")[0], [0, 0x21, 0, 0])
        self.assertEqual(self.entry(entries, "Fn")[0], [1, 0, 0, 0])
        self.assertEqual(self.entry(entries, "/?")[0], [0, 0x87, 0, 0])  # ABNT2 fix

    def test_bindings(self):
        _, home = self.entry(build_keymap("TG700", {}), "Home")
        pos = f'{home["row"]},{home["col"]}'
        self.assertEqual(self.entry(build_keymap("TG700", {pos: {"type": "macro", "value": 3}}), "Home")[0],
                         [0x10, 3, 0, 0])
        self.assertEqual(self.entry(build_keymap("TG700", {pos: {"type": "key", "value": 0x04}}), "Home")[0],
                         [0, 0x04, 0, 0])

    def test_write_packets(self):
        d = FakeDevice()
        d.write_keymap(build_keymap("TG700", {}))
        self.assertEqual(len(d.sent), 10)
        self.assertEqual([p[5] for p in d.sent], [56] * 9 + [24])

    def test_all_layouts(self):
        for model in LAYOUTS:
            self.assertEqual(len(build_keymap(model, {})), 132, model)


class ReaderTest(unittest.TestCase):
    def test_boot_and_nkro(self):
        r = KeyboardReader()
        r.feed("a", True, bytes([0x02, 0, 0x04, 0, 0, 0, 0, 0]))
        self.assertEqual(r.pressed(), {0xE1, 0x04})
        nkro = bytearray(21)
        nkro[0] = 5
        nkro[1 + 0x87 // 8] |= 1 << (0x87 % 8)
        r.feed("b", False, bytes(nkro))
        self.assertEqual(r.pressed(), {0xE1, 0x04, 0x87})
        r.feed("a", True, bytes(8))
        self.assertEqual(r.pressed(), {0x87})


if __name__ == "__main__":
    unittest.main()
