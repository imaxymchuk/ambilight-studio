import colorsys
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QLinearGradient, QPainterPath
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QLineEdit, QSizePolicy
)
from ..config import TOTAL_LEDS, SEG1_LEFT, SEG2_TOP, SEG3_RIGHT


class SmoothToggle(QWidget):
    toggled = Signal(bool)

    def __init__(self, checked=True, parent=None):
        super().__init__(parent)
        self._checked = checked
        self.setFixedSize(52, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.c_on_track = QColor("#D0BCFF")
        self.c_on_thumb = QColor("#381E72")
        self.c_off_track = QColor("#36343B")
        self.c_off_thumb = QColor("#938F99")

    def set_palette_colors(self, on_track, on_thumb, off_track, off_thumb):
        self.c_on_track = QColor(on_track)
        self.c_on_thumb = QColor(on_thumb)
        self.c_off_track = QColor(off_track)
        self.c_off_thumb = QColor(off_thumb)
        self.update()

    def isChecked(self):
        return self._checked

    def setChecked(self, val: bool):
        if self._checked != val:
            self._checked = val
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self._checked = not self._checked
            self.update()
            self.toggled.emit(self._checked)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(1.0, 1.0, self.width() - 2.0, self.height() - 2.0)
        radius = rect.height() / 2.0

        if self._checked:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(self.c_on_track))
            p.drawRoundedRect(rect, radius, radius)
            thumb_d = 22.0
            cx = rect.right() - 4.0 - thumb_d / 2.0
            cy = rect.center().y()
            p.setBrush(QBrush(self.c_on_thumb))
            p.drawEllipse(QPointF(cx, cy), thumb_d / 2.0, thumb_d / 2.0)
        else:
            p.setPen(QPen(self.c_off_thumb, 1.8))
            p.setBrush(QBrush(self.c_off_track))
            p.drawRoundedRect(rect, radius, radius)
            thumb_d = 16.0
            cx = rect.left() + 7.0 + thumb_d / 2.0
            cy = rect.center().y()
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(self.c_off_thumb))
            p.drawEllipse(QPointF(cx, cy), thumb_d / 2.0, thumb_d / 2.0)


class MaterialSlider(QWidget):
    valueChanged = Signal(int)

    def __init__(self, min_val=0, max_val=100, parent=None):
        super().__init__(parent)
        self._min = min_val
        self._max = max_val
        self._val = min_val
        self._dragging = False
        self._hovered = False
        self.setFixedHeight(26)
        self.setCursor(Qt.PointingHandCursor)
        self.c_track = QColor("#36343B")
        self.c_fill = QColor("#D0BCFF")
        self.c_ring = QColor("#141218")

    def set_palette_colors(self, track_hex, fill_hex, ring_hex):
        self.c_track = QColor(track_hex)
        self.c_fill = QColor(fill_hex)
        self.c_ring = QColor(ring_hex)
        self.update()

    def setValue(self, v: int):
        v = max(self._min, min(self._max, int(v)))
        if self._val != v:
            self._val = v
            self.update()

    def value(self):
        return self._val

    def wheelEvent(self, event):
        event.ignore()

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def _pos_to_val(self, x: float):
        pad = 11.0
        usable = max(1.0, float(self.width()) - 2.0 * pad)
        ratio = max(0.0, min(1.0, (x - pad) / usable))
        new_v = int(round(self._min + ratio * (self._max - self._min)))
        if new_v != self._val:
            self._val = new_v
            self.update()
            self.valueChanged.emit(self._val)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._pos_to_val(event.position().x())

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._pos_to_val(event.position().x())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        pad = 11.0
        w = float(self.width())
        cy = float(self.height()) / 2.0
        usable = max(1.0, w - 2.0 * pad)
        ratio = (self._val - self._min) / max(1.0, float(self._max - self._min))
        hx = pad + ratio * usable

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(self.c_track))
        p.drawRoundedRect(QRectF(pad, cy - 3.5, usable, 7.0), 3.5, 3.5)

        if hx > pad:
            p.setBrush(QBrush(self.c_fill))
            p.drawRoundedRect(QRectF(pad, cy - 3.5, hx - pad, 7.0), 3.5, 3.5)

        if self._dragging or self._hovered:
            halo = QColor(self.c_fill)
            halo.setAlpha(55)
            p.setBrush(QBrush(halo))
            p.drawEllipse(QPointF(hx, cy), 13.0, 13.0)

        p.setBrush(QBrush(self.c_ring))
        p.drawEllipse(QPointF(hx, cy), 9.5, 9.5)
        p.setBrush(QBrush(self.c_fill))
        p.drawEllipse(QPointF(hx, cy), 7.0, 7.0)


