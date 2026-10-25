#!/usr/bin/env bash
# Build a self-contained Debian package from the checkout.
#
#   bash packaging/build-deb.sh
#
# Output: dist/ophis_<version>_all.deb
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/ophis/__init__.py)
if [ -z "$VERSION" ]; then
  echo "could not read __version__ from src/ophis/__init__.py" >&2
  exit 1
fi

NAME=ophis
ARCH=all
ROOT="build/deb/${NAME}_${VERSION}_${ARCH}"
OUT="dist/${NAME}_${VERSION}_${ARCH}.deb"
MAINTAINER="Arda Aycan <87617257+EpicYamo@users.noreply.github.com>"

rm -rf "$ROOT" "$OUT"
mkdir -p "$ROOT/DEBIAN" \
         "$ROOT/usr/bin" \
         "$ROOT/usr/lib/ophis" \
         "$ROOT/usr/lib/udev/rules.d" \
         "$ROOT/usr/share/applications" \
         "$ROOT/usr/share/icons/hicolor/scalable/apps" \
         "$ROOT/usr/share/doc/ophis"

# --- payload ---------------------------------------------------------------
cp -r src/ophis "$ROOT/usr/lib/ophis/ophis"
cp -r data "$ROOT/usr/lib/ophis/data"
find "$ROOT/usr/lib/ophis" -name '__pycache__' -type d -prune -exec rm -rf {} +

write_wrapper() {
  local path="$1"
  local module="$2"
  shift 2
  cat > "$path" <<EOF
#!/bin/sh
exec /usr/bin/env PYTHONPATH=/usr/lib/ophis /usr/bin/python3 -m ${module} "$@"
EOF
  chmod 0755 "$path"
}

write_wrapper "$ROOT/usr/bin/ophis" "ophis.cli" '"$@"'
write_wrapper "$ROOT/usr/bin/ophis-gui" "ophis.gui.app" '--tray --show "$@"'
write_wrapper "$ROOT/usr/bin/ophis-tray" "ophis.tray" '"$@"'

sed 's|^Exec=.*|Exec=ophis-gui|; s|^Icon=.*|Icon=io.github.epicyamo.Ophis|' \
  data/ophis.desktop > "$ROOT/usr/share/applications/io.github.epicyamo.Ophis.desktop"
cp data/io.github.epicyamo.Ophis.svg \
   "$ROOT/usr/share/icons/hicolor/scalable/apps/io.github.epicyamo.Ophis.svg"
cp data/99-razer-hidraw.rules "$ROOT/usr/lib/udev/rules.d/99-razer-hidraw.rules"

cp README.md CHANGELOG.md LICENSE "$ROOT/usr/share/doc/ophis/"
gzip -9 -n -c CHANGELOG.md > "$ROOT/usr/share/doc/ophis/changelog.gz"
cat > "$ROOT/usr/share/doc/ophis/copyright" <<EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: ophis
Source: https://github.com/EpicYamo/ophis

Files: *
Copyright: 2026 Arda Aycan
License: MIT
EOF

# --- maintainer scripts ----------------------------------------------------
cat > "$ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ -x /usr/bin/udevadm ]; then
    udevadm control --reload-rules || true
    udevadm trigger --action=change --subsystem-match=hidraw || true
fi
if [ -x /usr/bin/update-desktop-database ]; then
    update-desktop-database -q /usr/share/applications || true
fi
exit 0
EOF

cat > "$ROOT/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if [ -x /usr/bin/udevadm ]; then
        udevadm control --reload-rules || true
        udevadm trigger --action=change --subsystem-match=hidraw || true
    fi
fi
exit 0
EOF
chmod 0755 "$ROOT/DEBIAN/postinst" "$ROOT/DEBIAN/postrm"

# --- control ---------------------------------------------------------------
SIZE=$(du -sk --exclude=DEBIAN "$ROOT" | cut -f1)
cat > "$ROOT/DEBIAN/control" <<EOF
Package: ${NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.11), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1
Recommends: gir1.2-ayatanaappindicator3-0.1
Installed-Size: ${SIZE}
Maintainer: ${MAINTAINER}
Homepage: https://github.com/EpicYamo/ophis
Description: Control centre for the Razer Blade 14 (2022)
 Performance profiles, fan curves, per-key RGB animations, the lid logo and
 the battery charge limit, plus a tray application and a CLI. Talks to the
 laptop's embedded controller over hidraw; no kernel module and no daemon.
EOF

mkdir -p dist
dpkg-deb --build --root-owner-group "$ROOT" "$OUT"
echo "built $OUT"
