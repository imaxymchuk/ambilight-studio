import socket
import numpy as np
from ..logger import get_logger

log = get_logger("WledUdpDriver")


class WledUdpDriver:
    """Мережевий драйвер WLED / ESP32 через UDP DDP (порт 4048) для неонових та COB RGBIC стрічок."""

    def __init__(self, ip: str, num_leds: int = 90, color_order: str = "RGB"):
        self.ip = ip.strip()
        self.port = 4048
        self.num_leds = num_leds
        self.color_order = color_order
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.is_connected = bool(self.ip)
        if self.is_connected:
            log.info(f"Ініціалізовано WLED повторювач: {self.ip}:{self.port} ({num_leds} LED, {color_order})")

    def init_pc_mode(self):
        pass

    def send_frame(self, rgb_array: np.ndarray, profile: dict):
        if not self.ip:
            return
        br = float(profile.get("brightness", 1.0))
        scaled = np.clip(rgb_array.astype(np.float32) * br, 0, 255).astype(np.uint8)

        if self.color_order == "GRB":
            scaled = scaled[:, [1, 0, 2]]
        elif self.color_order == "BRG":
            scaled = scaled[:, [2, 0, 1]]

        payload = scaled.tobytes()
        data_len = len(payload)
        # Заголовок DDP (Distributed Display Protocol, 10 байт)
        header = bytearray([
            0x41, 0x01, 0x01, 0x01,
            0x00, 0x00, 0x00, 0x00,
            (data_len >> 8) & 0xFF, data_len & 0xFF
        ])
        try:
            self.sock.sendto(header + payload, (self.ip, self.port))
            self.is_connected = True
        except OSError as e:
            self.is_connected = False
            log.warning(f"Помилка відправки DDP кадру на {self.ip}: {e}")

    def turn_off(self):
        if not self.ip:
            return
        zeros = np.zeros((self.num_leds, 3), dtype=np.uint8)
        self.send_frame(zeros, {"brightness": 0.0})

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass
