"""Interactive helper: shows what the 'ledModeType' byte and direction byte do."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from kbm_tg700.protocol import Device  # noqa: E402

with Device() as d:
    orig = d.get_led()
    st = d.get_led()
    st.mode, st.color, st.brightness, st.speed = 0x04, (0, 0, 255), 4, 2   # Estrias, azul
    notes = {}
    for ct in (0, 1, 4, 7):
        st.color_type = ct
        d.set_led(st)
        notes[f"tipo {ct}"] = input(f"[Estrias, cor AZUL, tipo={ct}] Está azul ou multicolorido? ")
    st.color_type = 0
    for dr in range(0, 8):
        st.direction = dr
        d.set_led(st)
        notes[f"direção {dr}"] = input(f"[direção={dr}] Para onde a luz se move? (esq/dir/cima/baixo/horário/anti/centro/fora) ")
    d.set_led(orig)
print(notes)
