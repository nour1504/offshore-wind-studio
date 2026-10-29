#!/bin/sh
# Offshore Wind Studio @VERSION@ - installateur Linux sans mot de passe administrateur.
#
# Installe le logiciel dans votre dossier personnel (~/.local/share/OffshoreWindStudio), ajoute
# Offshore Wind Studio et « Désinstaller Offshore Wind Studio » au menu des applications.
# Une version déjà installée est remplacée. Vos projets et réglages ne sont jamais touchés.
#
#   sh OffshoreWindStudio-@VERSION@-linux-setup.run              installer
#   sh OffshoreWindStudio-@VERSION@-linux-setup.run --uninstall  désinstaller
#
# The program follows this header as a gzip-compressed tar archive, after the __PAYLOAD__ line.
set -eu

VERSION="@VERSION@"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
DEST="$DATA/OffshoreWindStudio"
APPS="$DATA/applications"
ICONS="$DATA/icons/hicolor/256x256/apps"
BIN="$HOME/.local/bin"
SELF="$0"

say() {
    # In a terminal, a line; double-clicked, a dialog when the desktop has one
    if [ -t 1 ] || [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
        printf '%s\n' "$2"
    elif command -v zenity >/dev/null 2>&1; then
        zenity "--$1" --title="Offshore Wind Studio" --text="$2" >/dev/null 2>&1 || true
    elif command -v kdialog >/dev/null 2>&1; then
        kdialog --title "Offshore Wind Studio" "--msgbox" "$2" >/dev/null 2>&1 || true
    elif command -v notify-send >/dev/null 2>&1; then
        notify-send "Offshore Wind Studio" "$2" || true
    else
        printf '%s\n' "$2"
    fi
}

uninstall() {
    rm -rf "$DEST" "$DEST.new"
    rm -f "$APPS/offshore-wind-studio.desktop" "$APPS/offshore-wind-studio-uninstall.desktop" \
        "$ICONS/offshore-wind-studio.png"
    if [ -L "$BIN/offshore-wind-studio" ]; then rm -f "$BIN/offshore-wind-studio"; fi
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$APPS" 2>/dev/null || true
}

if [ "${1:-}" = "--uninstall" ]; then
    uninstall
    say info "Offshore Wind Studio est désinstallé. Vos projets (~/OffshoreWindStudio) et vos réglages sont conservés."
    exit 0
fi

case "$(uname -m)" in
    x86_64|amd64) ;;
    *) say error "Offshore Wind Studio demande un PC 64 bits Intel/AMD (x86_64)."; exit 1 ;;
esac

LINE=$(awk '/^__PAYLOAD__$/ { print NR + 1; exit 0 }' "$SELF")
mkdir -p "$DATA" "$APPS" "$ICONS" "$BIN"
rm -rf "$DEST.new"
mkdir -p "$DEST.new"
if ! tail -n "+$LINE" "$SELF" | tar -xz -C "$DEST.new"; then
    rm -rf "$DEST.new"
    say error "L'installation a échoué : le fichier semble incomplet. Téléchargez-le de nouveau."
    exit 1
fi
# The previous version is replaced only once the new one is complete
rm -rf "$DEST"
mv "$DEST.new/OffshoreWindStudio" "$DEST"
rmdir "$DEST.new"
cp "$DEST/owstudio.png" "$ICONS/offshore-wind-studio.png"
ln -sfn "$DEST/OffshoreWindStudio" "$BIN/offshore-wind-studio"

cat > "$DEST/uninstall.sh" <<EOF
#!/bin/sh
# Désinstalle Offshore Wind Studio $VERSION (vos projets et réglages sont conservés)
DATA="$DATA"; DEST="$DEST"; APPS="$APPS"; ICONS="$ICONS"; BIN="$BIN"
if [ -n "\${DISPLAY:-}\${WAYLAND_DISPLAY:-}" ] && command -v zenity >/dev/null 2>&1; then
    zenity --question --title="Offshore Wind Studio" --text="Désinstaller Offshore Wind Studio ? Vos projets et réglages sont conservés." || exit 0
fi
rm -rf "\$DEST"
rm -f "\$APPS/offshore-wind-studio.desktop" "\$APPS/offshore-wind-studio-uninstall.desktop" "\$ICONS/offshore-wind-studio.png"
[ -L "\$BIN/offshore-wind-studio" ] && rm -f "\$BIN/offshore-wind-studio"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "\$APPS" 2>/dev/null || true
exit 0
EOF
chmod 0755 "$DEST/uninstall.sh"

cat > "$APPS/offshore-wind-studio.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Offshore Wind Studio
Comment=WRF/WPS wind and wake simulations for offshore wind farms
Comment[fr]=Simulations WRF/WPS du vent et des sillages des parcs éoliens en mer
Exec="$DEST/OffshoreWindStudio"
Icon=$ICONS/offshore-wind-studio.png
Terminal=false
Categories=Science;Physics;
StartupNotify=true
EOF
cat > "$APPS/offshore-wind-studio-uninstall.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Uninstall Offshore Wind Studio
Name[fr]=Désinstaller Offshore Wind Studio
Exec=sh "$DEST/uninstall.sh"
Icon=$ICONS/offshore-wind-studio.png
Terminal=false
Categories=Science;Physics;
NoDisplay=false
EOF
chmod 0644 "$APPS/offshore-wind-studio.desktop" "$APPS/offshore-wind-studio-uninstall.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$APPS" 2>/dev/null || true

say info "Offshore Wind Studio $VERSION est installé. Ouvrez-le depuis le menu des applications."
exit 0
__PAYLOAD__
