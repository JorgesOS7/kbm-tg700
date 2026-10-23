import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from kbm_tg700.protocol import Device
with Device() as d:
    d.factory_reset()
print("Reset de fábrica enviado.")