class CollapsibleSection(QFrame):
    def __init__(self, title: str, expanded: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._expanded = expanded
        self._title = title

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(16, 12, 16, 14)
        main_lay.setSpacing(10)

        self.header_btn = QPushButton()
        self.header_btn.setObjectName("SectionHeaderBtn")
        self.header_btn.setCursor(Qt.PointingHandCursor)
        self.header_btn.setFixedHeight(28)
        self.header_btn.clicked.connect(self.toggle)
        main_lay.addWidget(self.header_btn)

        self.body = QWidget()
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(2, 4, 2, 0)
        self.body_lay.setSpacing(10)
        main_lay.addWidget(self.body)

        self._sync_state()

    def toggle(self):
        self._expanded = not self._expanded
        self._sync_state()

    def _sync_state(self):
        arrow = "▾" if self._expanded else "▸"
        self.header_btn.setText(f"{arrow}   {self._title}")
        self.body.setVisible(self._expanded)


class InteractiveHudCanvas(QWidget):
    zoneDrawn = Signal(list)
    zoneRemoved = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zones = []
        self.c_bg = QColor("#1D1B20")
        self.c_border = QColor("#49454F")
        self.c_accent = QColor("#D0BCFF")
        self.setFixedHeight(146)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.CrossCursor)

        self._dragging = False
        self._start_pt = QPointF()
        self._cur_pt = QPointF()

    def set_palette(self, bg_hex, border_hex, accent_hex):
        self.c_bg = QColor(bg_hex)
        self.c_border = QColor(border_hex)
        self.c_accent = QColor(accent_hex)
        self.update()

    def set_zones(self, zones_list):
        self.zones = zones_list or []
        self.update()

    def _screen_rect(self) -> QRectF:
        h = float(self.height() - 10)
        w = min(float(self.width() - 10), h * (16.0 / 9.0))
        x0 = (self.width() - w) / 2.0
        y0 = 5.0
        return QRectF(x0, y0, w, h)

    def _pt_to_norm(self, pt: QPointF):
        sr = self._screen_rect()
        nx = max(0.0, min(1.0, (pt.x() - sr.left()) / max(1.0, sr.width())))
        ny = max(0.0, min(1.0, (pt.y() - sr.top()) / max(1.0, sr.height())))
        return nx, ny

    def mousePressEvent(self, event):
        sr = self._screen_rect()
        if event.button() == Qt.LeftButton and sr.contains(event.position()):
            self._dragging = True
            self._start_pt = event.position()
            self._cur_pt = event.position()
            self.update()
        elif event.button() == Qt.RightButton and sr.contains(event.position()):
            nx, ny = self._pt_to_norm(event.position())
            for idx in range(len(self.zones) - 1, -1, -1):
                r = self.zones[idx].get("rect", [0, 0, 0, 0])
                if r[0] <= nx <= r[2] and r[1] <= ny <= r[3]:
                    self.zoneRemoved.emit(idx)
                    break

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._cur_pt = event.position()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            x1, y1 = self._pt_to_norm(self._start_pt)
            x2, y2 = self._pt_to_norm(event.position())
            rx1, rx2 = round(min(x1, x2), 2), round(max(x1, x2), 2)
            ry1, ry2 = round(min(y1, y2), 2), round(max(y1, y2), 2)
            if (rx2 - rx1) >= 0.04 and (ry2 - ry1) >= 0.04:
                self.zoneDrawn.emit([rx1, ry1, rx2, ry2])
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        sr = self._screen_rect()

        p.setPen(QPen(self.c_border, 1.5))
        p.setBrush(QBrush(self.c_bg))
        p.drawRoundedRect(sr, 12.0, 12.0)

        for z in self.zones:
            r = z.get("rect", [0, 0, 0, 0])
            zx = sr.left() + r[0] * sr.width()
            zy = sr.top() + r[1] * sr.height()
            zw = max(6.0, (r[2] - r[0]) * sr.width())
            zh = max(6.0, (r[3] - r[1]) * sr.height())

            fill = QColor("#FF6B6B")
            fill.setAlpha(75)
            p.setPen(QPen(QColor("#FF6B6B"), 1.6, Qt.DashLine))
            p.setBrush(QBrush(fill))
            p.drawRoundedRect(QRectF(zx, zy, zw, zh), 6.0, 6.0)

        if self._dragging:
            x1, y1 = self._pt_to_norm(self._start_pt)
            x2, y2 = self._pt_to_norm(self._cur_pt)
            rx1, rx2 = min(x1, x2), max(x1, x2)
            ry1, ry2 = min(y1, y2), max(y1, y2)

            zx = sr.left() + rx1 * sr.width()
            zy = sr.top() + ry1 * sr.height()
            zw = (rx2 - rx1) * sr.width()
            zh = (ry2 - ry1) * sr.height()

            sel_fill = QColor(self.c_accent)
            sel_fill.setAlpha(85)
            p.setPen(QPen(self.c_accent, 2.0))
            p.setBrush(QBrush(sel_fill))
            p.drawRoundedRect(QRectF(zx, zy, zw, zh), 6.0, 6.0)


class LedStripPreviewWidget(QWidget):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.off_color = QColor("#2B2930")
        self.device_mode = "monitor_qube"
        self.strip_shape = "triangle"
        self.setMinimumHeight(104)
        self.setMaximumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_off_color(self, hex_c):
        self.off_color = QColor(hex_c)
        self.update()

    def set_geometry_mode(self, dev_id: str, shape_mode: str):
        self.device_mode = dev_id
        self.strip_shape = shape_mode
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = float(self.width())
        h = float(self.height())
        arr = self.engine.latest_preview
        p.setPen(Qt.NoPen)

        if self.device_mode == "tv_nbbuff":
            pad_x, pad_y = 26.0, 12.0
            rw, rh = w - 2 * pad_x, h - 2 * pad_y
            perim = 2.0 * (rw + rh)
            for i in range(TOTAL_LEDS):
                d = (i / float(TOTAL_LEDS)) * perim
                if d < rw:
                    x, y = pad_x + d, pad_y
                elif d < rw + rh:
                    x, y = pad_x + rw, pad_y + (d - rw)
                elif d < 2 * rw + rh:
                    x, y = pad_x + rw - (d - rw - rh), pad_y + rh
                else:
                    x, y = pad_x, pad_y + rh - (d - 2 * rw - rh)
                self._draw_dot(p, x, y, arr[i])
            return

        if self.strip_shape == "u_shape":
            pad_x = 34.0
            top_y = 14.0
            bot_y = h - 12.0
            idx = 0

            for i in range(SEG1_LEFT):
                t = i / max(1, SEG1_LEFT - 1)
                y = bot_y - (bot_y - top_y - 10.0) * t
                self._draw_dot(p, pad_x, y, arr[idx])
                idx += 1

            for i in range(SEG2_TOP):
                t = (i + 0.5) / SEG2_TOP
                x = (pad_x + 8.0) + (w - 2.0 * (pad_x + 8.0)) * t
                self._draw_dot(p, x, top_y, arr[idx])
                idx += 1

            for i in range(SEG3_RIGHT):
                t = i / max(1, SEG3_RIGHT - 1)
                y = (top_y + 10.0) + (bot_y - top_y - 10.0) * t
                self._draw_dot(p, w - pad_x, y, arr[idx])
                idx += 1
            return

        cx = w / 2.0
        pad_x = 22.0
        span_x = cx - pad_x - 12.0
        idx = 0

        for i in range(SEG1_LEFT):
            t = i / max(1, SEG1_LEFT - 1)
            x = (cx - 12.0) - span_x * t
            y = (h - 14.0) - (h - 38.0) * t
            self._draw_dot(p, x, y, arr[idx])
            idx += 1

        for i in range(SEG2_TOP):
            t = (i + 0.5) / SEG2_TOP
            x = (pad_x + 10.0) + (w - 2.0 * (pad_x + 10.0)) * t
            y = 14.0
            self._draw_dot(p, x, y, arr[idx])
            idx += 1

        for i in range(SEG3_RIGHT):
            t = i / max(1, SEG3_RIGHT - 1)
            x = (w - pad_x) - span_x * t
            y = 24.0 + (h - 38.0) * t
            self._draw_dot(p, x, y, arr[idx])
            idx += 1

    def _draw_dot(self, p: QPainter, x: float, y: float, rgb):
        r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
        if r + g + b < 15:
            p.setBrush(QBrush(self.off_color))
            p.drawEllipse(QPointF(x, y), 3.6, 3.6)
        else:
            glow = QColor(r, g, b, 65)
            p.setBrush(QBrush(glow))
            p.drawEllipse(QPointF(x, y), 6.2, 6.2)
            p.setBrush(QBrush(QColor(r, g, b)))
            p.drawEllipse(QPointF(x, y), 3.8, 3.8)


