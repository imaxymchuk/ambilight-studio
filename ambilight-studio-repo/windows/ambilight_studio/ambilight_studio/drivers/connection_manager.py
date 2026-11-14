import socket
import hid
import numpy as np
from ..config import VID, PID, TOTAL_LEDS
from ..logger import get_logger
from .usb_hid import UsbHidStripDriver
from .wled_udp import WledUdpDriver

log = get_logger("ConnectionManager")


class ConnectionManager:
    """
    Аналізує доступні контролери (USB HID, WLED мережа), перевіряє умови сумісності
    та керує виводом на головну стрічку і повторювачі (Mirror mode).
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.primary_driver = UsbHidStripDriver(num_leds=TOTAL_LEDS)
        self.repeater_drivers = []
        self._last_repeater_sig = None
        self.last_diagnostics = {}
        self.refresh_topology()

    def inspect_environment(self) -> dict:
        """Діагностика підключених контролерів та умов для роботи повторювача."""
        report = {
            "usb_hid_found": False,
            "usb_hid_info": "Не підключено",
            "wled_configured": False,
            "wled_reachable": False,
            "wled_info": "IP не вказано",
            "repeater_ready": False
        }

        try:
            devs = hid.enumerate(VID, PID)
            if devs:
                report["usb_hid_found"] = True
                prod = devs[0].get("product_string") or "USB RGBIC Controller"
                report["usb_hid_info"] = f"{prod} (0x{VID:04X}:0x{PID:04X}) • {TOTAL_LEDS} LED"
        except Exception as e:
            log.error(f"Помилка сканування USB HID: {e}")

        wled_ip = self.cfg.data.get("repeater_wled_ip", "").strip()
        if wled_ip:
            report["wled_configured"] = True
            try:
                socket.inet_aton(wled_ip)
                report["wled_reachable"] = True
                r_leds = int(self.cfg.data.get("repeater_leds", 90))
                r_order = self.cfg.data.get("repeater_color_order", "RGB")
                report["wled_info"] = f"WLED UDP {wled_ip}:4048 • {r_leds} LED ({r_order})"
            except OSError:
                report["wled_info"] = f"Некоректна IP-адреса: {wled_ip}"

        report["repeater_ready"] = bool(
            self.cfg.data.get("repeater_enabled", False) and report["wled_reachable"]
        )
        self.last_diagnostics = report
        return report

    def refresh_topology(self):
        """Оновлює список активних повторювачів згідно з конфігом та перевіркою умов."""
        diag = self.inspect_environment()
        rep_enabled = bool(self.cfg.data.get("repeater_enabled", False))
        wled_ip = self.cfg.data.get("repeater_wled_ip", "").strip()
        r_leds = max(1, int(self.cfg.data.get("repeater_leds", 90)))
        r_order = self.cfg.data.get("repeater_color_order", "RGB")

        sig = (rep_enabled, wled_ip, r_leds, r_order)
        if sig == self._last_repeater_sig:
            return

        self._last_repeater_sig = sig
        for drv in self.repeater_drivers:
            drv.turn_off()
            drv.close()
        self.repeater_drivers.clear()

        if rep_enabled:
            if not diag["wled_reachable"]:
                log.warning("Повторювач увімкнено, але умови не виконані: вкажіть коректну IP-адресу WLED.")
                return
            wled_drv = WledUdpDriver(ip=wled_ip, num_leds=r_leds, color_order=r_order)
            self.repeater_drivers.append(wled_drv)
            log.info(f"Режим повторювача активовано: основна ({TOTAL_LEDS} LED) -> копія ({r_leds} LED).")

    @staticmethod
    def resample_frame(rgb_array: np.ndarray, target_leds: int) -> np.ndarray:
        """Інтерполює масив кольорів під іншу кількість світлодіодів повторювача."""
        src_len = len(rgb_array)
        if src_len == target_leds:
            return rgb_array
        src_x = np.linspace(0.0, 1.0, src_len, dtype=np.float32)
        dst_x = np.linspace(0.0, 1.0, target_leds, dtype=np.float32)
        out = np.empty((target_leds, 3), dtype=np.uint8)
        for c in range(3):
            out[:, c] = np.interp(dst_x, src_x, rgb_array[:, c]).astype(np.uint8)
        return out

    def init_pc_mode(self):
        self.refresh_topology()
        self.primary_driver.init_pc_mode()
        for drv in self.repeater_drivers:
            drv.init_pc_mode()

    def send_frame(self, rgb_array: np.ndarray, profile: dict):
        self.primary_driver.send_frame(rgb_array, profile)
        if self.repeater_drivers:
            for drv in self.repeater_drivers:
                mapped = self.resample_frame(rgb_array, drv.num_leds)
                drv.send_frame(mapped, profile)

    def turn_off(self):
        self.primary_driver.turn_off()
        for drv in self.repeater_drivers:
            drv.turn_off()

    def close(self):
        self.primary_driver.close()
        for drv in self.repeater_drivers:
            drv.close()
