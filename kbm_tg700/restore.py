"""Re-send the saved profile to the keyboard.

The firmware keeps macros and key bindings in volatile memory: they are lost whenever the keyboard
loses power (replugging the cable, or a reboot that cuts USB power). This module backs both the
"Gravar no teclado" button and the headless ``kbm-tg700 --restore`` run by a udev-triggered
user service every time the keyboard shows up.
"""
import time

from . import profile as profile_store
from .keymap import build_keymap
from .protocol import MACRO_SLOTS, Device


def apply_profile(device, profile, clear_unused_macros=False):
    """Write macros and key map. Returns False (and sends nothing) if the profile has no customisation."""
    macros = profile.get("macros", [])
    bindings = profile.get("bindings", {})
    if not macros and not bindings:
        return False
    for slot in range(MACRO_SLOTS):
        if slot < len(macros):
            m = macros[slot]
            device.write_macro(slot, [tuple(e) for e in m["events"]], 1, m.get("repeat", 1))
        elif clear_unused_macros:
            device.clear_macro(slot)
    device.write_keymap(build_keymap(profile.get("model", "TG700"), bindings))
    return True


def open_device(factory=Device, timeout=15, sleep=time.sleep, now=time.monotonic):
    """Open the keyboard, waiting for the hidraw node and its udev ACL to show up after hotplug/login."""
    deadline = now() + timeout
    while True:
        try:
            return factory()
        except (FileNotFoundError, PermissionError):
            if now() >= deadline:
                raise
            sleep(0.5)


def main():
    profile = profile_store.load()
    if not profile.get("macros") and not profile.get("bindings"):
        print("Perfil sem macros nem teclas remapeadas: nada a restaurar.")
        return 0
    try:
        device = open_device()
    except OSError as e:
        print(f"Teclado indisponível: {e}")
        return 1
    with device:
        apply_profile(device, profile)
    print("Perfil restaurado no teclado.")
    return 0
