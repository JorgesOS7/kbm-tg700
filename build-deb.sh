#!/bin/sh
# Builds dist/kbm-tg700_<version>_all.deb
set -e
cd "$(dirname "$0")"
VERSION=$(python3 -c "import kbm_tg700; print(kbm_tg700.__version__)")
ROOT=build/deb
rm -rf "$ROOT" && mkdir -p "$ROOT/DEBIAN" dist && chmod 755 "$ROOT"

install -d "$ROOT/usr/lib/kbm-tg700/kbm_tg700"
install -m 644 kbm_tg700/*.py kbm_tg700/layouts.json "$ROOT/usr/lib/kbm-tg700/kbm_tg700/"
install -d "$ROOT/usr/bin"
cat > "$ROOT/usr/bin/kbm-tg700" <<'SH'
#!/bin/sh
PYTHONPATH=/usr/lib/kbm-tg700${PYTHONPATH:+:$PYTHONPATH} exec python3 -m kbm_tg700 "$@"
SH
chmod 755 "$ROOT/usr/bin/kbm-tg700"
install -D -m 644 packaging/br.com.kbm.TG700Control.desktop "$ROOT/usr/share/applications/br.com.kbm.TG700Control.desktop"
install -D -m 644 packaging/br.com.kbm.TG700Control.svg "$ROOT/usr/share/icons/hicolor/scalable/apps/br.com.kbm.TG700Control.svg"
install -D -m 644 packaging/70-kbm-tg700.rules "$ROOT/usr/lib/udev/rules.d/70-kbm-tg700.rules"
install -D -m 644 README.md "$ROOT/usr/share/doc/kbm-tg700/README.md"

cat > "$ROOT/DEBIAN/control" <<CTL
Package: kbm-tg700
Version: $VERSION
Section: utils
Homepage: https://github.com/JorgesOS7/kbm-tg700
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1 (>= 1.4), udev
Maintainer: José Jorge <JorgesOS7@users.noreply.github.com>
Description: Controle RGB, macros e remapeamento para teclados KBM! GAMING TG600/TG700
 Versão nativa para Linux do software do teclado KBM! GAMING (KaBuM!) TG600/TG700
 (chip JieLi, USB 4a4c:e987). Permite trocar modo de iluminação, cor, brilho,
 velocidade e direção do RGB, gravar macros e remapear teclas na memória do teclado.
CTL
cat > "$ROOT/DEBIAN/postinst" <<'PI'
#!/bin/sh
set -e
if [ "$1" = configure ]; then
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger --subsystem-match=hidraw --action=change 2>/dev/null || true
    gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
fi
PI
cat > "$ROOT/DEBIAN/postrm" <<'PR'
#!/bin/sh
set -e
udevadm control --reload-rules 2>/dev/null || true
PR
chmod 755 "$ROOT/DEBIAN/postinst" "$ROOT/DEBIAN/postrm"
find "$ROOT" -name __pycache__ -prune -exec rm -rf {} +
dpkg-deb --root-owner-group --build "$ROOT" "dist/kbm-tg700_${VERSION}_all.deb"
