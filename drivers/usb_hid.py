import threading
import time
import hid
import numpy as np
from ..config import VID, PID, TOTAL_LEDS
from ..logger import get_logger

log = get_logger("UsbHidDriver")


class UsbHidStripDriver:
    """Апаратний драйвер USB HID контролера підсвітки (0x1A86:0xFE07)."""

    def __init__(self, num_leds: int = TOTAL_LEDS, color_order: str = "RGB"):
        self.num_leds = num_leds
        self.color_order = color_order
        self.lock = threading.Lock()
        self.device = None
        self.pkt_id = 1
        self.idx_col = np.arange(1, num_leds + 1, dtype=np.uint8)
        self.lut_cache_key = None
        self.lut_r = None
        self.lut_g = None
        self.lut_b = None
        self.is_connected = False

    def _next_id(self) -> int:
        self.pkt_id = 1 if self.pkt_id >= 254 else self.pkt_id + 1
        return self.pkt_id

    def _open_hid(self):
        try:
            devices = hid.enumerate(VID, PID)
            if not devices:
                log.warning(f"USB HID стрічку (VID={hex(VID)}, PID={hex(PID)}) не знайдено в системі.")
                self.is_connected = False
                return None

            target_path = next(
                (d["path"] for d in devices if b"mi_00" in d["path"].lower() or d["usage_page"] >= 0xFF00),
                devices[0]["path"]
            )
            dev = hid.device()
            dev.open_path(target_path)
            self.is_connected = True
            log.info(f"USB HID контролер успішно підключено ({self.num_leds} LED).")
            return dev
        except Exception as e:
            self.is_connected = False
            log.error(f"Не вдалося відкрити USB HID інтерфейс: {e}")
            return None

    def _send_buffer(self, buf: bytearray):
        if self.device is None:
            self.device = self._open_hid()
            if self.device is None:
                return
        try:
            for i in range(0, len(buf), 64):
                chunk = buf[i:i + 64]
                report = bytes([0x00]) + bytes(chunk) + bytes(64 - len(chunk))
                self.device.write(report)
        except OSError as e:
            log.warning(f"Втрачено зв'язок з USB HID стрічкою ({e}). Перепідключення...")
            self.is_connected = False
            try:
                self.device.close()
            except Exception:
                pass
            self.device = None

    def _make_rb_packet(self, action: int, payload: bytes = b"") -> bytearray:
        length = 6 + len(payload)
        buf = bytearray([0x52, 0x42, length, self._next_id(), action]) + bytearray(payload)
        buf.append(sum(buf) % 256)
        return buf

    def init_pc_mode(self):
        with self.lock:
            self._send_buffer(self._make_rb_packet(147, b"\x00"))
            time.sleep(0.06)

    def turn_off(self):
        with self.lock:
            for _ in range(3):
                self._send_buffer(self._make_rb_packet(151))
                time.sleep(0.015)

    def _update_luts(self, profile: dict):
        key = (
            profile.get("gain_r", 1.0),
            profile.get("gain_g", 0.82),
            profile.get("gain_b", 0.68),
            profile.get("brightness", 1.0)
        )
        if key == self.lut_cache_key:
            return
        self.lut_cache_key = key
        br = key[3]
        self.lut_r = np.array([int(min(255, ((i / 255.0) ** 2.00) * 255 * key[0] * br)) for i in range(256)], dtype=np.uint8)
        self.lut_g = np.array([int(min(255, ((i / 255.0) ** 2.22) * 255 * key[1] * br)) for i in range(256)], dtype=np.uint8)
        self.lut_b = np.array([int(min(255, ((i / 255.0) ** 2.35) * 255 * key[2] * br)) for i in range(256)], dtype=np.uint8)

    def send_frame(self, rgb_array: np.ndarray, profile: dict):
        self._update_luts(profile)
        corrected = np.empty_like(rgb_array)
        corrected[:, 0] = self.lut_r[rgb_array[:, 0]]
        corrected[:, 1] = self.lut_g[rgb_array[:, 1]]
        corrected[:, 2] = self.lut_b[rgb_array[:, 2]]

        if self.color_order == "GRB":
            corrected = corrected[:, [1, 0, 2]]
        elif self.color_order == "BRG":
            corrected = corrected[:, [2, 0, 1]]

        packed = np.column_stack((self.idx_col, corrected, self.idx_col)).tobytes()
        total_len = 7 + len(packed)
        header = bytearray([
            0x53, 0x43,
            (total_len >> 8) & 0xFF,
            total_len & 0xFF,
            self._next_id(),
            0x80
        ])
        full_pkt = header + packed
        full_pkt.append(sum(full_pkt) % 256)
        with self.lock:
            self._send_buffer(full_pkt)

    def close(self):
        if self.device:
            try:
                self.device.close()
            except Exception:
                pass
            self.device = None
            self.is_connected = False
