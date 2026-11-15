import json
import os
import threading
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QScrollArea, QFrame, QStackedWidget,
    QInputDialog, QMessageBox, QSizePolicy, QLineEdit
)
from ..logger import LOG_PATH
from ..config import (
    ConfigManager, DEVICES_META, STRIP_SHAPES, SCENES_META,
    HUD_PRESETS, DEFAULT_PROFILES, PROTECTED_PROFILES, ICO_PATH
)
from ..core.engine import AmbilightEngine
from ..platform_win import (
    build_material_you_palette, apply_dwm_window_theme,
    sync_windows_autostart, list_visible_processes
)
from .widgets import (
    SmoothToggle, MaterialSlider, CollapsibleSection,
    InteractiveHudCanvas, LedStripPreviewWidget,
    PhotoshopColorPicker, DrawerBackdropOverlay
)


class TrayBridge(QObject):
    show_req = Signal()
    toggle_req = Signal()
    profile_req = Signal(str)
    quit_req = Signal()


class AmbilightQtWindow(QMainWindow):
    def __init__(self, cfg: ConfigManager, engine: AmbilightEngine, bridge: TrayBridge):
        super().__init__()
        self.cfg = cfg
        self.engine = engine
        self.bridge = bridge

        self.theme_name = self.cfg.data.get("theme", "dark")
        if self.theme_name not in ("dark", "light"):
            self.theme_name = "dark"
        self.pal = build_material_you_palette(self.theme_name)

        self.setWindowTitle("Ambilight Studio")
        if os.path.exists(ICO_PATH):
            self.setWindowIcon(QIcon(ICO_PATH))

        w = max(520, int(self.cfg.data.get("win_w", 580)))
        h = max(680, int(self.cfg.data.get("win_h", 790)))
        self.resize(w, h)
        self.setMinimumSize(520, 640)

        self.mode_buttons = {}
        self.scene_buttons = {}
        self.nav_buttons = {}
        self.device_cards = {}
        self.shape_buttons = {}
        self.sliders = {}
        self._drawer_open = False

        self._build_ui()
        self._apply_stylesheet()
        self._load_profile_to_ui()
        self._sync_device_and_shape()
        self._refresh_rules_combo()
        self._refresh_diag_label()

        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self._tick_preview)
        self.preview_timer.start(100)

        self.bridge.show_req.connect(self._do_show)
        self.bridge.toggle_req.connect(self._on_power_toggled_from_tray)
        self.bridge.profile_req.connect(self._on_profile_from_tray)
        self.bridge.quit_req.connect(self._do_quit)

    def _build_ui(self):
        root_widget = QWidget()
        root_widget.setObjectName("RootBg")
        self.setCentralWidget(root_widget)

        root_vbox = QVBoxLayout(root_widget)
        root_vbox.setContentsMargins(0, 0, 0, 0)
        root_vbox.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        root_vbox.addWidget(self.scroll)

        scroll_canvas = QWidget()
        scroll_canvas.setObjectName("ScrollCanvas")
        self.scroll.setWidget(scroll_canvas)

        center_row = QHBoxLayout(scroll_canvas)
        center_row.setContentsMargins(20, 12, 20, 20)
        center_row.addStretch(1)

        self.main_col = QWidget()
        self.main_col.setMaximumWidth(680)
        self.main_col.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        center_row.addWidget(self.main_col, stretch=10)
        center_row.addStretch(1)

        col = QVBoxLayout(self.main_col)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(14)

        # 1. ШАПКА
        header = QHBoxLayout()
        header.setSpacing(12)

        self.btn_drawer = QPushButton("☰")
        self.btn_drawer.setObjectName("DrawerOpenBtn")
        self.btn_drawer.setCursor(Qt.PointingHandCursor)
        self.btn_drawer.setToolTip("Вибір пристрою відображення")
        self.btn_drawer.setFixedSize(42, 42)
        self.btn_drawer.clicked.connect(lambda: self._set_drawer_open(True))
        header.addWidget(self.btn_drawer, alignment=Qt.AlignVCenter)

        title_stack = QVBoxLayout()
        title_stack.setSpacing(2)
        self.lbl_title = QLabel("Ambilight Studio")
        self.lbl_title.setObjectName("AppTitle")
        self.lbl_sub = QLabel("Монітор Qube 27\" • 71 LED")
        self.lbl_sub.setObjectName("AppSub")
        title_stack.addWidget(self.lbl_title)
        title_stack.addWidget(self.lbl_sub)
        header.addLayout(title_stack, stretch=1)

        self.power_switch = SmoothToggle(checked=self.cfg.data.get("enabled", True))
        self.power_switch.toggled.connect(self._on_power_switch)
        header.addWidget(self.power_switch, alignment=Qt.AlignVCenter)

        col.addLayout(header)

        # 2. НАВІГАЦІЯ
        nav_card = QFrame()
        nav_card.setObjectName("NavPillContainer")
        nav_row = QHBoxLayout(nav_card)
        nav_row.setContentsMargins(6, 6, 6, 6)
        nav_row.setSpacing(6)

        tabs = [
            ("control", "Керування"),
            ("rules", "Ігри та винятки"),
            ("settings", "Налаштування")
        ]
        for idx, (n_key, n_label) in enumerate(tabs):
            btn = QPushButton(n_label)
            btn.setObjectName("NavTab")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(38)
            btn.clicked.connect(lambda checked=False, i=idx, k=n_key: self._switch_page(i, k))
            nav_row.addWidget(btn)
            self.nav_buttons[n_key] = btn

        col.addWidget(nav_card)

        # 3. СТЕК СТОРІНОК
        self.pages = QStackedWidget()
        col.addWidget(self.pages)

        # === СТОРІНКА 1: КЕРУВАННЯ ===
        page_ctrl = QWidget()
        p1 = QVBoxLayout(page_ctrl)
        p1.setContentsMargins(0, 0, 0, 0)
        p1.setSpacing(14)

        preview_card = QFrame()
        preview_card.setObjectName("Card")
        pv_lay = QVBoxLayout(preview_card)
        pv_lay.setContentsMargins(16, 12, 16, 12)
        pv_lay.setSpacing(8)

        self.shape_bar = QWidget()
        sb_row = QHBoxLayout(self.shape_bar)
        sb_row.setContentsMargins(0, 0, 0, 0)
        sb_row.setSpacing(8)

        lbl_geom = QLabel("Геометрія стрічки:")
        lbl_geom.setObjectName("AppSub")
        sb_row.addWidget(lbl_geom)
        sb_row.addStretch(1)

        for s_id, s_name in STRIP_SHAPES:
            s_btn = QPushButton(s_name)
            s_btn.setObjectName("ShapePillBtn")
            s_btn.setCursor(Qt.PointingHandCursor)
            s_btn.setFixedHeight(28)
            s_btn.clicked.connect(lambda checked=False, sh=s_id: self._select_strip_shape(sh))
            sb_row.addWidget(s_btn)
            self.shape_buttons[s_id] = s_btn

        pv_lay.addWidget(self.shape_bar)

        self.led_preview = LedStripPreviewWidget(self.engine)
        pv_lay.addWidget(self.led_preview)
        p1.addWidget(preview_card)

        mode_card = QFrame()
        mode_card.setObjectName("Card")
        mc_lay = QVBoxLayout(mode_card)
        mc_lay.setContentsMargins(14, 14, 14, 14)
        mc_lay.setSpacing(12)

        seg_row = QHBoxLayout()
        seg_row.setSpacing(8)
        for m_key, m_label in [("ambilight", "Екран"), ("scenes", "Сцени"), ("static", "Колір")]:
            btn = QPushButton(m_label)
            btn.setObjectName("ModeSegment")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(40)
            btn.clicked.connect(lambda checked=False, k=m_key: self._select_mode_group(k))
            seg_row.addWidget(btn)
            self.mode_buttons[m_key] = btn
        mc_lay.addLayout(seg_row)

        self.scenes_box = QWidget()
        sc_grid = QGridLayout(self.scenes_box)
        sc_grid.setContentsMargins(0, 2, 0, 0)
        sc_grid.setSpacing(8)
        for idx, (s_key, s_title, dot_hex) in enumerate(SCENES_META):
            btn = QPushButton(s_title)
            btn.setObjectName("SceneChip")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(38)
            btn.setProperty("dot_color", dot_hex)
            btn.setProperty("base_title", s_title)
            btn.clicked.connect(lambda checked=False, k=s_key: self._select_scene(k))
            sc_grid.addWidget(btn, idx // 3, idx % 3)
            self.scene_buttons[s_key] = btn
        mc_lay.addWidget(self.scenes_box)

        self.picker_box = PhotoshopColorPicker(self.cfg.current().get("static_color", [255, 165, 130]))
        self.picker_box.colorChanged.connect(self._on_picker_color_changed)
        mc_lay.addWidget(self.picker_box)

        p1.addWidget(mode_card)

        # Картка профілів
        prof_card = QFrame()
        prof_card.setObjectName("Card")
        pr_lay = QHBoxLayout(prof_card)
        pr_lay.setContentsMargins(14, 12, 14, 12)
        pr_lay.setSpacing(8)

        self.combo_profile = QComboBox()
        self.combo_profile.setObjectName("ProfileCombo")
        self.combo_profile.setFixedHeight(40)
        self.combo_profile.addItems(list(self.cfg.data["profiles"].keys()))
        self.combo_profile.currentTextChanged.connect(self._on_profile_selected)
        pr_lay.addWidget(self.combo_profile, stretch=1)

        self.btn_add_prof = QPushButton("＋")
        self.btn_add_prof.setObjectName("ProfileSquareBtn")
        self.btn_add_prof.setCursor(Qt.PointingHandCursor)
        self.btn_add_prof.setToolTip("Створити новий профіль")
        self.btn_add_prof.setFixedSize(40, 40)
        self.btn_add_prof.clicked.connect(self._create_profile)
        pr_lay.addWidget(self.btn_add_prof)

        self.btn_reset_prof = QPushButton("↻")
        self.btn_reset_prof.setObjectName("ProfileSquareBtn")
        self.btn_reset_prof.setCursor(Qt.PointingHandCursor)
        self.btn_reset_prof.setToolTip("Скинути профіль до базових налаштувань")
        self.btn_reset_prof.setFixedSize(40, 40)
        self.btn_reset_prof.clicked.connect(self._reset_profile)
        pr_lay.addWidget(self.btn_reset_prof)

        self.btn_del_prof = QPushButton("✕")
        self.btn_del_prof.setObjectName("ProfileDangerSquareBtn")
        self.btn_del_prof.setCursor(Qt.PointingHandCursor)
        self.btn_del_prof.setToolTip("Видалити власний профіль")
        self.btn_del_prof.setFixedSize(40, 40)
        self.btn_del_prof.clicked.connect(self._delete_profile)
        pr_lay.addWidget(self.btn_del_prof)

        p1.addWidget(prof_card)

        sec_base = CollapsibleSection("Яскравість та динаміка", expanded=True)
        self._add_slider(sec_base.body_lay, "brightness", "Яскравість", 10, 100, 100.0, "{:.0%}")
        self._add_slider(sec_base.body_lay, "anim_speed", "Швидкість анімації", 20, 250, 100.0, "{:.1f}x")
        self._add_slider(sec_base.body_lay, "smoothing", "Плавність переходів", 5, 85, 100.0, "{:.2f}")
        p1.addWidget(sec_base)

        sec_cal = CollapsibleSection("Калібрування зображення та сцен", expanded=False)
        self._add_slider(sec_cal.body_lay, "saturation", "Насиченість кольорів", 80, 160, 100.0, "{:.2f}")
        self._add_slider(sec_cal.body_lay, "fire_boost", "Акцент полум'я / спалахів", 10, 100, 10.0, "{:.1f}")
        self._add_slider(sec_cal.body_lay, "min_dim", "Мінімальна яскравість у темряві", 5, 70, 100.0, "{:.0%}")
        self._add_slider(sec_cal.body_lay, "fps", "Частота кадрів захоплення", 20, 60, 1.0, "{:.0f} FPS")

        dim_row = QHBoxLayout()
        lbl_dim = QLabel("Адаптивний димінг темних сцен")
        lbl_dim.setObjectName("RowLabel")
        dim_row.addWidget(lbl_dim, stretch=1)
        self.dim_switch = SmoothToggle(checked=True)
        self.dim_switch.toggled.connect(self._on_dimming_toggled)
        dim_row.addWidget(self.dim_switch)
        sec_cal.body_lay.addLayout(dim_row)
        p1.addWidget(sec_cal)

        sec_rgb = CollapsibleSection("Баланс кольору (RGB)", expanded=False)
        self._add_slider(sec_rgb.body_lay, "gain_r", "Червоний канал (R)", 50, 100, 100.0, "{:.2f}")
        self._add_slider(sec_rgb.body_lay, "gain_g", "Зелений канал (G)", 50, 100, 100.0, "{:.2f}")
        self._add_slider(sec_rgb.body_lay, "gain_b", "Синій канал (B)", 40, 100, 100.0, "{:.2f}")
        p1.addWidget(sec_rgb)

        p1.addStretch(1)

        # === СТОРІНКА 2: ІГРИ ТА ВИНЯТКИ ===
        page_rules = QWidget()
        pr = QVBoxLayout(page_rules)
        pr.setContentsMargins(0, 0, 0, 0)
        pr.setSpacing(14)

        r_top_card = QFrame()
        r_top_card.setObjectName("Card")
        rt_lay = QVBoxLayout(r_top_card)
        rt_lay.setContentsMargins(16, 14, 16, 14)
        rt_lay.setSpacing(10)

        self.lbl_fg_status = QLabel("Активне вікно: виявлення...")
        self.lbl_fg_status.setObjectName("ValueLabel")
        rt_lay.addWidget(self.lbl_fg_status)

        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)
        self.combo_rules = QComboBox()
        self.combo_rules.setObjectName("ProfileCombo")
        self.combo_rules.setFixedHeight(40)
        self.combo_rules.currentTextChanged.connect(self._on_rule_selected)
        sel_row.addWidget(self.combo_rules, stretch=1)

        btn_add_rule = QPushButton("+ Додати гру")
        btn_add_rule.setObjectName("IconActionBtn")
        btn_add_rule.setCursor(Qt.PointingHandCursor)
        btn_add_rule.setFixedHeight(40)
        btn_add_rule.setFixedWidth(116)
        btn_add_rule.clicked.connect(self._add_app_rule_dialog)
        sel_row.addWidget(btn_add_rule)

        btn_del_rule = QPushButton("✕")
        btn_del_rule.setObjectName("ProfileDangerSquareBtn")
        btn_del_rule.setCursor(Qt.PointingHandCursor)
        btn_del_rule.setFixedSize(40, 40)
        btn_del_rule.clicked.connect(self._delete_app_rule)
        sel_row.addWidget(btn_del_rule)

        rt_lay.addLayout(sel_row)
        pr.addWidget(r_top_card)

        self.rule_editor_card = QFrame()
        self.rule_editor_card.setObjectName("Card")
        re_lay = QVBoxLayout(self.rule_editor_card)
        re_lay.setContentsMargins(18, 16, 18, 16)
        re_lay.setSpacing(14)

        r_en_row = QHBoxLayout()
        lbl_r_en = QLabel("Активувати правила для гри")
        lbl_r_en.setObjectName("RowLabel")
        lbl_r_en.setWordWrap(True)
        r_en_row.addWidget(lbl_r_en, stretch=1)
        self.rule_enabled_switch = SmoothToggle(checked=True)
        self.rule_enabled_switch.toggled.connect(self._on_rule_fields_changed)
        r_en_row.addWidget(self.rule_enabled_switch)
        re_lay.addLayout(r_en_row)

        r_prof_row = QHBoxLayout()
        r_prof_row.setSpacing(10)
        lbl_rp = QLabel("Автопрофіль")
        lbl_rp.setObjectName("RowLabel")
        r_prof_row.addWidget(lbl_rp)
        self.combo_rule_profile = QComboBox()
        self.combo_rule_profile.setObjectName("ProfileCombo")
        self.combo_rule_profile.setFixedHeight(38)
        self.combo_rule_profile.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.combo_rule_profile.setMinimumWidth(160)
        self.combo_rule_profile.currentTextChanged.connect(self._on_rule_fields_changed)
        r_prof_row.addWidget(self.combo_rule_profile, stretch=1)
        re_lay.addLayout(r_prof_row)

        r_act_row = QHBoxLayout()
        r_act_row.setSpacing(10)
        lbl_ra = QLabel("Зона HUD")
        lbl_ra.setObjectName("RowLabel")
        r_act_row.addWidget(lbl_ra)
        self.combo_hud_action = QComboBox()
        self.combo_hud_action.setObjectName("ProfileCombo")
        self.combo_hud_action.setFixedHeight(38)
        self.combo_hud_action.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.combo_hud_action.addItem("Замінити фоном", "neighbor_fill")
        self.combo_hud_action.addItem("Приглушити зону", "dim_zone")
        self.combo_hud_action.currentIndexChanged.connect(self._on_rule_fields_changed)
        r_act_row.addWidget(self.combo_hud_action, stretch=1)
        re_lay.addLayout(r_act_row)

        lbl_viz = QLabel("Намалюйте зону мишкою на схемі екрана (ПКМ — видалити):")
        lbl_viz.setObjectName("AppSub")
        lbl_viz.setWordWrap(True)
        re_lay.addWidget(lbl_viz)

        self.hud_viz = InteractiveHudCanvas()
        self.hud_viz.zoneDrawn.connect(self._on_canvas_zone_drawn)
        self.hud_viz.zoneRemoved.connect(self._remove_hud_zone)
        re_lay.addWidget(self.hud_viz)

        add_z_row = QHBoxLayout()
        add_z_row.setSpacing(8)
        self.combo_hud_preset = QComboBox()
        self.combo_hud_preset.setObjectName("ProfileCombo")
        self.combo_hud_preset.setFixedHeight(38)
        for p_key, (p_title, _) in HUD_PRESETS.items():
            self.combo_hud_preset.addItem(p_title, p_key)
        add_z_row.addWidget(self.combo_hud_preset, stretch=1)

        btn_add_zone = QPushButton("+ Шаблон")
        btn_add_zone.setObjectName("IconActionBtn")
        btn_add_zone.setCursor(Qt.PointingHandCursor)
        btn_add_zone.setFixedSize(102, 38)
        btn_add_zone.clicked.connect(self._add_hud_zone_to_rule)
        add_z_row.addWidget(btn_add_zone)
        re_lay.addLayout(add_z_row)

        self.zones_list_lay = QVBoxLayout()
        self.zones_list_lay.setSpacing(6)
        re_lay.addLayout(self.zones_list_lay)

        pr.addWidget(self.rule_editor_card)
        pr.addStretch(1)

        # === СТОРІНКА 3: НАЛАШТУВАННЯ ===
        page_set = QWidget()
        p2 = QVBoxLayout(page_set)
        p2.setContentsMargins(0, 0, 0, 0)
        p2.setSpacing(14)

        sys_card = QFrame()
        sys_card.setObjectName("Card")
        sys_lay = QVBoxLayout(sys_card)
        sys_lay.setContentsMargins(18, 16, 18, 16)
        sys_lay.setSpacing(14)

        r_theme = QHBoxLayout()
        lbl_theme = QLabel("Темна тема інтерфейсу")
        lbl_theme.setObjectName("RowLabel")
        r_theme.addWidget(lbl_theme, stretch=1)
        self.theme_switch = SmoothToggle(checked=(self.theme_name == "dark"))
        self.theme_switch.toggled.connect(self._on_theme_toggled)
        r_theme.addWidget(self.theme_switch)
        sys_lay.addLayout(r_theme)

        r_auto = QHBoxLayout()
        lbl_auto = QLabel("Автозапуск разом із Windows")
        lbl_auto.setObjectName("RowLabel")
        r_auto.addWidget(lbl_auto, stretch=1)
        self.auto_switch = SmoothToggle(checked=bool(self.cfg.data.get("autostart", True)))
        self.auto_switch.toggled.connect(self._on_autostart_toggled)
        r_auto.addWidget(self.auto_switch)
        sys_lay.addLayout(r_auto)

        r_tray_auto = QHBoxLayout()
        lbl_tray_auto = QLabel("Запускати згорнутим у трей")
        lbl_tray_auto.setObjectName("RowLabel")
        r_tray_auto.addWidget(lbl_tray_auto, stretch=1)
        self.tray_auto_switch = SmoothToggle(checked=bool(self.cfg.data.get("start_in_tray", True)))
        self.tray_auto_switch.toggled.connect(self._on_start_tray_toggled)
        r_tray_auto.addWidget(self.tray_auto_switch)
        sys_lay.addLayout(r_tray_auto)

        p2.addWidget(sys_card)

        rep_card = QFrame()
        rep_card.setObjectName("Card")
        rep_lay = QVBoxLayout(rep_card)
        rep_lay.setContentsMargins(18, 16, 18, 16)
        rep_lay.setSpacing(12)

        r_rep = QHBoxLayout()
        lbl_rep = QLabel("Повторювач на неонову / WLED стрічку")
        lbl_rep.setObjectName("RowLabel")
        r_rep.addWidget(lbl_rep, stretch=1)
        self.rep_switch = SmoothToggle(checked=bool(self.cfg.data.get("repeater_enabled", False)))
        self.rep_switch.toggled.connect(self._on_repeater_changed)
        r_rep.addWidget(self.rep_switch)
        rep_lay.addLayout(r_rep)

        r_ip = QHBoxLayout()
        r_ip.setSpacing(8)
        self.edit_wled_ip = QLineEdit()
        self.edit_wled_ip.setObjectName("HexInput")
        self.edit_wled_ip.setPlaceholderText("IP контролера WLED (напр. 192.168.1.120)")
        self.edit_wled_ip.setFixedHeight(36)
        self.edit_wled_ip.setText(self.cfg.data.get("repeater_wled_ip", ""))
        self.edit_wled_ip.editingFinished.connect(self._on_repeater_changed)
        r_ip.addWidget(self.edit_wled_ip, stretch=1)

        self.combo_rep_order = QComboBox()
        self.combo_rep_order.setObjectName("ProfileCombo")
        self.combo_rep_order.setFixedHeight(36)
        self.combo_rep_order.addItems(["RGB", "GRB", "BRG"])
        self.combo_rep_order.setCurrentText(self.cfg.data.get("repeater_color_order", "RGB"))
        self.combo_rep_order.currentTextChanged.connect(self._on_repeater_changed)
        r_ip.addWidget(self.combo_rep_order)
        rep_lay.addLayout(r_ip)

        self.lbl_diag = QLabel("")
        self.lbl_diag.setObjectName("AppSub")
        self.lbl_diag.setWordWrap(True)
        rep_lay.addWidget(self.lbl_diag)

        p2.addWidget(rep_card)

        act_card = QFrame()
        act_card.setObjectName("Card")
        act_lay = QVBoxLayout(act_card)
        act_lay.setContentsMargins(18, 16, 18, 16)
        act_lay.setSpacing(10)

        self.btn_open_log = QPushButton("Відкрити файл логів")
        self.btn_open_log.setObjectName("TonalBtn")
        self.btn_open_log.setCursor(Qt.PointingHandCursor)
        self.btn_open_log.setFixedHeight(44)
        self.btn_open_log.clicked.connect(lambda: os.startfile(LOG_PATH) if os.path.exists(LOG_PATH) else None)
        act_lay.addWidget(self.btn_open_log)

        self.btn_hide = QPushButton("Згорнути в трей")
        self.btn_hide.setObjectName("TonalBtn")
        self.btn_hide.setCursor(Qt.PointingHandCursor)
        self.btn_hide.setFixedHeight(44)
        self.btn_hide.clicked.connect(self.hide)
        act_lay.addWidget(self.btn_hide)

        self.btn_quit = QPushButton("Вийти")
        self.btn_quit.setObjectName("DangerBtn")
        self.btn_quit.setCursor(Qt.PointingHandCursor)
        self.btn_quit.setFixedHeight(44)
        self.btn_quit.clicked.connect(self._do_quit)
        act_lay.addWidget(self.btn_quit)

        p2.addWidget(act_card)
        p2.addStretch(1)

        self.pages.addWidget(page_ctrl)
        self.pages.addWidget(page_rules)
        self.pages.addWidget(page_set)

        # === ПЛАВАЮЧИЙ OVERLAY DRAWER ПРИСТРОЇВ ===
        self.drawer_backdrop = DrawerBackdropOverlay(root_widget)
        self.drawer_backdrop.setObjectName("DrawerBackdrop")
        self.drawer_backdrop.setVisible(False)
        self.drawer_backdrop.clicked.connect(lambda: self._set_drawer_open(False))

        self.device_drawer = QFrame(root_widget)
        self.device_drawer.setObjectName("DeviceDrawer")
        self.device_drawer.setVisible(False)

        dr_lay = QVBoxLayout(self.device_drawer)
        dr_lay.setContentsMargins(18, 20, 18, 20)
        dr_lay.setSpacing(12)

        dr_top = QHBoxLayout()
        lbl_dr = QLabel("Пристрої")
        lbl_dr.setObjectName("DrawerTitle")
        dr_top.addWidget(lbl_dr)
        dr_top.addStretch(1)

        btn_close_dr = QPushButton("✕")
        btn_close_dr.setObjectName("DrawerCloseBtn")
        btn_close_dr.setCursor(Qt.PointingHandCursor)
        btn_close_dr.setFixedSize(32, 32)
        btn_close_dr.clicked.connect(lambda: self._set_drawer_open(False))
        dr_top.addWidget(btn_close_dr)
        dr_lay.addLayout(dr_top)

        lbl_dr_hint = QLabel("Оберіть активну стрічку відображення:")
        lbl_dr_hint.setObjectName("AppSub")
        lbl_dr_hint.setWordWrap(True)
        dr_lay.addWidget(lbl_dr_hint)

        for dev in DEVICES_META:
            card = QPushButton()
            card.setObjectName("DeviceItemBtn")
            card.setCursor(Qt.PointingHandCursor)
            card.setFixedHeight(72)
            card.setText(f"{dev['title']}\n{dev['subtitle']}")
            card.clicked.connect(lambda checked=False, d_id=dev["id"]: self._select_device(d_id))
            dr_lay.addWidget(card)
            self.device_cards[dev["id"]] = card

        dr_lay.addStretch(1)

        lbl_foot_dr = QLabel("Виберіть пристрій, яким зараз керує програма.")
        lbl_foot_dr.setObjectName("AppSub")
        lbl_foot_dr.setWordWrap(True)
        dr_lay.addWidget(lbl_foot_dr)

        self._switch_page(0, "control")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_overlay_drawer()

    def _layout_overlay_drawer(self):
        cw = self.centralWidget().width()
        ch = self.centralWidget().height()
        drawer_w = 270
        self.drawer_backdrop.setGeometry(0, 0, cw, ch)
        self.device_drawer.setGeometry(0, 0, drawer_w, ch)

    def _set_drawer_open(self, is_open: bool):
        self._drawer_open = is_open
        self._layout_overlay_drawer()
        self.drawer_backdrop.setVisible(is_open)
        self.device_drawer.setVisible(is_open)
        if is_open:
            self.drawer_backdrop.raise_()
            self.device_drawer.raise_()

    def _select_device(self, dev_id: str):
        self.cfg.data["active_device"] = dev_id
        self.cfg.save()
        self._sync_device_and_shape()
        self._set_drawer_open(False)

    def _select_strip_shape(self, shape_id: str):
        self.cfg.data["strip_shape"] = shape_id
        self.cfg.save()
        self.engine.force_resend = True
        self._sync_device_and_shape()

    def _sync_device_and_shape(self):
        cur_dev = self.cfg.data.get("active_device", "monitor_qube")
        cur_shape = self.cfg.data.get("strip_shape", "triangle")
        self.led_preview.set_geometry_mode(cur_dev, cur_shape)
        self.shape_bar.setVisible(cur_dev == "monitor_qube")

        shape_title = next((name for sid, name in STRIP_SHAPES if sid == cur_shape), "Трикутник (V)")
        for d in DEVICES_META:
            if d["id"] == cur_dev:
                if cur_dev == "monitor_qube":
                    self.lbl_sub.setText(f"{d['title']} • {shape_title}")
                else:
                    self.lbl_sub.setText(f"{d['title']} • {d['subtitle']}")
            btn = self.device_cards.get(d["id"])
            if btn:
                btn.setProperty("active", d["id"] == cur_dev)
                btn.style().unpolish(btn)
                btn.style().polish(btn)

        for sid, sbtn in self.shape_buttons.items():
            sbtn.setProperty("active", sid == cur_shape)
            sbtn.style().unpolish(sbtn)
            sbtn.style().polish(sbtn)

    # === ЛОГІКА ВКЛАДКИ "ІГРИ ТА ВИНЯТКИ" ===

    def _refresh_rules_combo(self):
        rules = self.cfg.data.get("app_rules", {})
        cur = self.combo_rules.currentText()
        self.combo_rules.blockSignals(True)
        self.combo_rules.clear()
        for exe_name in rules.keys():
            self.combo_rules.addItem(exe_name)
        if cur in rules:
            self.combo_rules.setCurrentText(cur)
        self.combo_rules.blockSignals(False)
        self._load_selected_rule_to_ui()

    def _on_rule_selected(self, _txt):
        self._load_selected_rule_to_ui()

    def _load_selected_rule_to_ui(self):
        exe = self.combo_rules.currentText()
        rules = self.cfg.data.get("app_rules", {})
        if not exe or exe not in rules:
            self.rule_editor_card.setVisible(False)
            return

        self.rule_editor_card.setVisible(True)
        rule = rules[exe]

        self.rule_enabled_switch.setChecked(bool(rule.get("enabled", True)))

        self.combo_rule_profile.blockSignals(True)
        self.combo_rule_profile.clear()
        self.combo_rule_profile.addItems(list(self.cfg.data["profiles"].keys()))
        prof_target = rule.get("profile", "Ігри")
        if prof_target in self.cfg.data["profiles"]:
            self.combo_rule_profile.setCurrentText(prof_target)
        self.combo_rule_profile.blockSignals(False)

        self.combo_hud_action.blockSignals(True)
        act = rule.get("hud_action", "neighbor_fill")
        idx = self.combo_hud_action.findData(act)
        if idx >= 0:
            self.combo_hud_action.setCurrentIndex(idx)
        self.combo_hud_action.blockSignals(False)

        zones = rule.get("zones", [])
        self.hud_viz.set_zones(zones)

        while self.zones_list_lay.count():
            item = self.zones_list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for z_idx, z in enumerate(zones):
            row_f = QFrame()
            row_f.setObjectName("ZoneChipRow")
            rl = QHBoxLayout(row_f)
            rl.setContentsMargins(12, 6, 8, 6)
            r = z.get("rect", [0, 0, 0, 0])
            lbl = QLabel(f"{z.get('label', 'Зона')}  ({int(r[0]*100)}%, {int(r[1]*100)}% → {int(r[2]*100)}%, {int(r[3]*100)}%)")
            lbl.setObjectName("RowLabel")
            lbl.setWordWrap(True)
            rl.addWidget(lbl, stretch=1)

            btn_rm = QPushButton("✕")
            btn_rm.setObjectName("DangerIconBtn")
            btn_rm.setCursor(Qt.PointingHandCursor)
            btn_rm.setFixedSize(28, 28)
            btn_rm.clicked.connect(lambda checked=False, i=z_idx: self._remove_hud_zone(i))
            rl.addWidget(btn_rm)

            self.zones_list_lay.addWidget(row_f)

    def _on_rule_fields_changed(self, *_args):
        exe = self.combo_rules.currentText()
        rules = self.cfg.data.get("app_rules", {})
        if exe not in rules:
            return
        rule = rules[exe]
        rule["enabled"] = bool(self.rule_enabled_switch.isChecked())
        rule["profile"] = self.combo_rule_profile.currentText()
        rule["hud_action"] = self.combo_hud_action.currentData()
        self.cfg.save()

    def _on_canvas_zone_drawn(self, rect):
        exe = self.combo_rules.currentText()
        rules = self.cfg.data.get("app_rules", {})
        if exe not in rules:
            return
        rules[exe].setdefault("zones", []).append({
            "label": "Власна зона",
            "rect": rect
        })
        self.cfg.save()
        self._load_selected_rule_to_ui()

    def _add_hud_zone_to_rule(self):
        exe = self.combo_rules.currentText()
        rules = self.cfg.data.get("app_rules", {})
        if exe not in rules:
            return
        preset_key = self.combo_hud_preset.currentData()
        if preset_key in HUD_PRESETS:
            title, rect = HUD_PRESETS[preset_key]
            rules[exe].setdefault("zones", []).append({
                "label": title,
                "rect": list(rect)
            })
            self.cfg.save()
            self._load_selected_rule_to_ui()

    def _remove_hud_zone(self, z_idx: int):
        exe = self.combo_rules.currentText()
        rules = self.cfg.data.get("app_rules", {})
        if exe in rules and 0 <= z_idx < len(rules[exe].get("zones", [])):
            rules[exe]["zones"].pop(z_idx)
            self.cfg.save()
            self._load_selected_rule_to_ui()

    def _add_app_rule_dialog(self):
        procs = list_visible_processes()
        if procs:
            exe, ok = QInputDialog.getItem(
                self, "Додати гру або програму",
                "Оберіть запущений процес або введіть назву .exe:",
                procs, 0, True
            )
        else:
            exe, ok = QInputDialog.getText(
                self, "Додати гру або програму",
                "Введіть назву файлу процесу (наприклад, Witcher3.exe):"
            )
        if ok and exe and exe.strip():
            exe = exe.strip()
            if not exe.lower().endswith(".exe"):
                exe += ".exe"
            self.cfg.data.setdefault("app_rules", {})[exe] = {
                "enabled": True,
                "display_name": exe,
                "profile": "Ігри",
                "hud_action": "neighbor_fill",
                "fire_boost_override": 3.0,
                "zones": [
                    {"label": "Лівий верхній HUD (HP/MP)", "rect": [0.00, 0.00, 0.30, 0.19]}
                ]
            }
            self.cfg.save()
            self._refresh_rules_combo()
        self._refresh_diag_label()
        self.combo_rules.setCurrentText(exe)

    def _delete_app_rule(self):
        exe = self.combo_rules.currentText()
        rules = self.cfg.data.get("app_rules", {})
        if exe in rules:
            del rules[exe]
            self.cfg.save()
            self._refresh_rules_combo()
        self._refresh_diag_label()

    # === ЗАГАЛЬНІ МЕТОДИ ===

    def _add_slider(self, parent_layout, key, title, min_i, max_i, scale, fmt):
        box = QVBoxLayout()
        box.setSpacing(2)

        top = QHBoxLayout()
        lbl_t = QLabel(title)
        lbl_t.setObjectName("RowLabel")
        lbl_v = QLabel("")
        lbl_v.setObjectName("ValueLabel")
        top.addWidget(lbl_t)
        top.addStretch(1)
        top.addWidget(lbl_v)
        box.addLayout(top)

        slider = MaterialSlider(min_i, max_i)
        slider.valueChanged.connect(lambda val, k=key: self._on_slider_changed(k, val))
        box.addWidget(slider)

        parent_layout.addLayout(box)
        self.sliders[key] = (slider, lbl_v, scale, fmt)

    def _switch_page(self, idx, key):
        self.pages.setCurrentIndex(idx)
        for k, btn in self.nav_buttons.items():
            btn.setProperty("active", k == key)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _apply_stylesheet(self):
        p = self.pal
        apply_dwm_window_theme(int(self.winId()), self.theme_name, p["bg_window"])

        self.led_preview.set_off_color(p["led_off"])
        self.hud_viz.set_palette(p["surface_high"], p["border_subtle"], p["primary"])
        for sw in (self.power_switch, self.theme_switch, self.dim_switch, self.auto_switch, self.tray_auto_switch, self.rule_enabled_switch, self.rep_switch):
            sw.set_palette_colors(p["primary"], p["on_primary"], p["switch_off"], p["text_muted"])

        for slider, _, _, _ in self.sliders.values():
            slider.set_palette_colors(p["surface_high"], p["primary"], p["surface"])

        qss = f"""
        QWidget {{
            font-family: "Google Sans", "Segoe UI Variable Display", "Segoe UI", sans-serif;
            color: {p["text_main"]};
        }}
        QWidget#RootBg, QWidget#ScrollCanvas, QScrollArea {{
            background-color: {p["bg_window"]};
            border: none;
        }}
        QWidget#DrawerBackdrop {{
            background-color: rgba(0, 0, 0, 145);
        }}
        QFrame#DeviceDrawer {{
            background-color: {p["drawer_bg"]};
            border-right: 1px solid {p["border_subtle"]};
            border-top-right-radius: 26px;
            border-bottom-right-radius: 26px;
        }}
        QLabel#DrawerTitle {{
            font-size: 18px;
            font-weight: 700;
            color: {p["text_main"]};
        }}
        QPushButton#DrawerOpenBtn, QPushButton#DrawerCloseBtn {{
            background-color: {p["surface"]};
            color: {p["text_main"]};
            border-radius: 21px;
            border: 1px solid {p["border_subtle"]};
            font-size: 17px;
            font-weight: 700;
        }}
        QPushButton#DrawerCloseBtn {{
            border-radius: 16px;
            font-size: 14px;
        }}
        QPushButton#DrawerOpenBtn:hover, QPushButton#DrawerCloseBtn:hover {{
            background-color: {p["surface_hover"]};
        }}
        QPushButton#DeviceItemBtn {{
            background-color: {p["surface"]};
            color: {p["text_main"]};
            border-radius: 18px;
            border: 1px solid {p["border_subtle"]};
            text-align: left;
            padding: 10px 14px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton#DeviceItemBtn:hover {{
            background-color: {p["surface_hover"]};
        }}
        QPushButton#DeviceItemBtn[active="true"] {{
            background-color: {p["primary_container"]};
            color: {p["on_primary_container"]};
            border: 1.5px solid {p["primary"]};
            font-weight: 700;
        }}
        QPushButton#ShapePillBtn {{
            background-color: {p["surface_high"]};
            color: {p["text_muted"]};
            border-radius: 14px;
            border: 1px solid transparent;
            padding: 0 12px;
            font-size: 11px;
            font-weight: 700;
        }}
        QPushButton#ShapePillBtn:hover {{
            background-color: {p["surface_hover"]};
            color: {p["text_main"]};
        }}
        QPushButton#ShapePillBtn[active="true"] {{
            background-color: {p["primary_container"]};
            color: {p["on_primary_container"]};
            border: 1px solid {p["primary"]};
        }}
        QLabel#AppTitle {{
            font-size: 21px;
            font-weight: 700;
            color: {p["text_main"]};
        }}
        QLabel#AppSub {{
            font-size: 12px;
            color: {p["text_muted"]};
        }}
        QLabel#RowLabel {{
            font-size: 13px;
            font-weight: 500;
            color: {p["text_main"]};
        }}
        QLabel#ValueLabel {{
            font-size: 13px;
            font-weight: 700;
            color: {p["primary"]};
        }}
        QFrame#Card, QFrame#NavPillContainer {{
            background-color: {p["surface"]};
            border-radius: 24px;
            border: 1px solid {p["border_subtle"]};
        }}
        QFrame#ZoneChipRow {{
            background-color: {p["surface_high"]};
            border-radius: 14px;
        }}
        QPushButton#SectionHeaderBtn {{
            background-color: transparent;
            color: {p["text_main"]};
            border: none;
            text-align: left;
            font-size: 14px;
            font-weight: 700;
            padding: 0 2px;
        }}
        QPushButton#SectionHeaderBtn:hover {{
            color: {p["primary"]};
        }}
        QPushButton#NavTab {{
            background-color: transparent;
            color: {p["text_muted"]};
            border-radius: 18px;
            font-size: 13px;
            font-weight: 700;
            border: none;
        }}
        QPushButton#NavTab:hover {{
            background-color: {p["surface_hover"]};
            color: {p["text_main"]};
        }}
        QPushButton#NavTab[active="true"] {{
            background-color: {p["primary_container"]};
            color: {p["on_primary_container"]};
        }}
        QPushButton#ModeSegment {{
            background-color: {p["surface_high"]};
            color: {p["text_muted"]};
            border-radius: 20px;
            font-size: 13px;
            font-weight: 700;
            border: none;
        }}
        QPushButton#ModeSegment:hover {{
            background-color: {p["surface_hover"]};
            color: {p["text_main"]};
        }}
        QPushButton#ModeSegment[active="true"] {{
            background-color: {p["primary"]};
            color: {p["on_primary"]};
        }}
        QPushButton#SceneChip {{
            background-color: {p["surface_high"]};
            color: {p["text_main"]};
            border-radius: 19px;
            font-size: 12px;
            font-weight: 600;
            border: 1px solid transparent;
            padding: 0 10px;
        }}
        QPushButton#SceneChip:hover {{
            background-color: {p["surface_hover"]};
        }}
        QPushButton#SceneChip[active="true"] {{
            background-color: {p["primary_container"]};
            color: {p["on_primary_container"]};
            border: 1.5px solid {p["primary"]};
            font-weight: 700;
        }}
        QComboBox#ProfileCombo {{
            background-color: {p["surface_high"]};
            color: {p["text_main"]};
            border-radius: 19px;
            padding: 0 14px;
            font-size: 13px;
            font-weight: 600;
            border: none;
        }}
        QComboBox#ProfileCombo:hover {{
            background-color: {p["surface_hover"]};
        }}
        QComboBox#ProfileCombo::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {p["surface"]};
            color: {p["text_main"]};
            selection-background-color: {p["primary_container"]};
            selection-color: {p["on_primary_container"]};
            border-radius: 14px;
            padding: 6px;
            outline: none;
        }}
        QLineEdit#HexInput {{
            background-color: {p["surface_high"]};
            color: {p["text_main"]};
            border-radius: 14px;
            font-size: 13px;
            font-weight: 700;
            border: 1px solid {p["border_subtle"]};
        }}
        QPushButton#ProfileSquareBtn {{
            background-color: {p["primary_container"]};
            color: {p["on_primary_container"]};
            border-radius: 19px;
            font-size: 20px;
            font-weight: 700;
            padding: 0px;
            border: none;
        }}
        QPushButton#ProfileSquareBtn:hover {{
            background-color: {p["surface_hover"]};
        }}
        QPushButton#ProfileDangerSquareBtn {{
            background-color: {p["danger_bg"]};
            color: {p["danger_fg"]};
            border-radius: 19px;
            font-size: 18px;
            font-weight: 700;
            padding: 0px;
            border: none;
        }}
        QPushButton#ProfileDangerSquareBtn:hover {{
            background-color: {p["danger_hover"]};
        }}
        QPushButton#ProfileDangerSquareBtn:disabled {{
            background-color: {p["surface_high"]};
            color: {p["text_muted"]};
            opacity: 0.45;
        }}
        QPushButton#IconActionBtn, QPushButton#TonalBtn {{
            background-color: {p["primary_container"]};
            color: {p["on_primary_container"]};
            border-radius: 19px;
            font-size: 13px;
            font-weight: 700;
            border: none;
        }}
        QPushButton#IconActionBtn:hover, QPushButton#TonalBtn:hover {{
            background-color: {p["surface_hover"]};
        }}
        QPushButton#DangerIconBtn, QPushButton#DangerBtn {{
            background-color: {p["danger_bg"]};
            color: {p["danger_fg"]};
            border-radius: 19px;
            font-size: 14px;
            font-weight: 700;
            border: none;
        }}
        QPushButton#DangerIconBtn:hover, QPushButton#DangerBtn:hover {{
            background-color: {p["danger_hover"]};
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 6px;
            margin: 8px 2px 8px 0;
        }}
        QScrollBar::handle:vertical {{
            background: {p["surface_hover"]};
            border-radius: 3px;
            min-height: 28px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        """
        self.setStyleSheet(qss)
        self._refresh_mode_visuals()

    def _refresh_mode_visuals(self):
        cur_mode = self.cfg.current().get("mode", "ambilight")
        active_group = "scenes" if cur_mode.startswith("hue_") else cur_mode

        for m_key, btn in self.mode_buttons.items():
            btn.setProperty("active", m_key == active_group)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self.scenes_box.setVisible(active_group == "scenes")
        self.picker_box.setVisible(active_group == "static")

        if active_group == "scenes":
            for s_key, btn in self.scene_buttons.items():
                is_sel = (s_key == cur_mode)
                base_title = btn.property("base_title")
                btn.setText(f"✓  {base_title}" if is_sel else f"●  {base_title}")
                btn.setProperty("active", is_sel)
                btn.style().unpolish(btn)
                btn.style().polish(btn)

    def _select_mode_group(self, group_key):
        prof = self.cfg.current()
        if group_key == "scenes":
            if not prof.get("mode", "").startswith("hue_"):
                prof["mode"] = "hue_candle"
        else:
            prof["mode"] = group_key
        self.engine.force_resend = True
        self.cfg.save()
        self._refresh_mode_visuals()

    def _select_scene(self, scene_key):
        prof = self.cfg.current()
        prof["mode"] = scene_key
        self.engine.force_resend = True
        self.cfg.save()
        self._refresh_mode_visuals()

    def _on_picker_color_changed(self, rgb):
        prof = self.cfg.current()
        prof["static_color"] = rgb
        prof["mode"] = "static"
        self.engine.force_resend = True
        self.cfg.save()

    def _update_profile_action_buttons(self):
        cur_name = self.cfg.data.get("active_profile", "")
        is_protected = cur_name in PROTECTED_PROFILES
        self.btn_del_prof.setEnabled(not is_protected)
        if is_protected:
            self.btn_del_prof.setToolTip(f"Стандартний профіль «{cur_name}» не можна видалити")
        else:
            self.btn_del_prof.setToolTip(f"Видалити профіль «{cur_name}»")

    def _load_profile_to_ui(self):
        p = self.cfg.current()
        self.combo_profile.blockSignals(True)
        self.combo_profile.setCurrentText(self.cfg.data["active_profile"])
        self.combo_profile.blockSignals(False)

        self._update_profile_action_buttons()
        self.dim_switch.setChecked(bool(p.get("adaptive_dimming", True)))
        self.picker_box.set_rgb(p.get("static_color", [255, 165, 130]))

        for key, (slider, lbl_v, scale, fmt) in self.sliders.items():
            real_val = float(p.get(key, 1.0))
            slider.blockSignals(True)
            slider.setValue(int(round(real_val * scale)))
            slider.blockSignals(False)
            lbl_v.setText(fmt.format(real_val))

        self._refresh_mode_visuals()
        self.engine.force_resend = True

    def _on_slider_changed(self, key, raw_int):
        _, lbl_v, scale, fmt = self.sliders[key]
        real_val = raw_int / scale
        lbl_v.setText(fmt.format(real_val))
        p = self.cfg.current()
        p[key] = int(round(real_val)) if key == "fps" else round(real_val, 3)
        self.engine.force_resend = True
        self.cfg.save()

    def _on_dimming_toggled(self, state):
        p = self.cfg.current()
        p["adaptive_dimming"] = bool(state)
        self.engine.force_resend = True
        self.cfg.save()

    def _on_repeater_changed(self, *_args):
        self.cfg.data["repeater_enabled"] = bool(self.rep_switch.isChecked())
        self.cfg.data["repeater_wled_ip"] = self.edit_wled_ip.text().strip()
        self.cfg.data["repeater_color_order"] = self.combo_rep_order.currentText()
        self.cfg.save()
        self.engine.driver.refresh_topology()
        self._refresh_diag_label()

    def _refresh_diag_label(self):
        d = self.engine.driver.inspect_environment()
        self.lbl_diag.setText(f"Основна: {d['usb_hid_info']}\nПовторювач: {d['wled_info']}")

    def _on_theme_toggled(self, is_dark):
        self.theme_name = "dark" if is_dark else "light"
        self.cfg.data["theme"] = self.theme_name
        self.cfg.save()
        self.pal = build_material_you_palette(self.theme_name)
        self._apply_stylesheet()

    def _on_autostart_toggled(self, enabled):
        self.cfg.data["autostart"] = bool(enabled)
        self.cfg.save()
        threading.Thread(
            target=sync_windows_autostart,
            args=(bool(enabled), bool(self.cfg.data.get("start_in_tray", True))),
            daemon=True
        ).start()

    def _on_start_tray_toggled(self, in_tray):
        self.cfg.data["start_in_tray"] = bool(in_tray)
        self.cfg.save()
        if self.cfg.data.get("autostart", True):
            threading.Thread(
                target=sync_windows_autostart,
                args=(True, bool(in_tray)),
                daemon=True
            ).start()

    def _on_power_switch(self, enabled):
        self.cfg.data["enabled"] = bool(enabled)
        self.cfg.save()

    def _on_profile_selected(self, name):
        if name and name in self.cfg.data["profiles"]:
            self.cfg.data["active_profile"] = name
            self.cfg.save()
            self._load_profile_to_ui()

    def _create_profile(self):
        name, ok = QInputDialog.getText(self, "Новий профіль", "Назва профілю:")
        if ok and name.strip():
            name = name.strip()
            if name in self.cfg.data["profiles"]:
                QMessageBox.warning(self, "Увага", f"Профіль «{name}» вже існує.")
                return
            self.cfg.data["profiles"][name] = json.loads(json.dumps(self.cfg.current()))
            self.cfg.data["active_profile"] = name
            self.combo_profile.blockSignals(True)
            self.combo_profile.clear()
            self.combo_profile.addItems(list(self.cfg.data["profiles"].keys()))
            self.combo_profile.setCurrentText(name)
            self.combo_profile.blockSignals(False)
            self.cfg.save()
            self._update_profile_action_buttons()

    def _reset_profile(self):
        cur = self.combo_profile.currentText()
        if not cur:
            return
        reply = QMessageBox.question(
            self,
            "Скидання профілю",
            f"Скинути всі параметри профілю «{cur}» до базових значень?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        base_template = DEFAULT_PROFILES.get(cur, DEFAULT_PROFILES["Кіно"])
        self.cfg.data["profiles"][cur] = json.loads(json.dumps(base_template))
        self.cfg.save()
        self._load_profile_to_ui()

    def _delete_profile(self):
        cur = self.combo_profile.currentText()
        if cur in PROTECTED_PROFILES:
            QMessageBox.information(
                self,
                "Захищений профіль",
                f"Стандартний профіль «{cur}» не можна видалити. Ви можете скинути його параметри кнопкою «↻»."
            )
            return

        reply = QMessageBox.question(
            self,
            "Видалення профілю",
            f"Ви дійсно бажаєте видалити профіль «{cur}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        del self.cfg.data["profiles"][cur]
        nxt = next(iter(self.cfg.data["profiles"]))
        self.cfg.data["active_profile"] = nxt
        self.combo_profile.blockSignals(True)
        self.combo_profile.clear()
        self.combo_profile.addItems(list(self.cfg.data["profiles"].keys()))
        self.combo_profile.blockSignals(False)
        self.cfg.save()
        self._load_profile_to_ui()

    def _tick_preview(self):
        if not self.isVisible():
            return
        idx = self.pages.currentIndex()
        if idx == 0:
            self.led_preview.update()
        elif idx == 1:
            fg = self.engine.active_fg_exe or "—"
            rule = self.engine.active_rule_name
            if rule:
                self.lbl_fg_status.setText(f"Активне правило: {rule} (HUD маскується)")
            else:
                self.lbl_fg_status.setText(f"Поточне вікно Windows: {fg}")

    def _on_power_toggled_from_tray(self):
        new_st = not self.cfg.data["enabled"]
        self.cfg.data["enabled"] = new_st
        self.power_switch.setChecked(new_st)
        self.cfg.save()

    def _on_profile_from_tray(self, name):
        self.cfg.data["active_profile"] = name
        self.cfg.data["enabled"] = True
        self.power_switch.setChecked(True)
        self.cfg.save()
        self._load_profile_to_ui()

    def _do_show(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        event.ignore()
        self.cfg.data["win_w"] = self.width()
        self.cfg.data["win_h"] = self.height()
        self.cfg.save()
        self.hide()

    def _do_quit(self):
        self.cfg.data["win_w"] = self.width()
        self.cfg.data["win_h"] = self.height()
        self.cfg.save()
        self.engine.running = False
        if hasattr(self, "tray_icon"):
            self.tray_icon.stop()
        QApplication.quit()

