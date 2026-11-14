import json
import os

VID, PID = 0x1A86, 0xFE07
TOTAL_LEDS = 71
SEG1_LEFT = 18
SEG2_TOP = 35
SEG3_RIGHT = 18
DOWNSAMPLE_STEP = 8
ZONE_RADIUS = 0.12

CONFIG_PATH = os.path.join(os.path.expanduser("~"), "ambilight_config.json")
ICO_PATH = os.path.join(os.path.expanduser("~"), "ambilight.ico")

DEVICES_META = [
    {
        "id": "monitor_qube",
        "title": "Монітор Qube 27\"",
        "subtitle": "USB HID • 71 LED",
        "leds": 71
    },
    {
        "id": "tv_nbbuff",
        "title": "Телевізор / Неон (WLED / RGBIC)",
        "subtitle": "Повторювач • WLED UDP / RGBIC",
        "leds": 90
    }
]

STRIP_SHAPES = [
    ("triangle", "Трикутник (V)"),
    ("u_shape", "П-подібна (П)")
]

SCENES_META = [
    ("hue_candle", "Камін", "#FF9E7D"),
    ("hue_aurora", "Сяйво", "#6EE7B7"),
    ("hue_sunset", "Захід сонця", "#F472B6"),
    ("hue_ocean", "Океан", "#60A5FA"),
    ("hue_cyber", "Неон", "#C084FC"),
]

HUD_PRESETS = {
    "top_left_hp": ("Лівий верхній HUD (HP/MP)", [0.00, 0.00, 0.30, 0.19]),
    "top_right_map": ("Правий верхній HUD (Мінікарта)", [0.75, 0.00, 1.00, 0.25]),
    "bottom_bar": ("Нижня панель навичок", [0.20, 0.82, 0.80, 1.00]),
    "bottom_left_chat": ("Лівий нижній кут (Чат)", [0.00, 0.68, 0.32, 1.00]),
    "letterbox_21_9": ("Кіно-смуга зверху 21:9", [0.00, 0.00, 1.00, 0.13])
}

DEFAULT_APP_RULES = {
    "BlackDesert64.exe": {
        "enabled": True,
        "display_name": "Black Desert Online",
        "profile": "Ігри",
        "hud_action": "neighbor_fill",
        "fire_boost_override": 2.5,
        "zones": [
            {"label": "Лівий верхній бар HP/MP", "rect": [0.00, 0.00, 0.30, 0.19]}
        ]
    }
}

DEFAULT_PROFILES = {
    "Ігри": {
        "mode": "ambilight",
        "brightness": 1.0,
        "smoothing": 0.45,
        "saturation": 1.28,
        "fire_boost": 6.0,
        "anim_speed": 1.0,
        "adaptive_dimming": True,
        "min_dim": 0.28,
        "fps": 45,
        "gain_r": 1.00,
        "gain_g": 0.82,
        "gain_b": 0.68,
        "static_color": [255, 165, 130]
    },
    "Кіно": {
        "mode": "ambilight",
        "brightness": 0.85,
        "smoothing": 0.68,
        "saturation": 1.22,
        "fire_boost": 6.5,
        "anim_speed": 1.0,
        "adaptive_dimming": True,
        "min_dim": 0.22,
        "fps": 45,
        "gain_r": 1.00,
        "gain_g": 0.82,
        "gain_b": 0.68,
        "static_color": [255, 165, 130]
    },
    "Затишок": {
        "mode": "hue_candle",
        "brightness": 0.75,
        "smoothing": 0.50,
        "saturation": 1.20,
        "fire_boost": 6.0,
        "anim_speed": 1.1,
        "adaptive_dimming": False,
        "min_dim": 0.25,
        "fps": 30,
        "gain_r": 1.00,
        "gain_g": 0.82,
        "gain_b": 0.68,
        "static_color": [255, 155, 100]
    },
    "Фон": {
        "mode": "static",
        "brightness": 0.50,
        "smoothing": 0.60,
        "saturation": 1.15,
        "fire_boost": 4.0,
        "anim_speed": 1.0,
        "adaptive_dimming": False,
        "min_dim": 0.20,
        "fps": 25,
        "gain_r": 1.00,
        "gain_g": 0.82,
        "gain_b": 0.68,
        "static_color": [255, 180, 135]
    }
}

PROTECTED_PROFILES = tuple(DEFAULT_PROFILES.keys())


class ConfigManager:
    def __init__(self):
        self.data = {
            "active_profile": "Кіно",
            "active_device": "monitor_qube",
            "strip_shape": "triangle",
            "repeater_enabled": False,
            "repeater_wled_ip": "",
            "repeater_leds": 90,
            "repeater_color_order": "RGB",
            "enabled": True,
            "theme": "dark",
            "autostart": True,
            "start_in_tray": True,
            "win_w": 580,
            "win_h": 790,
            "profiles": json.loads(json.dumps(DEFAULT_PROFILES)),
            "app_rules": json.loads(json.dumps(DEFAULT_APP_RULES))
        }
        self.load()

    def load(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if "profiles" in loaded and loaded["profiles"]:
                        self.data.update(loaded)
                    if "app_rules" not in self.data or not self.data["app_rules"]:
                        self.data["app_rules"] = json.loads(json.dumps(DEFAULT_APP_RULES))
            except Exception:
                pass
        for def_name, def_vals in DEFAULT_PROFILES.items():
            if def_name not in self.data["profiles"]:
                self.data["profiles"][def_name] = json.loads(json.dumps(def_vals))

    def save(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_profile(self, name: str) -> dict:
        if name not in self.data["profiles"]:
            name = next(iter(self.data["profiles"]))
        return self.data["profiles"][name]

    def current(self) -> dict:
        name = self.data["active_profile"]
        if name not in self.data["profiles"]:
            name = next(iter(self.data["profiles"]))
            self.data["active_profile"] = name
        return self.data["profiles"][name]
