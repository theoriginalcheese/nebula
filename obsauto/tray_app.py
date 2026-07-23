import threading
import time

import pystray

from .icon_art import generate_animation_frames

ICON_PATH = None  # unused - kept only in case something still imports it


def build_tray_icon(app_window, icon_path):
    frames = generate_animation_frames(size=64, n_frames=24)
    stop_animation = threading.Event()

    def _show(icon, item):
        app_window.show()

    def _start(icon, item):
        app_window.root.after(0, app_window._start)

    def _stop(icon, item):
        app_window.root.after(0, app_window._stop)

    def _quit(icon, item):
        stop_animation.set()
        icon.stop()
        app_window.quit()

    menu = pystray.Menu(
        pystray.MenuItem("Show window", _show, default=True),
        pystray.MenuItem("Start monitoring", _start),
        pystray.MenuItem("Stop monitoring", _stop),
        pystray.MenuItem("Quit", _quit),
    )

    icon = pystray.Icon("nebula", frames[0], "Nebula", menu)
    thread = threading.Thread(target=icon.run, daemon=True)
    thread.start()

    def animate():
        i = 0
        while not stop_animation.wait(0.08):
            if icon.visible:
                icon.icon = frames[i % len(frames)]
                i += 1

    threading.Thread(target=animate, daemon=True).start()
    return icon
