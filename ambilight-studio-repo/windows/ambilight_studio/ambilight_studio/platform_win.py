import colorsys
import ctypes
import os
import subprocess
import sys
import winreg
from PIL import Image, ImageDraw
from .config import ICO_PATH


def set_app_user_model_id():
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Custom.AmbilightStudio.Modular.V1")
        except Exception:
            pass


def get_foreground_process_name() -> str:
    if sys.platform != "win32":
        return ""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        h_proc = kernel32.OpenProcess(0x1000, False, pid.value)
        if not h_proc:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(512)
            size = ctypes.c_ulong(512)
            if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value)
        finally:
            kernel32.CloseHandle(h_proc)
    except Exception:
        pass
    return ""


def list_visible_processes() -> list:
    found = set()
    if sys.platform != "win32":
        return []
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def callback(hwnd, lparam):
            if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value:
                    h_proc = kernel32.OpenProcess(0x1000, False, pid.value)
                    if h_proc:
                        buf = ctypes.create_unicode_buffer(512)
                        size = ctypes.c_ulong(512)
                        if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                            exe = os.path.basename(buf.value)
                            if exe and exe.lower() not in (
                                "explorer.exe", "applicationframehost.exe",
                                "textinputhost.exe", "pythonw.exe", "python.exe"
                            ):
                                found.add(exe)
                        kernel32.CloseHandle(h_proc)
            return True

        user32.EnumWindows(WNDENUMPROC(callback), 0)
    except Exception:
        pass
    return sorted(found, key=str.lower)


def get_system_accent_hue() -> float:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM")
        val, _ = winreg.QueryValueEx(key, "AccentColor")
        winreg.CloseKey(key)
        r = (val & 0xFF) / 255.0
        g = ((val >> 8) & 0xFF) / 255.0
        b = ((val >> 16) & 0xFF) / 255.0
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        if s > 0.12:
            return h
    except Exception:
        pass
    return 0.74


def hsl_hex(h: float, s: float, l: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h % 1.0, max(0.0, min(1.0, l)), max(0.0, min(1.0, s)))
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def build_material_you_palette(mode="dark") -> dict:
    h = get_system_accent_hue()
    if mode == "dark":
        return {
            "bg_window": hsl_hex(h, 0.12, 0.08),
            "surface": hsl_hex(h, 0.14, 0.13),
            "surface_high": hsl_hex(h, 0.16, 0.19),
            "surface_hover": hsl_hex(h, 0.20, 0.25),
            "drawer_bg": hsl_hex(h, 0.15, 0.11),
            "border_subtle": hsl_hex(h, 0.16, 0.23),
            "primary": hsl_hex(h, 0.68, 0.76),
            "on_primary": hsl_hex(h, 0.65, 0.12),
            "primary_container": hsl_hex(h, 0.45, 0.28),
            "on_primary_container": hsl_hex(h, 0.75, 0.90),
            "text_main": hsl_hex(h, 0.10, 0.94),
            "text_muted": hsl_hex(h, 0.12, 0.64),
            "led_off": hsl_hex(h, 0.15, 0.23),
            "switch_off": hsl_hex(h, 0.14, 0.27),
            "danger_bg": "#3D1F24",
            "danger_hover": "#52282F",
            "danger_fg": "#FFB4AB"
        }
    return {
        "bg_window": hsl_hex(h, 0.22, 0.97),
        "surface": hsl_hex(h, 0.25, 0.92),
        "surface_high": hsl_hex(h, 0.26, 0.87),
        "surface_hover": hsl_hex(h, 0.30, 0.82),
        "drawer_bg": hsl_hex(h, 0.24, 0.95),
        "border_subtle": hsl_hex(h, 0.22, 0.80),
        "primary": hsl_hex(h, 0.55, 0.44),
        "on_primary": "#FFFFFF",
        "primary_container": hsl_hex(h, 0.65, 0.86),
        "on_primary_container": hsl_hex(h, 0.60, 0.16),
        "text_main": hsl_hex(h, 0.15, 0.12),
        "text_muted": hsl_hex(h, 0.14, 0.40),
        "led_off": hsl_hex(h, 0.20, 0.82),
        "switch_off": hsl_hex(h, 0.18, 0.76),
        "danger_bg": "#FFDAD6",
        "danger_hover": "#FFB4AB",
        "danger_fg": "#93000A"
    }


def apply_dwm_window_theme(hwnd: int, theme_name: str, bg_hex: str):
    if sys.platform != "win32":
        return
    try:
        dark_val = ctypes.c_int(1 if theme_name == "dark" else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_val), ctypes.sizeof(dark_val))
        clean_hex = bg_hex.lstrip("#")
        r, g, b = int(clean_hex[0:2], 16), int(clean_hex[2:4], 16), int(clean_hex[4:6], 16)
        colorref = ctypes.c_int((b << 16) | (g << 8) | r)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colorref), ctypes.sizeof(colorref))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(colorref), ctypes.sizeof(colorref))
    except Exception:
        pass


def sync_windows_autostart(enabled: bool, start_in_tray: bool):
    if sys.platform != "win32":
        return
    try:
        if not enabled:
            subprocess.run(
                ["schtasks", "/Delete", "/TN", "AmbilightStudio", "/F"],
                capture_output=True, creationflags=0x08000000
            )
            return
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = sys.executable
        user_dir = os.path.expanduser("~")
        args = "-m ambilight_studio --tray" if start_in_tray else "-m ambilight_studio"
        ps_cmd = (
            f'$a = New-ScheduledTaskAction -Execute "{pythonw}" -Argument "{args}" -WorkingDirectory "{user_dir}"; '
            f'$t = New-ScheduledTaskTrigger -AtLogOn; '
            f'$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Days 0); '
            f'Register-ScheduledTask -TaskName "AmbilightStudio" -Action $a -Trigger $t -Settings $s -Force | Out-Null'
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            capture_output=True, creationflags=0x08000000
        )
    except Exception:
        pass


def ensure_app_icon():
    h = get_system_accent_hue()
    c_outer = hsl_hex(h, 0.65, 0.72)
    c_mid = hsl_hex(h, 0.40, 0.90)
    c_core = hsl_hex((h + 0.08) % 1.0, 0.75, 0.68)

    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    imgs = []
    for w, h_px in sizes:
        scale = 4
        sw, sh = w * scale, h_px * scale
        img = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        pad = int(sw * 0.04)
        draw.ellipse((pad, pad, sw - pad, sh - pad), fill=c_outer)
        r1 = int(sw * 0.20)
        draw.ellipse((r1, r1, sw - r1, sh - r1), fill=c_mid)
        r2 = int(sw * 0.31)
        draw.ellipse((r2, r2, sw - r2, sh - r2), fill=c_core)
        imgs.append(img.resize((w, h_px), Image.Resampling.LANCZOS))
    try:
        imgs[-1].save(ICO_PATH, format="ICO", sizes=sizes)
    except Exception:
        pass
    return imgs[4]
