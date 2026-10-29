#!/usr/bin/env bash
# End-to-end checks of the Linux installers, run as root in the test distribution OffshoreWindStudio-Test
# (Debian) prepared by setup-env.sh test. The user "tester" has no administrator rights and its
# home folder holds no real data. Usage: test-install.sh <repository folder seen from Linux> <step>
#   deb      install the .deb with apt, menu entry, start, health, uninstall (data kept)
#   run      the no-sudo installer as "tester": install, update, start, health, uninstall
#   buster   the application starts in a minimal Debian 10 (glibc 2.28, no desktop library)
#   window   desktop start with WSLg: own window (system GTK); browser mode without it
set -euo pipefail

REPO="$1"
STEP="$2"
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$REPO/backend/src/owstudio/__init__.py")
DEB="$REPO/dist/linux/offshore-wind-studio_${VERSION}_amd64.deb"
RUN="$REPO/dist/linux/OffshoreWindStudio-${VERSION}-linux-setup.run"
# Without a graphical session: installers write their messages instead of opening dialogs
as_tester() { runuser -u tester -- env -u DISPLAY -u WAYLAND_DISPLAY HOME=/home/tester "$@"; }
as_tester_desktop() { runuser -u tester -- env HOME=/home/tester "$@"; }

health() {  # health <port>: waits for the server, prints its answer
    for _ in $(seq 1 60); do
        if answer=$(curl -fsS "http://127.0.0.1:$1/api/health" 2>/dev/null); then
            echo "$answer"
            return 0
        fi
        sleep 1
    done
    echo "no answer on port $1" >&2
    return 1
}

stop() {  # stop <pid>: the process started here, and only it
    kill "$1" 2>/dev/null || true
    wait "$1" 2>/dev/null || true
}

case "$STEP" in
deb)
    echo "== package"
    dpkg-deb --info "$DEB" | sed -n '1,20p'
    dpkg-deb --contents "$DEB" | grep -E "usr/bin|applications|icons|OffshoreWindStudio$" | head
    apt-get install -y -q "$DEB" >/dev/null
    desktop-file-validate /usr/share/applications/offshore-wind-studio.desktop && echo "menu entry valid"
    test -x /opt/offshore-wind-studio/OffshoreWindStudio
    as_tester mkdir -p /home/tester/OffshoreWindStudio/keep && as_tester touch /home/tester/OffshoreWindStudio/keep/project.txt
    as_tester offshore-wind-studio serve --port 8795 >/tmp/ows-deb.log 2>&1 &
    pid=$!
    health 8795
    stop "$pid"
    apt-get remove -y -q offshore-wind-studio >/dev/null
    test ! -e /opt/offshore-wind-studio && test ! -e /usr/share/applications/offshore-wind-studio.desktop
    test -f /home/tester/OffshoreWindStudio/keep/project.txt && echo "removed; user data kept"
    ;;
run)
    echo "== no-sudo installer"
    cp "$RUN" /home/tester/setup.run && chown tester: /home/tester/setup.run
    chmod 0644 /home/tester/setup.run  # as after a download: not executable
    as_tester sh /home/tester/setup.run
    as_tester test -x /home/tester/.local/share/OffshoreWindStudio/OffshoreWindStudio
    desktop-file-validate /home/tester/.local/share/applications/offshore-wind-studio.desktop
    desktop-file-validate /home/tester/.local/share/applications/offshore-wind-studio-uninstall.desktop
    echo "menu entries valid"
    as_tester sh /home/tester/setup.run >/dev/null && echo "installed again over itself (update)"
    as_tester /home/tester/.local/bin/offshore-wind-studio serve --port 8797 >/tmp/ows-run.log 2>&1 &
    pid=$!
    health 8797
    stop "$pid"
    as_tester sh /home/tester/.local/share/OffshoreWindStudio/uninstall.sh
    test ! -e /home/tester/.local/share/OffshoreWindStudio
    test ! -e /home/tester/.local/share/applications/offshore-wind-studio.desktop
    test -f /home/tester/OffshoreWindStudio/keep/project.txt && echo "uninstalled; user data kept"
    ;;
buster)
    echo "== Debian 10 (glibc $(chroot /srv/buster ldd --version | head -1 | grep -o '[0-9.]*$'))"
    rm -rf /srv/buster/opt/OffshoreWindStudio
    mkdir -p /tmp/ows-buster
    tail -n "+$(awk '/^__PAYLOAD__$/ { print NR + 1; exit 0 }' "$RUN")" "$RUN" | tar -xz -C /srv/buster/opt
    mountpoint -q /srv/buster/proc || mount -t proc proc /srv/buster/proc
    chroot /srv/buster env HOME=/root /opt/OffshoreWindStudio/OffshoreWindStudio serve --port 8798 >/tmp/ows-buster.log 2>&1 &
    pid=$!
    health 8798
    curl -fsS -o /dev/null -w "interface: HTTP %{http_code}\n" http://127.0.0.1:8798/
    curl -fsS "http://127.0.0.1:8798/api/variables?names=RMOL" | head -c 80; echo
    stop "$pid"
    umount /srv/buster/proc
    rm -rf /srv/buster/opt/OffshoreWindStudio /srv/buster/root/.config /srv/buster/root/OffshoreWindStudio
    ;;
window)
    echo "== window and browser modes"
    apt-get install -y -q "$DEB" >/dev/null
    export XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir
    # Own window: the system's GTK and WebKitGTK through its python3
    as_tester_desktop env DISPLAY="${DISPLAY:-:0}" WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
        XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir /opt/offshore-wind-studio/OffshoreWindStudio >/tmp/ows-window.log 2>&1 &
    pid=$!
    sleep 15
    pgrep -u tester -af "data/linux/window.py http://127.0.0.1:" && echo "own window open"
    port=$(pgrep -u tester -af "data/linux/window.py" | grep -o '127.0.0.1:[0-9]*' | head -1 | cut -d: -f2)
    health "$port"
    echo "$port" > /tmp/ows-window-port
    if [ "${3:-}" != "--keep" ]; then
        pkill -u tester -f "data/linux/window.py" || true
        wait "$pid" 2>/dev/null || true
        echo "window closed: application stopped ($(pgrep -u tester -f OffshoreWindStudio >/dev/null && echo still running || echo yes))"
        # Browser mode: no graphical session for a window; the page and Quit stop it
        as_tester env -u DISPLAY -u WAYLAND_DISPLAY /opt/offshore-wind-studio/OffshoreWindStudio >/tmp/ows-browser.log 2>&1 &
        pid=$!
        sleep 8
        port=$(grep -o '127.0.0.1:[0-9]*' /tmp/ows-browser.log | head -1 | cut -d: -f2)
        health "$port"
        curl -fsS -X POST "http://127.0.0.1:$port/api/system/heartbeat"; echo
        curl -fsS -X POST "http://127.0.0.1:$port/api/system/quit"; echo
        sleep 4
        if kill -0 "$pid" 2>/dev/null; then echo "still running after Quit" >&2; stop "$pid"; exit 1; fi
        echo "browser mode: Quit stopped the application"
        apt-get remove -y -q offshore-wind-studio >/dev/null
    fi
    ;;
*)
    echo "unknown step $STEP" >&2
    exit 2
    ;;
esac
echo "ok: $STEP"
