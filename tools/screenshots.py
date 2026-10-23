"""Regenerates docs/screenshots/*.png from a demo profile.

Run with the keyboard connected:  python3 tools/screenshots.py
The demo profile lives in a temporary XDG_CONFIG_HOME, and lighting controls are changed on
screen only (nothing is written to the keyboard), so neither the user's profile nor the
keyboard state is touched.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "docs", "screenshots")

cfg = tempfile.mkdtemp(prefix="kbm-shots-")
os.environ["XDG_CONFIG_HOME"] = cfg
sys.path.insert(0, ROOT)

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Graphene", "1.0")
from gi.repository import Adw, GLib, Graphene, Gtk  # noqa: E402


def typed(text_codes, delay=10):
    events = []
    for code in text_codes:
        events += [[code, True, False, delay], [code, False, False, delay]]
    return events


GIT_STATUS = [0x0A, 0x0C, 0x17, 0x2C, 0x16, 0x17, 0x04, 0x17, 0x18, 0x16, 0x28]  # "git status" + Enter
DEMO = {
    "model": "TG700",
    "macros": [
        {"name": "git status", "repeat": 1, "events": typed(GIT_STATUS)},
        {"name": "Clique triplo", "repeat": 1,
         "events": [[1, True, True, 10], [1, False, True, 40]] * 3},
    ],
    "bindings": {},  # filled by fix_demo_bindings()
}

os.makedirs(os.path.join(cfg, "kbm-tg700"))
with open(os.path.join(cfg, "kbm-tg700", "profile.json"), "w") as f:
    json.dump(DEMO, f)

from kbm_tg700 import app as A  # noqa: E402
from kbm_tg700.keymap import LAYOUTS  # noqa: E402


def fix_demo_bindings():
    """Point the demo bindings at real TG700 keys (Home, PgDn, CapsLk)."""
    pos = {k["label"]: f'{k["row"]},{k["col"]}' for k in LAYOUTS["TG700"]}
    DEMO["bindings"] = {pos["Home"]: {"type": "macro", "value": 0},
                        pos["PgDn"]: {"type": "macro", "value": 1},
                        pos["CapsLk"]: {"type": "key", "value": 0xE0}}
    with open(os.path.join(cfg, "kbm-tg700", "profile.json"), "w") as f:
        json.dump(DEMO, f)


fix_demo_bindings()


def save(win, name):
    w, h = win.get_width(), win.get_height()
    paint = Gtk.WidgetPaintable(widget=win)
    snap = Gtk.Snapshot()
    paint.snapshot(snap, w, h)
    tex = win.get_renderer().render_texture(snap.to_node(), Graphene.Rect().init(0, 0, w, h))
    tex.save_to_png(os.path.join(OUT, name))
    print("saved", name, w, "x", h)


class Shots(A.App):
    def do_activate(self):
        A.App.do_activate(self)
        w = self.props.active_window
        w.set_default_size(1100, 760)
        steps = []

        def light():
            w.stack.set_visible_child_name("light")
            if w.mode_ids:
                w._loading = True  # change the controls on screen only, nothing is sent
                w.mode_row.set_selected(w.mode_ids.index(0x0E) if 0x0E in w.mode_ids else 0)
                w.speed.set_value(3)
                w.bright.set_value(4)
                w.dir_row.set_selected(2)
                w.full_color.set_active(True)
                w._loading = False

        def macros():
            w.stack.set_visible_child_name("macros")
            w.macro_list.select_row(w.macro_list.get_row_at_index(0))

        def keys():
            w.stack.set_visible_child_name("keys")

        def tester():
            w.stack.set_visible_child_name("tester")
            for code, down in [(0x0B, True), (0x0B, False), (0x08, True), (0x08, False), (0x0F, True),
                               (0x0F, False), (0x12, True), (0x12, False), (0xE1, True), (0x87, True)]:
                w.tester_event(code, down)

        def about():
            w.stack.set_visible_child_name("light")
            w.on_about()

        for name, fn in [("iluminacao.png", light), ("macros.png", macros), ("teclas.png", keys),
                         ("testar-teclas.png", tester), ("sobre.png", about)]:
            steps.append((name, fn))

        def run(i=[0]):
            if i[0] > 0:
                save(w, steps[i[0] - 1][0])
            if i[0] == len(steps):
                self.quit()
                return False
            steps[i[0]][1]()
            i[0] += 1
            return True

        GLib.timeout_add(1500, run)


os.makedirs(OUT, exist_ok=True)
Adw.init()
Shots().run([])
