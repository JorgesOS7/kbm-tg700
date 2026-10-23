"""GTK4 / libadwaita control panel for the KBM! GAMING TG600/TG700 keyboard."""
import os
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import __version__, profile as profile_store  # noqa: E402
from .hidcodes import EVDEV_TO_HID, bindable_keys, hid_name  # noqa: E402
from .hidinput import KeyboardReader, find_input_nodes  # noqa: E402
from .keymap import LAYOUTS, build_keymap  # noqa: E402
from .protocol import (MAX_MACRO_EVENTS, MACRO_SLOTS, MODE_NAMES, MOUSE_LEFT, MOUSE_MIDDLE,  # noqa: E402
                       MOUSE_RIGHT, Device)

APP_ID = "br.com.kbm.TG700Control"

# wire values 0..5, identified on hardware with the Striation mode
DIRECTIONS = ["Horário", "Anti-horário", "Esquerda", "Direita", "Baixo", "Cima"]
MOUSE_NAMES = {MOUSE_LEFT: "Clique esquerdo", MOUSE_RIGHT: "Clique direito", MOUSE_MIDDLE: "Clique do meio"}

RELEASE_NOTES = """
<p>Nesta versão:</p>
<ul>
  <li>Janela Sobre com autor, créditos, notas da versão e informações de depuração</li>
  <li>O número de série do teclado não aparece mais na barra superior</li>
  <li>Screenshots do app no README</li>
</ul>
"""


def usb_id(hidraw_path):
    """'4a4c:e987'-style id of a /dev/hidrawN node, read from sysfs."""
    try:
        with open(f"/sys/class/hidraw/{os.path.basename(hidraw_path)}/device/uevent") as f:
            hid_id = next(l.split("=", 1)[1] for l in f.read().splitlines() if l.startswith("HID_ID="))
        _, vid, pid = hid_id.strip().split(":")
        return f"{int(vid, 16):04x}:{int(pid, 16):04x}"
    except (OSError, StopIteration, ValueError):
        return "?"

CSS = b"""
.kbd-key { min-width: 0; min-height: 0; padding: 0; font-size: 0.8em; }
.kbd-key.bound-macro { background: alpha(@accent_bg_color, 0.55); color: @accent_fg_color; }
.kbd-key.bound-key { background: alpha(@warning_bg_color, 0.55); }
.kbd-key.bound-disabled { background: alpha(@error_bg_color, 0.45); }
.kbd-key.selected { outline: 2px solid @accent_color; }
.kbd-key.legend { border-radius: 6px; padding: 4px 8px; }
.recorder { border: 2px dashed alpha(@accent_color, 0.6); border-radius: 12px; padding: 18px; }
.recorder.recording { border-color: @error_color; background: alpha(@error_color, 0.08); }
.test-key { border-radius: 6px; background: alpha(@view_fg_color, 0.08); font-size: 0.8em; }
.test-key.tested { background: alpha(@success_bg_color, 0.7); color: @success_fg_color; }
.test-key.down { background: @accent_bg_color; color: @accent_fg_color; }
.test-last { font-size: 1.6em; font-weight: bold; }
"""


