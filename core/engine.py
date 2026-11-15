import time
import dxcam
import numpy as np
from ..config import (
    ConfigManager, TOTAL_LEDS, SEG1_LEFT, SEG2_TOP, SEG3_RIGHT,
    DOWNSAMPLE_STEP, ZONE_RADIUS
)
from ..drivers.connection_manager import ConnectionManager
from ..platform_win import get_foreground_process_name
from ..logger import get_logger

log = get_logger("Engine")


class AmbilightEngine:
    """Ядро захоплення екрана, розрахунку кольору, HUD-винятків та генерації сцен."""

    def __init__(self, cfg: ConfigManager, driver: ConnectionManager):
        self.cfg = cfg
        self.driver = driver
        self.running = True
        self._cached_shape_mode = self.cfg.data.get("strip_shape", "triangle")
        self.led_coords = self._build_led_coordinates(self._cached_shape_mode)
        self.force_resend = True
        self.latest_preview = np.zeros((TOTAL_LEDS, 3), dtype=np.uint8)
        self._led_positions_norm = np.linspace(0.0, 1.0, TOTAL_LEDS, dtype=np.float32)
        self._rng = np.random.default_rng(42)

        self.active_fg_exe = ""
        self.active_rule_name = ""
        self._last_fg_check = 0.0

    def _emit_frame(self, rgb_array: np.ndarray, profile: dict):
        self.latest_preview = rgb_array.copy()
        self.driver.send_frame(rgb_array, profile)

    def _generate_hue_scene(self, mode: str, t: float, speed: float) -> np.ndarray:
        pos = self._led_positions_norm
        phase = t * speed

        if mode == "hue_candle":
            wave = 0.78 + 0.14 * np.sin(phase * 4.5 + pos * 9.0) + 0.08 * np.cos(phase * 7.3 - pos * 14.0)
            sparks = self._rng.uniform(0.88, 1.06, size=TOTAL_LEDS).astype(np.float32)
            intensity = np.clip(wave * sparks, 0.45, 1.0)
            r = np.full(TOTAL_LEDS, 255.0, dtype=np.float32) * intensity
            g = (95.0 + 35.0 * np.sin(phase * 3.1 + pos * 6.0)) * intensity
            b = (12.0 + 8.0 * np.cos(phase * 5.0 + pos * 11.0)) * intensity
            return np.column_stack((r, g, b)).astype(np.uint8)
        elif mode == "hue_aurora":
            w1 = 0.5 + 0.5 * np.sin(phase * 0.9 + pos * 5.5)
            w2 = 0.5 + 0.5 * np.cos(phase * 0.65 - pos * 4.0)
            r = 40.0 + 135.0 * (w2 ** 1.8)
            g = 210.0 * w1 + 40.0 * (1.0 - w2)
            b = 140.0 + 115.0 * (1.0 - w1 * 0.6)
            return np.clip(np.column_stack((r, g, b)), 0, 255).astype(np.uint8)
        elif mode == "hue_sunset":
            w = 0.5 + 0.5 * np.sin(phase * 0.7 + pos * 3.8)
            r = 255.0 * (0.85 + 0.15 * w)
            g = 65.0 + 110.0 * w
            b = 45.0 + 125.0 * (1.0 - w)
            return np.clip(np.column_stack((r, g, b)), 0, 255).astype(np.uint8)
        elif mode == "hue_ocean":
            w = 0.5 + 0.5 * np.sin(phase * 0.85 + pos * 6.0)
            r = 10.0 + 35.0 * w
            g = 90.0 + 135.0 * w
            b = 200.0 + 55.0 * (0.5 + 0.5 * np.cos(phase * 0.5 + pos * 3.0))
            return np.clip(np.column_stack((r, g, b)), 0, 255).astype(np.uint8)
        else:
            w = 0.5 + 0.5 * np.sin(phase * 1.4 + pos * 5.0)
            r = 235.0 * w + 25.0 * (1.0 - w)
            g = 35.0 + 95.0 * (1.0 - w)
            b = 210.0 + 45.0 * np.cos(phase * 1.1 - pos * 4.0)
            return np.clip(np.column_stack((r, g, b)), 0, 255).astype(np.uint8)

    def _build_led_coordinates(self, shape_mode: str) -> list:
        coords = []
        if shape_mode == "u_shape":
            for i in range(SEG1_LEFT):
                t = i / max(1, SEG1_LEFT - 1)
                coords.append(((0.08, 0.90 - 0.76 * t), (0.24, 0.78 - 0.50 * t)))
            for i in range(SEG2_TOP):
                t = (i + 0.5) / SEG2_TOP
                coords.append(((0.08 + 0.84 * t, 0.12), (0.24 + 0.52 * t, 0.28)))
            for i in range(SEG3_RIGHT):
                t = i / max(1, SEG3_RIGHT - 1)
                coords.append(((0.92, 0.14 + 0.76 * t), (0.76, 0.28 + 0.50 * t)))
        else:
            for i in range(SEG1_LEFT):
                t = i / max(1, SEG1_LEFT - 1)
                coords.append(((0.44 - 0.30 * t, 0.82 - 0.42 * t), (0.382 - 0.12 * t, 0.618 - 0.15 * t)))
            for i in range(SEG2_TOP):
                t = (i + 0.5) / SEG2_TOP
                coords.append(((0.12 + 0.76 * t, 0.16), (0.25 + 0.50 * t, 0.382)))
            for i in range(SEG3_RIGHT):
                t = i / max(1, SEG3_RIGHT - 1)
                coords.append(((0.86 - 0.30 * t, 0.40 + 0.42 * t), (0.74 - 0.12 * t, 0.468 + 0.15 * t)))
        return coords

    def _precompute_zone_indices(self, sh: int, sw: int):
        rx = max(2, int(sw * ZONE_RADIUS))
        ry = max(2, int(sh * ZONE_RADIUS))
        grid_y = np.linspace(-ry, ry, 5, dtype=np.int32)
        grid_x = np.linspace(-rx, rx, 5, dtype=np.int32)
        dy, dx = np.meshgrid(grid_y, grid_x, indexing="ij")
        dy, dx = dy.ravel(), dx.ravel()

        edge_y = np.empty((TOTAL_LEDS, 25), dtype=np.int32)
        edge_x = np.empty((TOTAL_LEDS, 25), dtype=np.int32)
        gold_y = np.empty((TOTAL_LEDS, 25), dtype=np.int32)
        gold_x = np.empty((TOTAL_LEDS, 25), dtype=np.int32)

        for idx, ((px, py), (gx, gy)) in enumerate(self.led_coords):
            edge_y[idx] = np.clip(int(py * sh) + dy, 0, sh - 1)
            edge_x[idx] = np.clip(int(px * sw) + dx, 0, sw - 1)
            gold_y[idx] = np.clip(int(gy * sh) + dy, 0, sh - 1)
            gold_x[idx] = np.clip(int(gx * sw) + dx, 0, sw - 1)
        return edge_y, edge_x, gold_y, gold_x

    def _apply_hud_exclusions(self, small_frame: np.ndarray, rule: dict) -> np.ndarray:
        zones = rule.get("zones", [])
        if not zones:
            return small_frame

        sh, sw, _ = small_frame.shape
        action = rule.get("hud_action", "neighbor_fill")
        masked = small_frame.copy()

        for z in zones:
            rect = z.get("rect", [0, 0, 0, 0])
            x1 = max(0, min(sw - 1, int(rect[0] * sw)))
            y1 = max(0, min(sh - 1, int(rect[1] * sh)))
            x2 = max(x1 + 1, min(sw, int(rect[2] * sw)))
            y2 = max(y1 + 1, min(sh, int(rect[3] * sh)))

            if action == "dim_zone":
                masked[y1:y2, x1:x2] = 0.0
            else:
                samples = []
                if y2 + 4 < sh:
                    samples.append(masked[y2:min(sh, y2 + 6), x1:x2].reshape(-1, 3))
                if x2 + 4 < sw:
                    samples.append(masked[y1:y2, x2:min(sw, x2 + 6)].reshape(-1, 3))
                if y1 - 4 > 0:
                    samples.append(masked[max(0, y1 - 6):y1, x1:x2].reshape(-1, 3))
                if x1 - 4 > 0:
                    samples.append(masked[y1:y2, max(0, x1 - 6):x1].reshape(-1, 3))

                if samples:
                    fill_color = np.median(np.vstack(samples), axis=0)
                else:
                    fill_color = np.array([0.0, 0.0, 0.0], dtype=np.float32)
                masked[y1:y2, x1:x2] = fill_color

        return masked

    def _analyze_zones(self, pixels_batch: np.ndarray, fire_boost_val: float):
        max_c = pixels_batch.max(axis=2)
        min_c = pixels_batch.min(axis=2)
        zone_energy = max_c.mean(axis=1) / 255.0

        luma_norm = max_c / 255.0
        sat = (max_c - min_c) / (max_c + 1e-5)

        r, b = pixels_batch[:, :, 0], pixels_batch[:, :, 2]
        warmth = np.clip((r - b) / 255.0, 0.0, 1.0)
        fire_boost = 1.0 + (warmth ** 1.5) * (luma_norm ** 2.0) * fire_boost_val

        weights = (luma_norm ** 2.4) * (0.35 + sat) * fire_boost + 0.002
        weights /= weights.sum(axis=1, keepdims=True)
        colors = (pixels_batch * weights[:, :, None]).sum(axis=1)

        fire_mask = (colors[:, 0] > colors[:, 1]) & (colors[:, 1] > colors[:, 2]) & ((colors[:, 0] - colors[:, 2]) > 8)
        colors[fire_mask, 2] *= 0.30
        colors[fire_mask, 1] *= 0.88
        return colors, zone_energy

    def _find_2k_output_idx(self) -> int:
        try:
            for line in dxcam.output_info().splitlines():
                if "2560x1440" in line:
                    return int(line.split("Output[")[1].split("]")[0])
        except Exception as e:
            log.warning(f"Не вдалося визначити 2K-монітор через dxcam: {e}")
        return 0

    def _match_active_rule(self):
        now = time.perf_counter()
        if now - self._last_fg_check >= 0.6:
            self._last_fg_check = now
            self.active_fg_exe = get_foreground_process_name()

        if not self.active_fg_exe:
            self.active_rule_name = ""
            return None

        rules = self.cfg.data.get("app_rules", {})
        fg_low = self.active_fg_exe.lower()
        for exe_key, rule in rules.items():
            if rule.get("enabled", True) and exe_key.lower() == fg_low:
                self.active_rule_name = exe_key
                return rule

        self.active_rule_name = ""
        return None

    def loop(self):
        self.driver.init_pc_mode()
        camera = None
        prev_colors = np.zeros((TOTAL_LEDS, 3), dtype=np.float32)
        last_sent = np.full((TOTAL_LEDS, 3), 255, dtype=np.uint8)
        cached_shape = None
        zone_indices = None
        none_streak = 0
        was_enabled = True
        t0 = time.perf_counter()

        while self.running:
            try:
                t_start = time.perf_counter()
                enabled = self.cfg.data.get("enabled", True)

                cur_shape_mode = self.cfg.data.get("strip_shape", "triangle")
                if cur_shape_mode != self._cached_shape_mode:
                    self._cached_shape_mode = cur_shape_mode
                    self.led_coords = self._build_led_coordinates(cur_shape_mode)
                    cached_shape = None
                    self.force_resend = True

                active_rule = self._match_active_rule()

                if active_rule and active_rule.get("profile") in self.cfg.data["profiles"]:
                    p = self.cfg.get_profile(active_rule["profile"])
                else:
                    p = self.cfg.current()

                fps = max(15, int(p.get("fps", 45)))
                frame_interval = 1.0 / fps

                if not enabled:
                    if was_enabled:
                        self.latest_preview.fill(0)
                        self.driver.turn_off()
                        was_enabled = False
                    time.sleep(0.15)
                    continue

                if not was_enabled:
                    self.driver.init_pc_mode()
                    was_enabled = True
                    self.force_resend = True

                mode = p.get("mode", "ambilight")

                if mode == "static":
                    sc = np.array(p.get("static_color", [255, 165, 130]), dtype=np.uint8)
                    arr = np.tile(sc, (TOTAL_LEDS, 1))
                    if self.force_resend or not np.array_equal(arr, last_sent):
                        self._emit_frame(arr, p)
                        last_sent[:] = arr
                        self.force_resend = False
                    time.sleep(0.05)
                    continue

                if mode.startswith("hue_"):
                    elapsed_total = t_start - t0
                    speed = float(p.get("anim_speed", 1.0))
                    scene_rgb = self._generate_hue_scene(mode, elapsed_total, speed).astype(np.float32)
                    sm = min(0.75, float(p.get("smoothing", 0.55)))
                    prev_colors = prev_colors * sm + scene_rgb * (1.0 - sm)
                    out_uint8 = np.clip(prev_colors, 0, 255).astype(np.uint8)
                    self._emit_frame(out_uint8, p)
                    last_sent[:] = out_uint8
                    sleep_time = max(0.015, (1.0 / 30.0) - (time.perf_counter() - t_start))
                    time.sleep(sleep_time)
                    continue

                if camera is None:
                    try:
                        out_idx = self._find_2k_output_idx()
                        camera = dxcam.create(output_idx=out_idx, output_color="BGRA")
                        log.info(f"DXGI захоплення екрана запущено (Output[{out_idx}]).")
                    except Exception as e:
                        log.error(f"Помилка ініціалізації dxcam: {e}")
                        time.sleep(0.5)
                        continue

                try:
                    frame = camera.grab()
                except Exception as e:
                    log.warning(f"Збій захоплення кадру dxcam ({e}). Скидання камери...")
                    frame = None
                    try:
                        del camera
                        camera = None
                    except Exception:
                        pass

                if frame is None:
                    none_streak += 1
                    if none_streak > 90:
                        none_streak = 0
                        try:
                            del camera
                            camera = None
                        except Exception:
                            pass
                    time.sleep(frame_interval)
                    continue

                none_streak = 0
                small = frame[::DOWNSAMPLE_STEP, ::DOWNSAMPLE_STEP, [2, 1, 0]].astype(np.float32)

                if active_rule:
                    small = self._apply_hud_exclusions(small, active_rule)

                sh, sw, _ = small.shape
                if cached_shape != (sh, sw):
                    cached_shape = (sh, sw)
                    zone_indices = self._precompute_zone_indices(sh, sw)

                ey, ex, gy, gx = zone_indices
                fb = float(active_rule.get("fire_boost_override", p.get("fire_boost", 6.0))) if active_rule else float(p.get("fire_boost", 6.0))
                p_col, p_energy = self._analyze_zones(small[ey, ex], fb)
                g_col, g_energy = self._analyze_zones(small[gy, gx], fb)

                edge_weight = np.clip(0.32 + p_energy * 2.2, 0.32, 0.75)[:, None]
                blended = p_col * edge_weight + g_col * (1.0 - edge_weight)
                energy = np.maximum(p_energy, g_energy * 0.85)

                mean_val = blended.mean(axis=1, keepdims=True)
                blended = mean_val + (blended - mean_val) * float(p.get("saturation", 1.24))

                if p.get("adaptive_dimming", True):
                    min_dim = float(p.get("min_dim", 0.28))
                    dim_factor = np.clip(min_dim + (energy ** 0.75) * (1.0 - min_dim), min_dim, 1.0)[:, None]
                    blended *= dim_factor

                blended = np.clip(blended, 0, 255)
                smoothed_spatial = blended.copy()
                smoothed_spatial[1:-1] = 0.22 * blended[:-2] + 0.56 * blended[1:-1] + 0.22 * blended[2:]

                luma = smoothed_spatial.mean(axis=1, keepdims=True)
                smoothed_spatial = np.where(luma < 5, 0.0, smoothed_spatial)

                sm = float(p.get("smoothing", 0.58))
                prev_colors = prev_colors * sm + smoothed_spatial * (1.0 - sm)
                out_uint8 = np.clip(prev_colors, 0, 255).astype(np.uint8)

                if self.force_resend or not np.array_equal(out_uint8, last_sent):
                    self._emit_frame(out_uint8, p)
                    last_sent[:] = out_uint8
                    self.force_resend = False

                elapsed = time.perf_counter() - t_start
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            except Exception as loop_err:
                log.error(f"Несподівана помилка в циклі обробки кадру: {loop_err}")
                time.sleep(0.25)

        self.latest_preview.fill(0)
        self.driver.turn_off()
        self.driver.close()