class SVBoxWidget(QWidget):
    changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hue = 0.05
        self.sat = 0.5
        self.val = 1.0
        self.setMinimumHeight(136)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.CrossCursor)

    def set_hsv(self, h, s, v):
        self.hue, self.sat, self.val = h, s, v
        self.update()

    def _pick(self, pos):
        w = max(1.0, float(self.width() - 1))
        h = max(1.0, float(self.height() - 1))
        self.sat = max(0.0, min(1.0, pos.x() / w))
        self.val = max(0.0, min(1.0, 1.0 - (pos.y() / h)))
        self.update()
        self.changed.emit(self.sat, self.val)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._pick(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._pick(e.position())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(rect, 16.0, 16.0)
        p.setClipPath(path)

        base_c = QColor.fromHsvF(self.hue, 1.0, 1.0)
        grad_h = QLinearGradient(0, 0, self.width(), 0)
        grad_h.setColorAt(0.0, QColor("#FFFFFF"))
        grad_h.setColorAt(1.0, base_c)
        p.fillRect(rect, grad_h)

        grad_v = QLinearGradient(0, 0, 0, self.height())
        grad_v.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad_v.setColorAt(1.0, QColor(0, 0, 0, 255))
        p.fillRect(rect, grad_v)

        cx = self.sat * (self.width() - 1)
        cy = (1.0 - self.val) * (self.height() - 1)
        p.setPen(QPen(QColor("#000000"), 3.0))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), 7.5, 7.5)
        p.setPen(QPen(QColor("#FFFFFF"), 2.0))
        p.drawEllipse(QPointF(cx, cy), 7.5, 7.5)


class HueBarWidget(QWidget):
    changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hue = 0.05
        self.setFixedHeight(20)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

    def set_hue(self, h):
        self.hue = h
        self.update()

    def _pick(self, pos):
        w = max(1.0, float(self.width() - 1))
        self.hue = max(0.0, min(0.999, pos.x() / w))
        self.update()
        self.changed.emit(self.hue)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._pick(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._pick(e.position())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(0, 2, self.width(), self.height() - 4)
        grad = QLinearGradient(0, 0, self.width(), 0)
        for i in range(7):
            grad.setColorAt(i / 6.0, QColor.fromHsvF(min(0.999, i / 6.0), 1.0, 1.0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(rect, 8.0, 8.0)

        cx = self.hue * (self.width() - 16) + 8
        p.setPen(QPen(QColor("#222222"), 2.0))
        p.setBrush(QBrush(QColor("#FFFFFF")))
        p.drawEllipse(QPointF(cx, self.height() / 2.0), 8.5, 8.5)


class PhotoshopColorPicker(QWidget):
    colorChanged = Signal(list)

    def __init__(self, initial_rgb, parent=None):
        super().__init__(parent)
        r, g, b = [c / 255.0 for c in initial_rgb]
        self.h, self.s, self.v = colorsys.rgb_to_hsv(r, g, b)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(12)
        self.sv_box = SVBoxWidget()
        top.addWidget(self.sv_box, stretch=1)

        side = QVBoxLayout()
        side.setSpacing(8)
        self.swatch = QFrame()
        self.swatch.setFixedSize(94, 86)
        self.swatch.setObjectName("ColorSwatch")
        side.addWidget(self.swatch)

        self.hex_edit = QLineEdit()
        self.hex_edit.setFixedSize(94, 38)
        self.hex_edit.setAlignment(Qt.AlignCenter)
        self.hex_edit.setObjectName("HexInput")
        side.addWidget(self.hex_edit)
        top.addLayout(side)

        layout.addLayout(top)
        self.hue_bar = HueBarWidget()
        layout.addWidget(self.hue_bar)

        self.sv_box.changed.connect(self._on_sv)
        self.hue_bar.changed.connect(self._on_hue)
        self.hex_edit.editingFinished.connect(self._on_hex)
        self._sync_visuals(emit=False)

    def set_rgb(self, rgb):
        r, g, b = [c / 255.0 for c in rgb]
        self.h, self.s, self.v = colorsys.rgb_to_hsv(r, g, b)
        self._sync_visuals(emit=False)

    def _on_sv(self, s, v):
        self.s, self.v = s, v
        self._sync_visuals(emit=True)

    def _on_hue(self, h):
        self.h = h
        self._sync_visuals(emit=True)

    def _on_hex(self):
        txt = self.hex_edit.text().strip().lstrip("#")
        if len(txt) == 6:
            try:
                r, g, b = int(txt[0:2], 16), int(txt[2:4], 16), int(txt[4:6], 16)
                self.h, self.s, self.v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
                self._sync_visuals(emit=True)
            except ValueError:
                pass

    def _sync_visuals(self, emit=False):
        self.sv_box.set_hsv(self.h, self.s, self.v)
        self.hue_bar.set_hue(self.h)
        r, g, b = [int(round(c * 255)) for c in colorsys.hsv_to_rgb(self.h, self.s, self.v)]
        hex_s = f"#{r:02X}{g:02X}{b:02X}"
        self.swatch.setStyleSheet(f"QFrame#ColorSwatch {{ background-color: {hex_s}; border-radius: 18px; }}")
        if not self.hex_edit.hasFocus():
            self.hex_edit.setText(hex_s)
        if emit:
            self.colorChanged.emit([r, g, b])


class DrawerBackdropOverlay(QWidget):
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
