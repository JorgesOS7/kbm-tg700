"""Hardware test: macro slot 0 = types 'kbm', bound to the Home key."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from kbm_tg700.protocol import Device
from kbm_tg700.keymap import LAYOUTS, build_keymap

home = next(k for k in LAYOUTS["TG700"] if k["label"] == "Home")
ev = []
for code in (14, 5, 16):  # k b m
    ev += [(code, True, False, 30), (code, False, False, 30)]
with Device() as d:
    d.write_macro(0, ev)
    d.write_keymap(build_keymap("TG700", {f'{home["row"]},{home["col"]}': {"type": "macro", "value": 0}}))
print("Pronto. Abra um editor de texto e aperte HOME: deve digitar 'kbm'.")
print("Teste também se as outras teclas e combinações Fn continuam normais.")
