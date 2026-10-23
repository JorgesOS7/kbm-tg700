"""Interactive helper: applies each mode the keyboard reports and records what the user sees."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from kbm_tg700.protocol import CMD_KEYBOARD_LED, CMD_LIGHT_MODE_LIST, Device  # noqa: E402

NAMES = ["Static", "Breath", "Twinkle", "Auto Ripple", "Striation", "Aurora", "Ripple",
         "Reactive", "Fireworks", "Speed Respond", "Musical Rhythm", "Custom", "Off"]

with Device() as d:
    r = d.command(CMD_LIGHT_MODE_LIST, query=True)
    data = r[6:6 + r[5]]
    ids = list(data[:data.index(0xA5)])
    original = d.command(CMD_KEYBOARD_LED, query=True)
    original = original[6:6 + original[5]]
    print("Modos reportados pelo teclado:", [hex(i) for i in ids])
    print("Nomes possíveis:", ", ".join(f"{n}={name}" for n, name in enumerate(NAMES)))
    print("Para cada modo, digite o número do nome (ou descreva o efeito) e Enter.\n")
    result = {}
    for mode in ids:
        payload = bytearray(original)
        payload[0] = mode
        payload[3:6] = bytes([0, 128, 255])
        d.command(CMD_KEYBOARD_LED, bytes(payload))
        ans = input(f"modo 0x{mode:02x}: ").strip()
        result[f"0x{mode:02x}"] = NAMES[int(ans)] if ans.isdigit() and int(ans) < len(NAMES) else ans
    d.command(CMD_KEYBOARD_LED, bytes(original))

out = os.path.join(os.path.dirname(__file__), "modes_observed.json")
with open(out, "w") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
print("\nSalvo em", out)
print(json.dumps(result, indent=2, ensure_ascii=False))
