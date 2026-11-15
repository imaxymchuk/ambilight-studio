import sys
import threading
import ctypes
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon

from .logger import setup_logging
from .config import ConfigManager
from .drivers.connection_manager import ConnectionManager
from .core.engine import AmbilightEngine
from .platform_win import set_app_user_model_id, ensure_app_icon
from .ui.main_window import AmbilightQtWindow, TrayBridge


def _check_single_instance():
    # Створюємо іменований системний м'ютекс Windows
    kernel32 = ctypes.windll.kernel32
    mutex_name = "Local\\AmbilightStudio_SingleInstance_Mutex_v2"
    handle = kernel32.CreateMutexW(None, True, mutex_name)
    last_error = kernel32.GetLastError()
    # ERROR_ALREADY_EXISTS = 183
    if last_error == 183 or handle == 0:
        return None
    return handle


def main():
    setup_logging()
    
    # Перевірка на запуск другої копії на рівні ОС Windows
    mutex_handle = _check_single_instance()
    if not mutex_handle:
        app = QApplication(sys.argv)
        QMessageBox.warning(
            None,
            "Ambilight Studio",
            "Програма вже запущена! Перевірте системний трей біля годинника."
        )
        sys.exit(0)

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
        import pystray
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

    import pystray
    icon = pystray.Icon("AmbilightStudio", tray_img, "Ambilight Studio", menu=build_tray_menu())
    win.tray_icon = icon
    threading.Thread(target=icon.run, name="TrayIconThread", daemon=True).start()

    if "--tray" not in sys.argv:
        win.show()

    def _on_shutdown():
        engine.running = False
        try:
            conn_mgr.turn_off()
            conn_mgr.close()
        except Exception:
            pass

    app.aboutToQuit.connect(_on_shutdown)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()



