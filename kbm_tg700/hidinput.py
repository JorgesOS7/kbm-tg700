"""Reads the raw keyboard reports of the TG600/TG700 (for the key tester).

Interface 0 sends 8-byte boot reports (modifiers + 6 keys). Interface 1 uses report IDs:
2 = mouse, 3 = consumer, 4 = system, 5 = NKRO bitmap of usages 0x00..0x9F (20 bytes).
"""
import glob
import os

from .protocol import PIDS, VID


def find_input_nodes():
    """hidraw paths of the keyboard's non-vendor interfaces."""
    nodes = []
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
        if len(parts) != 3 or int(parts[1], 16) != VID or int(parts[2], 16) not in PIDS:
            continue
        if desc.startswith(b"\x06\x1b\xff"):
            continue  # vendor (configuration) interface
        nodes.append(("/dev/" + os.path.basename(node), b"\x85" not in desc))
    return nodes


class KeyboardReader:
    """Tracks the set of pressed HID usages; call feed() for each report read from a node."""

    def __init__(self):
        self.sources = {}

    def pressed(self):
        out = set()
        for s in self.sources.values():
            out |= s
        return out

    def feed(self, path, boot, data):
        if boot and len(data) >= 8:
            keys = {0xE0 + b for b in range(8) if data[0] >> b & 1}
            keys |= {k for k in data[2:8] if k > 3}
            self.sources[(path, "boot")] = keys
        elif not boot and data and data[0] == 5:
            bits = data[1:21]
            self.sources[(path, "nkro")] = {i for i in range(len(bits) * 8) if bits[i // 8] >> (i % 8) & 1}
        elif not boot and data and data[0] == 3 and len(data) >= 3:
            usage = data[1] | data[2] << 8
            self.sources[(path, "consumer")] = {0x10000 | usage} if usage else set()