def event_label(ev):
    code, down, mouse, delay = ev
    name = MOUSE_NAMES.get(code, f"Botão {code}") if mouse else hid_name(code)
    return f"{'↓' if down else '↑'} {name}", f"espera {delay} ms"


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="KBM TG700", default_width=1000, default_height=720)
        self.device = None
        self.profile = profile_store.load()
        self.led = None
        self._led_timer = 0
        self._loading = False

        self.toasts = Adw.ToastOverlay()
        self.stack = Adw.ViewStack()
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)

        menu = Gio.Menu()
        menu.append("Reconectar teclado", "win.reconnect")
        menu.append("Restaurar padrão de fábrica", "win.factory-reset")
        menu.append("Sobre", "win.about")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu))
        self.status_label = Gtk.Label(css_classes=["dim-label"])
        header.pack_start(self.status_label)

        for name, cb in (("reconnect", self.on_reconnect), ("factory-reset", self.on_factory_reset),
                         ("about", self.on_about)):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            self.add_action(act)

        toolbar.add_top_bar(header)
        bottom = Adw.ViewSwitcherBar(stack=self.stack)
        toolbar.add_bottom_bar(bottom)
        self.toasts.set_child(self.stack)
        toolbar.set_content(self.toasts)
        self.set_content(toolbar)

        self.stack.add_titled_with_icon(self.build_light_page(), "light", "Iluminação", "weather-clear-symbolic")
        self.stack.add_titled_with_icon(self.build_macro_page(), "macros", "Macros", "media-record-symbolic")
        self.stack.add_titled_with_icon(self.build_keys_page(), "keys", "Teclas", "input-keyboard-symbolic")
        self.stack.add_titled_with_icon(self.build_tester_page(), "tester", "Testar teclas",
                                        "emblem-ok-symbolic")

        self.connect_device()

    # ------------------------------------------------------------------ device
    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=3))

    def connect_device(self):
        if self.device:
            try:
                self.device.close()
            except OSError:
                pass
            self.device = None
        try:
            self.device = Device()
            sn = self.device.serial()
            modes, max_b, max_s = self.device.supported_modes()
            self.led = self.device.get_led()
        except PermissionError:
            self.device = None
            self.set_connected(False, "Sem permissão (regra udev não instalada?)")
            return
        except (OSError, ValueError) as e:
            self.device = None
            self.set_connected(False, str(e) or "Teclado não encontrado")
            return
        self.device_info = {"path": self.device.path, "usb_id": usb_id(self.device.path), "serial": sn,
                            "modes": " ".join(f"{m:02x}" for m in modes), "max": (max_b, max_s)}
        # the serial stays out of the header so screenshots and screen shares don't expose it
        self.set_connected(True, f"Conectado · {self.model}")
        self.load_modes(modes, max_b, max_s)

    def set_connected(self, ok, text):
        self.status_label.set_label(("● " if ok else "○ ") + text)
        self.light_page.set_sensitive(ok)
        self.apply_macros_btn.set_sensitive(ok)
        self.apply_keys_btn.set_sensitive(ok)
        if not ok:
            self.toast(text)

    def guarded(self, fn, *args, ok_msg=None):
        if not self.device:
            self.toast("Teclado desconectado")
            return False
        try:
            fn(*args)
        except OSError as e:
            self.set_connected(False, f"Erro de comunicação: {e}")
            return False
        if ok_msg:
            self.toast(ok_msg)
        return True

    def on_reconnect(self, *_):
        self.connect_device()

    def on_factory_reset(self, *_):
        dlg = Adw.MessageDialog(transient_for=self, heading="Restaurar padrão de fábrica?",
                                body="Iluminação, macros e teclas remapeadas no teclado serão apagadas.")
        dlg.add_response("cancel", "Cancelar")
        dlg.add_response("reset", "Restaurar")
        dlg.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)

        def done(d, resp):
            if resp == "reset" and self.guarded(self.device.factory_reset, ok_msg="Padrão de fábrica restaurado"):
                self.profile["bindings"] = {}
                profile_store.save(self.profile)
                self.refresh_keys()
                GLib.timeout_add(800, lambda: (self.connect_device(), False)[1])
        dlg.connect("response", done)
        dlg.present()

    def debug_info(self):
        lines = [f"KBM TG700 Control {__version__}",
                 f"Python {sys.version.split()[0]}",
                 f"GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}",
                 f"libadwaita {Adw.get_major_version()}.{Adw.get_minor_version()}.{Adw.get_micro_version()}",
                 f"Kernel {os.uname().release}",
                 f"Modelo selecionado: {self.model}"]
        info = getattr(self, "device_info", None)
        if self.device and info:
            lines += [f"Teclado: conectado em {info['path']} (USB {info['usb_id']})",
                      f"Modos informados pelo firmware: {info['modes']}",
                      f"Brilho/velocidade máximos: {info['max'][0]}/{info['max'][1]}",
                      f"Estado do LED: {self.led.to_payload().hex() if self.led else '?'}"]
        else:
            lines.append("Teclado: não conectado")
        lines.append(f"Macros no perfil: {len(self.profile['macros'])}, "
                     f"teclas remapeadas: {len(self.profile['bindings'])}")
        return "\n".join(lines)

    def on_about(self, *_):
        props = dict(
            application_name="KBM TG700 Control", version=__version__, application_icon=APP_ID,
            developer_name="José Jorge",
            developers=["José Jorge https://github.com/JorgesOS7"],
            copyright="© 2026 José Jorge",
            license_type=Gtk.License.MIT_X11,
            website="https://github.com/JorgesOS7/kbm-tg700",
            issue_url="https://github.com/JorgesOS7/kbm-tg700/issues",
            comments="Controle de iluminação RGB, macros e teclas para os teclados KBM! GAMING "
                     "TG600/TG700 no Linux. Tudo é gravado na memória do teclado e funciona em "
                     "qualquer computador.",
            release_notes_version=__version__,
            release_notes=RELEASE_NOTES,
            debug_info=self.debug_info(),
            debug_info_filename="kbm-tg700-debug.txt",
        )
        about_cls = getattr(Adw, "AboutDialog", None)  # libadwaita >= 1.5
        about = about_cls(**props) if about_cls else Adw.AboutWindow(transient_for=self, **props)
        about.add_link("Documentação do protocolo",
                       "https://github.com/JorgesOS7/kbm-tg700/blob/main/docs/PROTOCOL.md")
        about.add_link("Como contribuir", "https://github.com/JorgesOS7/kbm-tg700/blob/main/CONTRIBUTING.md")
        about.add_acknowledgement_section("Feito com", [
            "GTK https://gtk.org", "libadwaita https://gnome.pages.gitlab.gnome.org/libadwaita/",
            "PyGObject https://pygobject.gnome.org",
            "Claude Code (engenharia reversa assistida por IA) https://claude.com/claude-code"])
        about.add_legal_section(
            "Marcas", None, Gtk.License.CUSTOM,
            "Projeto independente e não oficial, sem afiliação com a KaBuM! ou com a fabricante do "
            "teclado. KBM! GAMING, KaBuM!, TG600 e TG700 são marcas de seus respectivos donos e "
            "aparecem apenas para indicar compatibilidade.")
        if about_cls:
            about.present(self)
        else:
            about.present()

    # ------------------------------------------------------------------ lighting
    def build_light_page(self):
        page = Adw.PreferencesPage()
        self.light_page = page

        g = Adw.PreferencesGroup(title="Efeito")
        self.mode_model = Gtk.StringList()
        self.mode_ids = []
        self.mode_row = Adw.ComboRow(title="Modo de iluminação", model=self.mode_model)
        self.mode_row.connect("notify::selected", self.on_led_changed)
        g.add(self.mode_row)

        self.bright_row, self.bright = self._scale_row("Brilho", 0, 4)
        self.speed_row, self.speed = self._scale_row("Velocidade", 0, 4)
        g.add(self.bright_row)
        g.add(self.speed_row)

        self.dir_row = Adw.ComboRow(title="Direção", model=Gtk.StringList.new(DIRECTIONS))
        self.dir_row.connect("notify::selected", self.on_led_changed)
        g.add(self.dir_row)
        page.add(g)

        c = Adw.PreferencesGroup(title="Cor")
        self.full_color = Adw.SwitchRow(title="Cores do arco-íris", subtitle="Ignora a cor escolhida abaixo")
        self.full_color.connect("notify::active", self.on_led_changed)
        c.add(self.full_color)

        self.color_btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER)
        self.color_btn.connect("notify::rgba", self.on_led_changed)
        row = Adw.ActionRow(title="Cor principal")
        row.add_suffix(self.color_btn)
        c.add(row)

        presets = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=12,
                              min_children_per_line=6, margin_top=6)
        for hexc in ("#ff0000", "#ff5500", "#ffaa00", "#ffff00", "#55ff55", "#00ff00", "#00ffaa",
                     "#00ffff", "#0055ff", "#0000ff", "#aa00ff", "#ff00ff", "#ffffff"):
            b = Gtk.Button(width_request=32, height_request=32, tooltip_text=hexc)
            prov = Gtk.CssProvider()
            prov.load_from_data(f"button {{ background: {hexc}; border-radius: 16px; }}".encode())
            b.get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            b.connect("clicked", self.on_preset, hexc)
            presets.append(b)
        c.add(presets)
        page.add(c)
        return page

    def _scale_row(self, title, lo, hi):
        row = Adw.ActionRow(title=title)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 1)
        scale.set_hexpand(True)
        scale.set_draw_value(False)
        scale.set_size_request(260, -1)
        for v in range(lo, hi + 1):
            scale.add_mark(v, Gtk.PositionType.BOTTOM, str(v + 1))
        scale.connect("value-changed", self.on_led_changed)
        row.add_suffix(scale)
        return row, scale

    def load_modes(self, modes, max_b, max_s):
        self._loading = True
        self.mode_ids = modes
        self.mode_model.splice(0, self.mode_model.get_n_items(),
                               [MODE_NAMES.get(m, f"Modo 0x{m:02x}") for m in modes])
        led = self.led
        if led.mode in modes:
            self.mode_row.set_selected(modes.index(led.mode))
        self.bright.set_range(0, max_b)
        self.speed.set_range(0, max_s)
        self.bright.set_value(led.brightness)
        self.speed.set_value(led.speed)
        self.dir_row.set_selected(min(led.direction, len(DIRECTIONS) - 1))
        self.full_color.set_active(bool(led.color_type & 1))
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = (*(c / 255 for c in led.color), 1.0)
        self.color_btn.set_rgba(rgba)
        self._loading = False

    def on_preset(self, _btn, hexc):
        rgba = Gdk.RGBA()
        rgba.parse(hexc)
        self.full_color.set_active(False)
        self.color_btn.set_rgba(rgba)

    def on_led_changed(self, *_):
        if self._loading or not self.led:
            return
        if self._led_timer:
            GLib.source_remove(self._led_timer)
        self._led_timer = GLib.timeout_add(120, self.push_led)

    def push_led(self):
        self._led_timer = 0
        led = self.led
        sel = self.mode_row.get_selected()
        if sel < len(self.mode_ids):
            led.mode = self.mode_ids[sel]
        led.brightness = int(self.bright.get_value())
        led.speed = int(self.speed.get_value())
        led.direction = self.dir_row.get_selected()
        rgba = self.color_btn.get_rgba()
        led.color = (round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255))
        # bit 0 of ledModeType selects "Full color" (verified on hardware)
        led.color_type = (led.color_type | 1) if self.full_color.get_active() else (led.color_type & ~1)
        self.guarded(self.device.set_led, led)
        return False

    # ------------------------------------------------------------------ macros
    def build_macro_page(self):
        split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, position=280, shrink_start_child=False)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.macro_list = Gtk.ListBox(css_classes=["navigation-sidebar"], vexpand=True)
        self.macro_list.connect("row-selected", self.on_macro_selected)
        left.append(Gtk.ScrolledWindow(child=self.macro_list, vexpand=True))
        btns = Gtk.Box(spacing=6, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Nova macro")
        add.connect("clicked", self.on_macro_add)
        rem = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Excluir macro")
        rem.connect("clicked", self.on_macro_remove)
        btns.append(add)
        btns.append(rem)
        self.apply_macros_btn = Gtk.Button(label="Gravar no teclado", css_classes=["suggested-action"],
                                           hexpand=True)
        self.apply_macros_btn.connect("clicked", self.on_apply_all)
        btns.append(self.apply_macros_btn)
        left.append(btns)
        split.set_start_child(left)

        self.macro_editor = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=18,
                                    margin_bottom=18, margin_start=18, margin_end=18)
        self.macro_empty = Adw.StatusPage(icon_name="media-playlist-repeat-symbolic", title="Nenhuma macro",
                                          description="Crie uma macro com o botão + e grave as teclas.")
        self.macro_stack = Gtk.Stack()
        self.macro_stack.add_named(self.macro_empty, "empty")
        self.macro_stack.add_named(Gtk.ScrolledWindow(child=Adw.Clamp(child=self.macro_editor, maximum_size=720),
                                                      hscrollbar_policy=Gtk.PolicyType.NEVER), "edit")

        prefs = Adw.PreferencesGroup()
        self.macro_name = Adw.EntryRow(title="Nome")
        self.macro_name.connect("changed", self.on_macro_name)
        prefs.add(self.macro_name)
        self.macro_repeat = Adw.SpinRow.new_with_range(1, 255, 1)
        self.macro_repeat.set_title("Repetições")
        self.macro_repeat.connect("notify::value", self.on_macro_repeat)
        prefs.add(self.macro_repeat)
        self.fixed_delay = Adw.SpinRow.new_with_range(0, 5000, 5)
        self.fixed_delay.set_title("Atraso fixo ao gravar (ms)")
        self.fixed_delay.set_subtitle("0 = usar o tempo real entre as teclas")
        prefs.add(self.fixed_delay)
        self.macro_editor.append(prefs)

        self.recorder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["recorder"],
                                focusable=True)
        self.rec_label = Gtk.Label(label="Clique em “Gravar” e digite a sequência de teclas aqui",
                                   wrap=True, css_classes=["title-4"])
        self.recorder.append(self.rec_label)
        rb = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        self.rec_btn = Gtk.ToggleButton(label="● Gravar", css_classes=["destructive-action", "pill"])
        self.rec_btn.connect("toggled", self.on_record_toggled)
        rb.append(self.rec_btn)
        clear = Gtk.Button(label="Limpar", css_classes=["pill"])
        clear.connect("clicked", self.on_macro_clear_events)
        rb.append(clear)
        self.recorder.append(rb)
        mouse = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        mouse.append(Gtk.Label(label="Adicionar:", css_classes=["dim-label"]))
        for code in (MOUSE_LEFT, MOUSE_RIGHT, MOUSE_MIDDLE):
            mb = Gtk.Button(label=MOUSE_NAMES[code], css_classes=["pill", "flat"])
            mb.connect("clicked", self.on_add_mouse, code)
            mouse.append(mb)
        self.recorder.append(mouse)
        keyctl = Gtk.EventControllerKey()
        keyctl.connect("key-pressed", self.on_rec_key, True)
        keyctl.connect("key-released", self.on_rec_key, False)
        self.recorder.add_controller(keyctl)
        self.macro_editor.append(self.recorder)

        self.events_group = Adw.PreferencesGroup(title="Eventos")
        self.events_box = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
        self.events_group.add(self.events_box)
        self.macro_editor.append(self.events_group)

        split.set_end_child(self.macro_stack)
        self._rec_last = None
        self.refresh_macro_list()
        return split

    def current_macro(self):
        row = self.macro_list.get_selected_row()
        if row is None:
            return None, None
        i = row.get_index()
        return i, self.profile["macros"][i]

    def refresh_macro_list(self, select=None):
        self.macro_list.remove_all()
        for i, m in enumerate(self.profile["macros"]):
            self.macro_list.append(Gtk.Label(label=f"M{i + 1} · {m['name']}", xalign=0,
                                             margin_top=8, margin_bottom=8, margin_start=8))
        if self.profile["macros"]:
            r = self.macro_list.get_row_at_index(select if select is not None else 0)
            self.macro_list.select_row(r)
        else:
            self.macro_stack.set_visible_child_name("empty")

    def on_macro_add(self, *_):
        if len(self.profile["macros"]) >= MACRO_SLOTS:
            self.toast(f"O teclado suporta no máximo {MACRO_SLOTS} macros")
            return
        self.profile["macros"].append({"name": f"Macro {len(self.profile['macros']) + 1}", "repeat": 1,
                                       "events": []})
        self.save_profile()
        self.refresh_macro_list(len(self.profile["macros"]) - 1)

    def on_macro_remove(self, *_):
        i, m = self.current_macro()
        if m is None:
            return
        del self.profile["macros"][i]
        # drop bindings to the removed macro and shift later slots
        for k, b in list(self.profile["bindings"].items()):
            if b["type"] == "macro":
                if b["value"] == i:
                    del self.profile["bindings"][k]
                elif b["value"] > i:
                    b["value"] -= 1
        self.save_profile()
        self.refresh_macro_list()
        self.refresh_keys()

    def on_macro_selected(self, _lb, row):
        if row is None:
            return
        _, m = self.current_macro()
        self._loading = True
        self.macro_name.set_text(m["name"])
        self.macro_repeat.set_value(m.get("repeat", 1))
        self._loading = False
        self.refresh_events()
        self.macro_stack.set_visible_child_name("edit")

    def on_macro_name(self, entry):
        i, m = self.current_macro()
        if m is None or self._loading:
            return
        m["name"] = entry.get_text()
        self.save_profile()
        lbl = self.macro_list.get_row_at_index(i).get_child()
        lbl.set_label(f"M{i + 1} · {m['name']}")

    def on_macro_repeat(self, *_):
        _, m = self.current_macro()
        if m is not None and not self._loading:
            m["repeat"] = int(self.macro_repeat.get_value())
            self.save_profile()

    def refresh_events(self):
        _, m = self.current_macro()
        self.events_box.remove_all()
        if m is None:
            return
        for idx, ev in enumerate(m["events"]):
            title, sub = event_label(ev)
            row = Adw.ActionRow(title=title)
            spin = Gtk.SpinButton.new_with_range(0, 65535, 5)
            spin.set_value(ev[3])
            spin.set_valign(Gtk.Align.CENTER)
            spin.connect("value-changed", self.on_event_delay, idx)
            row.add_suffix(Gtk.Label(label="espera (ms)", css_classes=["dim-label"]))
            row.add_suffix(spin)
            rm = Gtk.Button(icon_name="list-remove-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
            rm.connect("clicked", self.on_event_remove, idx)
            row.add_suffix(rm)
            self.events_box.append(row)
        self.events_group.set_description(f"{len(m['events'])}/{MAX_MACRO_EVENTS} eventos")

    def on_event_delay(self, spin, idx):
        _, m = self.current_macro()
        m["events"][idx][3] = int(spin.get_value())
        self.save_profile()

    def on_event_remove(self, _b, idx):
        _, m = self.current_macro()
        del m["events"][idx]
        self.save_profile()
        self.refresh_events()

    def on_macro_clear_events(self, *_):
        _, m = self.current_macro()
        if m is not None:
            m["events"] = []
            self.save_profile()
            self.refresh_events()

    def on_record_toggled(self, btn):
        if btn.get_active():
            self._rec_last = None
            self._rec_down = set()
            self.recorder.add_css_class("recording")
            self.rec_label.set_label("Gravando… digite as teclas (clique em Parar para terminar)")
            self.recorder.grab_focus()
            btn.set_label("■ Parar")
        else:
            self.recorder.remove_css_class("recording")
            self.rec_label.set_label("Clique em “Gravar” e digite a sequência de teclas aqui")
            btn.set_label("● Gravar")

    def _append_event(self, code, down, mouse):
        _, m = self.current_macro()
        if m is None:
            return
        if len(m["events"]) >= MAX_MACRO_EVENTS:
            self.toast(f"Limite de {MAX_MACRO_EVENTS} eventos atingido")
            self.rec_btn.set_active(False)
            return
        now = time.monotonic()
        fixed = int(self.fixed_delay.get_value())
        if m["events"]:
            delay = fixed if fixed or self._rec_last is None else int((now - self._rec_last) * 1000)
            m["events"][-1][3] = min(delay, 65535)
        m["events"].append([code, down, mouse, fixed or 10])
        self._rec_last = now
        self.save_profile()
        self.refresh_events()

    def on_rec_key(self, _ctl, keyval, keycode, _state, down):
        if not self.rec_btn.get_active():
            return False
        hid = EVDEV_TO_HID.get(keycode - 8)
        if hid is None:
            self.toast(f"Tecla não suportada (código {keycode})")
            return True
        if down and hid in self._rec_down:
            return True  # autorepeat
        (self._rec_down.add if down else self._rec_down.discard)(hid)
        self._append_event(hid, down, False)
        return True

    def on_add_mouse(self, _b, code):
        self._rec_last = None
        self._append_event(code, True, True)
        self._append_event(code, False, True)

    # ------------------------------------------------------------------ keys
    def build_keys_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=18, margin_bottom=18,
                      margin_start=18, margin_end=18)
        top = Gtk.Box(spacing=12)
        top.append(Gtk.Label(label="Clique numa tecla para remapear ou atribuir uma macro.",
                             xalign=0, hexpand=True, wrap=True))
        self.model_dd = Gtk.DropDown.new_from_strings(list(LAYOUTS))
        self.model_dd.set_selected(list(LAYOUTS).index(self.profile.get("model", "TG700")))
        self.model_dd.connect("notify::selected", self.on_model_changed)
        top.append(Gtk.Label(label="Modelo:"))
        top.append(self.model_dd)
        box.append(top)

        self.kbd = Gtk.Fixed(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, hexpand=True, vexpand=True)
        frame = Gtk.Frame(child=self.kbd, css_classes=["card"])
        box.append(Gtk.ScrolledWindow(child=frame, vexpand=True, hscrollbar_policy=Gtk.PolicyType.AUTOMATIC))

        legend = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        for css, txt in (("bound-key", "Remapeada"), ("bound-macro", "Macro"), ("bound-disabled", "Desativada")):
            legend.append(Gtk.Label(label=txt, css_classes=["kbd-key", "legend", css], width_request=100))
        box.append(legend)

        bottom = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        clear = Gtk.Button(label="Limpar remapeamentos")
        clear.connect("clicked", self.on_clear_bindings)
        bottom.append(clear)
        self.apply_keys_btn = Gtk.Button(label="Gravar no teclado", css_classes=["suggested-action"])
        self.apply_keys_btn.connect("clicked", self.on_apply_all)
        bottom.append(self.apply_keys_btn)
        box.append(bottom)
        self.key_buttons = {}
        self.refresh_keys()
        return box

    @property
    def model(self):
        return self.profile.get("model", "TG700")

    def on_model_changed(self, dd, *_):
        self.profile["model"] = list(LAYOUTS)[dd.get_selected()]
        self.profile["bindings"] = {}
        self.save_profile()
        self.refresh_keys()
        self.refresh_tester()

    def refresh_keys(self):
        child = self.kbd.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.kbd.remove(child)
            child = nxt
        self.key_buttons = {}
        scale = 1.35
        for k in LAYOUTS[self.model]:
            pos = f'{k["row"]},{k["col"]}'
            b = Gtk.Button(css_classes=["kbd-key"])
            b.set_size_request(int(k["w"] * scale), int(k["h"] * scale))
            self.update_key_button(b, k, self.profile["bindings"].get(pos))
            b.connect("clicked", self.on_key_clicked, k)
            self.kbd.put(b, k["x"] * scale, k["y"] * scale)
            self.key_buttons[pos] = b

    def update_key_button(self, b, k, binding):
        for c in ("bound-key", "bound-macro", "bound-disabled"):
            b.remove_css_class(c)
        label = k["label"]
        tip = f"{k['label']}: padrão"
        if binding:
            if binding["type"] == "key":
                label = hid_name(binding["value"])
                tip = f"{k['label']} → {label}"
                b.add_css_class("bound-key")
            elif binding["type"] == "macro":
                macros = self.profile["macros"]
                name = macros[binding["value"]]["name"] if binding["value"] < len(macros) else "?"
                label = f"M{binding['value'] + 1}"
                tip = f"{k['label']} → macro “{name}”"
                b.add_css_class("bound-macro")
            elif binding["type"] == "disabled":
                tip = f"{k['label']}: desativada"
                b.add_css_class("bound-disabled")
        lbl = Gtk.Label(label=label, ellipsize=3, max_width_chars=6)
        b.set_child(lbl)
        b.set_tooltip_text(tip)

    def on_key_clicked(self, btn, k):
        pos = f'{k["row"]},{k["col"]}'
        pop = Gtk.Popover()
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6, margin_bottom=6,
                     margin_start=6, margin_end=6)
        vb.append(Gtk.Label(label=f"<b>{GLib.markup_escape_text(k['label'])}</b>", use_markup=True))

        def setb(binding):
            if binding is None:
                self.profile["bindings"].pop(pos, None)
            else:
                self.profile["bindings"][pos] = binding
            self.save_profile()
            self.update_key_button(btn, k, binding)
            pop.popdown()

        d = Gtk.Button(label="Padrão")
        d.connect("clicked", lambda *_: setb(None))
        vb.append(d)
        if k["code"] != -10:
            off = Gtk.Button(label="Desativar tecla")
            off.connect("clicked", lambda *_: setb({"type": "disabled", "value": 0}))
            vb.append(off)

        keys = bindable_keys()
        dd = Gtk.DropDown.new_from_strings([n for _, n in keys])
        dd.set_enable_search(True)
        keyrow = Gtk.Box(spacing=6)
        keyrow.append(dd)
        okk = Gtk.Button(label="Usar tecla")
        okk.connect("clicked", lambda *_: setb({"type": "key", "value": keys[dd.get_selected()][0]}))
        keyrow.append(okk)
        vb.append(keyrow)

        if self.profile["macros"]:
            mrow = Gtk.Box(spacing=6)
            mdd = Gtk.DropDown.new_from_strings([f"M{i + 1} · {m['name']}"
                                                 for i, m in enumerate(self.profile["macros"])])
            mrow.append(mdd)
            okm = Gtk.Button(label="Usar macro")
            okm.connect("clicked", lambda *_: setb({"type": "macro", "value": mdd.get_selected()}))
            mrow.append(okm)
            vb.append(mrow)
        else:
            vb.append(Gtk.Label(label="Crie macros na aba Macros", css_classes=["dim-label"]))

        pop.set_child(vb)
        pop.set_parent(btn)
        pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
        pop.popup()

    def on_clear_bindings(self, *_):
        self.profile["bindings"] = {}
        self.save_profile()
        self.refresh_keys()

    # ------------------------------------------------------------------ key tester
    def build_tester_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=18, margin_bottom=18,
                      margin_start=18, margin_end=18)
        top = Gtk.Box(spacing=12)
        self.test_info = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        top.append(self.test_info)
        self.test_count = Gtk.Label(css_classes=["dim-label"])
        top.append(self.test_count)
        reset = Gtk.Button(label="Reiniciar teste")
        reset.connect("clicked", lambda *_: self.refresh_tester())
        top.append(reset)
        box.append(top)

        self.test_kbd = Gtk.Fixed(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, hexpand=True)
        box.append(Gtk.Frame(child=self.test_kbd, css_classes=["card"]))

        self.test_last = Gtk.Label(label="Pressione uma tecla", css_classes=["test-last"])
        box.append(self.test_last)
        self.test_log = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE)
        box.append(Gtk.ScrolledWindow(child=self.test_log, vexpand=True, min_content_height=120))

        # swallow key presses while the tester is visible so they don't activate widgets
        keyctl = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keyctl.connect("key-pressed", self.on_tester_gtk_key, True)
        keyctl.connect("key-released", self.on_tester_gtk_key, False)
        self.add_controller(keyctl)

        self.test_reader = KeyboardReader()
        self.test_pressed = set()
        self.test_watches = []
        self.test_last_time = None
        self.open_tester_nodes()
        self.refresh_tester()
        return box

    def open_tester_nodes(self):
        for src in self.test_watches:
            GLib.source_remove(src)
        self.test_watches = []
        for path, boot in find_input_nodes():
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            self.test_watches.append(GLib.unix_fd_add_full(GLib.PRIORITY_DEFAULT, fd,
                                                           GLib.IOCondition.IN | GLib.IOCondition.HUP,
                                                           self.on_tester_report, (fd, path, boot)))
        if self.test_watches:
            self.test_info.set_label("Pressione as teclas do TG700: lendo os códigos HID brutos enviados pelo "
                                     "teclado. A tecla Fn é tratada pelo próprio teclado e não envia código.")
        else:
            self.test_info.set_label("Teclado não acessível diretamente: usando os eventos do sistema "
                                     "(qualquer teclado conectado será detectado).")

    def refresh_tester(self):
        child = self.test_kbd.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.test_kbd.remove(child)
            child = nxt
        self.test_keys = {}
        self.test_tested = set()
        scale = 1.2
        layout = LAYOUTS[self.model]
        for k in layout:
            lbl = Gtk.Label(label=k["label"], css_classes=["test-key"], ellipsize=3, max_width_chars=6)
            lbl.set_size_request(int(k["w"] * scale), int(k["h"] * scale))
            self.test_kbd.put(lbl, k["x"] * scale, k["y"] * scale)
            self.test_keys.setdefault(k["code"], []).append(lbl)
        self.test_total = len([k for k in layout if k["code"] > 0])
        self.test_log.remove_all()
        self.test_last.set_label("Pressione uma tecla")
        self.update_test_count()

    def update_test_count(self):
        self.test_count.set_label(f"{len(self.test_tested)}/{self.test_total} teclas testadas")

    def on_tester_report(self, fd, cond, data):
        fd, path, boot = data
        if cond & GLib.IOCondition.HUP:
            os.close(fd)
            return False
        try:
            while True:
                report = os.read(fd, 64)
                if not report:
                    break
                self.test_reader.feed(path, boot, report)
        except BlockingIOError:
            pass
        except OSError:
            os.close(fd)
            return False
        now = self.test_reader.pressed()
        for code in sorted(now - self.test_pressed):
            self.tester_event(code, True)
        for code in sorted(self.test_pressed - now):
            self.tester_event(code, False)
        self.test_pressed = now
        return True

    def on_tester_gtk_key(self, _ctl, _keyval, keycode, _state, down):
        if self.stack.get_visible_child_name() != "tester":
            return False
        if not self.test_watches:
            hid = EVDEV_TO_HID.get(keycode - 8)
            if hid is not None:
                self.tester_event(hid, down)
        return True

    def tester_event(self, code, down):
        consumer = code & 0x10000
        name = f"Mídia 0x{code & 0xFFFF:03X}" if consumer else hid_name(code)
        for lbl in self.test_keys.get(code, []):
            if down:
                lbl.add_css_class("down")
                lbl.add_css_class("tested")
                self.test_tested.add(code)
            else:
                lbl.remove_css_class("down")
        if down:
            self.test_last.set_label(f"{name}  ·  HID 0x{code & 0xFFFF:02X}")
            self.update_test_count()
        t = time.monotonic()
        delta = "" if self.test_last_time is None else f"+{int((t - self.test_last_time) * 1000)} ms"
        self.test_last_time = t
        row = Adw.ActionRow(title=f"{'↓' if down else '↑'} {name}",
                            subtitle=f"HID 0x{code & 0xFFFF:02X}" + ("" if code in self.test_keys or consumer
                                                                      else " · fora do layout"))
        row.add_suffix(Gtk.Label(label=delta, css_classes=["dim-label"]))
        self.test_log.prepend(row)
        last = self.test_log.get_row_at_index(60)
        if last:
            self.test_log.remove(last)

    # ------------------------------------------------------------------ apply
    def save_profile(self):
        profile_store.save(self.profile)

    def on_apply_all(self, *_):
        if self.rec_btn.get_active():
            self.rec_btn.set_active(False)

        def write():
            for slot in range(MACRO_SLOTS):
                if slot < len(self.profile["macros"]):
                    m = self.profile["macros"][slot]
                    self.device.write_macro(slot, [tuple(e) for e in m["events"]], 1, m.get("repeat", 1))
                else:
                    self.device.clear_macro(slot)
            self.device.write_keymap(build_keymap(self.model, self.profile["bindings"]))
        self.guarded(write, ok_msg="Macros e teclas gravadas no teclado")


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_startup(self):
        Adw.Application.do_startup(self)
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        win = self.props.active_window or Window(self)
        win.present()


def main():
    return App().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
