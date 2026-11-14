import sys
import threading
import pystray
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .logger import setup_logging
from .config import ConfigManager
from .drivers.connection_manager import ConnectionManager
from .core.engine import AmbilightEngine
from .platform_win import set_app_user_model_id, ensure_app_icon
from .ui.main_window import AmbilightQtWindow, TrayBridge


def main():
    setup_logging()
    set_app_user_model_id()
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    tray_img = ensure_app_icon()
    cfg = ConfigManager()
    conn_mgr = ConnectionManager(cfg)
    engine = AmbilightEngine(cfg, conn_mgr)

    t_engine = threading.Thread(target=engine.loop, name="AmbilightEngineThread", daemon=True)
    t_engine.start()

    bridge = TrayBridge()
    win = AmbilightQtWindow(cfg, engine, bridge)

    def make_setter(n):
        return lambda icon, item: bridge.profile_req.emit(n)

    def make_checker(n):
        return lambda item: cfg.data["active_profile"] == n

    def build_tray_menu():
        profile_items = [
            pystray.MenuItem(name, make_setter(name), checked=make_checker(name))
            for name in cfg.data["profiles"].keys()
        ]
        return pystray.Menu(
            pystray.MenuItem("Відкрити", lambda icon, item: bridge.show_req.emit(), default=True),
            pystray.MenuItem("Увімкнено", lambda icon, item: bridge.toggle_req.emit(), checked=lambda item: cfg.data["enabled"]),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Профілі", pystray.Menu(*profile_items)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Вихід", lambda icon, item: bridge.quit_req.emit())
        )

    icon = pystray.Icon("AmbilightStudio", tray_img, "Ambilight Studio", menu=build_tray_menu())
    win.tray_icon = icon
    threading.Thread(target=icon.run, name="TrayIconThread", daemon=True).start()

    if "--tray" not in sys.argv:
        win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
