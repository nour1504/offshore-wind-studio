# mypy: ignore-errors
"""Offshore Wind Studio's window on Linux, drawn with the system's GTK and WebKitGTK.

Run by the application with the system's own python3 (never the bundled one), so it uses the
desktop's libraries: ``python3 window.py <url>`` shows the interface served on 127.0.0.1 and
returns when the window is closed; ``python3 window.py --probe`` only says whether it can.
Kept compatible with Python 3.7 (Debian 10 / Scibian 10).
"""

import os
import sys


def load():
    import gi

    gi.require_version("Gtk", "3.0")
    for version in ("4.1", "4.0"):
        try:
            gi.require_version("WebKit2", version)
            break
        except ValueError:
            continue
    else:
        raise ImportError("WebKit2GTK is not installed")  # internal
    from gi.repository import GLib, Gtk, WebKit2

    return GLib, Gtk, WebKit2


def main(argv):
    try:
        GLib, Gtk, WebKit2 = load()
    except (ImportError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    if not Gtk.init_check(argv)[0]:
        return 3
    if "--probe" in argv:
        return 0
    url = argv[1]
    window = Gtk.Window(title="Offshore Wind Studio")
    window.set_default_size(1440, 900)
    window.set_size_request(1024, 700)
    icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "owstudio.png")
    if os.path.isfile(icon):
        window.set_icon_from_file(icon)
    view = WebKit2.WebView()
    settings = view.get_settings()
    settings.set_enable_developer_extras(False)

    downloads = GLib.get_user_special_dir(
        GLib.UserDirectory.DIRECTORY_DOWNLOAD
    ) or os.path.expanduser("~")

    def on_download(_context, download):
        # Exports (CSV, PDF, MP4, engine kit) go to the Downloads folder, like a browser
        def decide(item, suggested):
            target = os.path.join(downloads, os.path.basename(suggested) or "download")
            stem, extension = os.path.splitext(target)
            number = 1
            while os.path.exists(target):
                target = f"{stem} ({number}){extension}"
                number += 1
            item.set_destination("file://" + target)
            return True

        download.connect("decide-destination", decide)

    view.get_context().connect("download-started", on_download)
    window.add(view)
    window.connect("destroy", lambda _window: Gtk.main_quit())
    view.load_uri(url)
    window.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
