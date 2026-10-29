#!/usr/bin/env bash
# Builds the Linux installers of Offshore Wind Studio, inside the dedicated WSL distribution
# OffshoreWindStudio-Build (AlmaLinux 8, glibc 2.28), from the repository mounted under /mnt/c.
# Started by packaging/build-linux.ps1 once the interface is built into backend/src/owstudio/web.
#
#   1. copies the sources into the Linux file system (fast) and runs the server tests there;
#   2. builds the application folder with PyInstaller (packaging/linux/owstudio-linux.spec);
#   3. checks that nothing needs a glibc newer than 2.28 (Debian 10 / Scibian 10);
#   4. writes dist/linux/offshore-wind-studio_<version>_amd64.deb (into /opt, needs sudo) and
#      dist/linux/OffshoreWindStudio-<version>-linux-setup.run (into the home folder, no sudo).
#
# Usage: build-linux.sh <repository folder seen from Linux> [--skip-tests]
set -euo pipefail

REPO="$1"
SKIP_TESTS="${2:-}"
ENV=/opt/owsbuild/env
WORK=/root/owsbuild/work
PY="$ENV/bin/python"
MAX_GLIBC=2.28
APP=offshore-wind-studio
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$REPO/backend/src/owstudio/__init__.py")
[ -n "$VERSION" ] || { echo "version not found" >&2; exit 1; }
[ -f "$REPO/backend/src/owstudio/web/index.html" ] || { echo "interface not built: run build-linux.ps1" >&2; exit 1; }
echo "Offshore Wind Studio $VERSION for Linux"

echo "1/5 Sources and tests"
rm -rf "$WORK"
mkdir -p "$WORK"
tar -C "$REPO" --exclude=backend/.venv --exclude=backend/.mypy_cache --exclude=backend/.ruff_cache \
    --exclude=__pycache__ -cf - backend | tar -C "$WORK" -xf -
# Files read from Windows look executable: the sources get ordinary permissions
find "$WORK/backend" -type f -exec chmod 0644 {} +
mkdir -p "$WORK/packaging"
cp "$REPO/packaging/launcher.py" "$WORK/packaging/"
cp -r "$REPO/packaging/linux" "$WORK/packaging/linux"
if [ "$SKIP_TESTS" != "--skip-tests" ]; then
    (cd "$WORK/backend" && PYTHONPATH=src "$PY" -B -m pytest -q -p no:cacheprovider --disable-warnings)
fi

echo "2/5 Application folder (PyInstaller)"
(cd "$WORK" && "$PY" -m PyInstaller --noconfirm --clean --log-level WARN \
    --distpath "$WORK/dist" --workpath "$WORK/build" packaging/linux/owstudio-linux.spec)
BUNDLE="$WORK/dist/OffshoreWindStudio"
"$BUNDLE/OffshoreWindStudio" --help >/dev/null

echo "3/5 Compatibility (glibc <= $MAX_GLIBC)"
newest=$(find "$BUNDLE" -type f \( -name '*.so*' -o -perm -u+x \) -exec sh -c 'file -b "$1" | grep -q "^ELF" && objdump -T "$1" 2>/dev/null' _ {} \; \
    | grep -o 'GLIBC_[0-9.]*' | sed 's/GLIBC_//' | sort -uV | tail -1)
echo "newest glibc symbol needed: $newest"
if [ "$(printf '%s\n%s\n' "$newest" "$MAX_GLIBC" | sort -V | tail -1)" != "$MAX_GLIBC" ]; then
    echo "a library needs glibc $newest, newer than $MAX_GLIBC" >&2
    exit 1
fi

OUT="$REPO/dist/linux"
mkdir -p "$OUT"
rm -f "$OUT"/*.deb "$OUT"/*.run

echo "4/5 Debian package (.deb)"
PKG="$WORK/deb"
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/256x256/apps"
cp -a "$BUNDLE" "$PKG/opt/$APP"
ln -s "/opt/$APP/OffshoreWindStudio" "$PKG/usr/bin/$APP"
install -m 0644 "$WORK/backend/src/owstudio/data/linux/owstudio.png" "$PKG/usr/share/icons/hicolor/256x256/apps/$APP.png"
cat > "$PKG/usr/share/applications/$APP.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Offshore Wind Studio
Comment=WRF/WPS wind and wake simulations for offshore wind farms
Comment[fr]=Simulations WRF/WPS du vent et des sillages des parcs éoliens en mer
Exec=/opt/$APP/OffshoreWindStudio
Icon=$APP
Terminal=false
Categories=Science;Physics;
StartupNotify=true
EOF
size=$(du -sk "$PKG/opt" | cut -f1)
cat > "$PKG/DEBIAN/control" <<EOF
Package: $APP
Version: $VERSION
Architecture: amd64
Maintainer: Offshore Wind Studio
Depends: libc6 (>= 2.28)
Section: science
Priority: optional
Installed-Size: $size
Homepage: https://www2.mmm.ucar.edu/wrf/
Description: Offshore wind studies with the official WRF/WPS models
 Prepares, runs and analyses WRF 4.8.0 / WPS 4.7.0 simulations of the wind and the
 wakes of offshore wind farms (Fitch and MAV schemes). Projects and data stay in the
 user's home folder and are never removed with the package.
EOF
# Menus and icons refresh when the desktop's tools exist; never an error otherwise
for script in postinst postrm; do
    printf '#!/bin/sh\nset -e\ncommand -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true\ncommand -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true\nexit 0\n' > "$PKG/DEBIAN/$script"
    chmod 0755 "$PKG/DEBIAN/$script"
done
chmod -R u=rwX,go=rX "$PKG/opt" "$PKG/usr"
# A .deb is an ar archive of debian-binary, control.tar.gz and data.tar.xz (what dpkg-deb
# writes); files belong to root
(cd "$PKG/DEBIAN" && tar --owner=0 --group=0 --numeric-owner -czf "$WORK/control.tar.gz" .)
(cd "$PKG" && tar --owner=0 --group=0 --numeric-owner -cJf "$WORK/data.tar.xz" ./opt ./usr)
echo "2.0" > "$WORK/debian-binary"
DEB="$OUT/${APP}_${VERSION}_amd64.deb"
(cd "$WORK" && ar rc "$DEB" debian-binary control.tar.gz data.tar.xz)

echo "5/5 Installer without administrator password (.run)"
RUN="$OUT/OffshoreWindStudio-$VERSION-linux-setup.run"
sed "s/@VERSION@/$VERSION/g" "$WORK/packaging/linux/setup-header.sh" > "$RUN"
(cd "$WORK/dist" && install -m 0644 "$WORK/backend/src/owstudio/data/linux/owstudio.png" OffshoreWindStudio/owstudio.png \
    && tar --owner=0 --group=0 --numeric-owner -cz OffshoreWindStudio) >> "$RUN"
chmod 0755 "$RUN"

ls -l "$OUT"
echo "done"
