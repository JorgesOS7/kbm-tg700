"""Restoring the saved profile after the keyboard loses power (the firmware keeps the key map in RAM)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kbm_tg700 import restore  # noqa: E402
from test_protocol import FakeDevice  # noqa: E402


def profile(bindings=None, macros=None):
    return {"model": "TG700", "macros": macros or [], "bindings": bindings or {}}


class RestoreTest(unittest.TestCase):
    def test_nothing_to_restore_sends_nothing(self):
        d = FakeDevice()
        self.assertFalse(restore.apply_profile(d, profile()))
        self.assertEqual(d.sent, [])

    def test_bindings_write_keymap_only(self):
        d = FakeDevice()
        self.assertTrue(restore.apply_profile(d, profile({"2,16": {"type": "key", "value": 0x21}})))
        self.assertEqual(len(d.sent), 10)
        self.assertTrue(all(p[1] == 0x18 for p in d.sent))
        self.assertEqual(d.sent[0][4], 0)
        # row 2, col 16 -> index 60 -> packet 4, slot 4 in packet
        self.assertEqual(d.sent[4][6 + 4 * 4:6 + 4 * 4 + 4], bytes([0, 0x21, 0, 0]))

    def test_macros_are_written_before_keymap(self):
        d = FakeDevice()
        macros = [{"name": "m", "repeat": 1, "events": [[4, 1, 0, 10], [4, 0, 0, 10]]}]
        restore.apply_profile(d, profile({"0,0": {"type": "macro", "value": 0}}, macros))
        self.assertEqual([p[1] for p in d.sent], [0x19] * 5 + [0x18] * 10)
        self.assertTrue(all(p[2] == 0 for p in d.sent[:5]))

    def test_macros_alone_still_write_them(self):
        d = FakeDevice()
        macros = [{"name": "m", "repeat": 1, "events": [[4, 1, 0, 10]]}]
        self.assertTrue(restore.apply_profile(d, profile(macros=macros)))
        self.assertEqual([p[1] for p in d.sent], [0x19] * 5 + [0x18] * 10)


class WaitForDeviceTest(unittest.TestCase):
    def test_retries_until_device_appears(self):
        calls = []

        def factory():
            calls.append(1)
            if len(calls) < 3:
                raise FileNotFoundError("not yet")
            return "dev"

        slept = []
        self.assertEqual(restore.open_device(factory, timeout=10, sleep=slept.append), "dev")
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(slept), 2)

    def test_permission_error_is_retried_too(self):
        calls = []

        def factory():
            calls.append(1)
            if len(calls) < 2:
                raise PermissionError("acl not applied yet")
            return "dev"

        self.assertEqual(restore.open_device(factory, timeout=10, sleep=lambda s: None), "dev")

    def test_gives_up_after_timeout(self):
        def factory():
            raise FileNotFoundError("never")

        clock = iter(range(0, 100))
        with self.assertRaises(FileNotFoundError):
            restore.open_device(factory, timeout=3, sleep=lambda s: None, now=lambda: next(clock))


if __name__ == "__main__":
    unittest.main()
