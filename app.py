"""
app.py — UI completa del Mania Inverse Generator (PySide6).
"""

import sys
import os
import subprocess
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QFileDialog,
    QCheckBox, QComboBox, QInputDialog,
    QLineEdit,
)

from beatmap import Beatmap
from inverse import invert_section, auto_detect_sections
from osu_client import fetch_status
from osu_paths import find_songs_folder


# ------------------------------------------------------------------
# Paleta
# ------------------------------------------------------------------

DARK_BG       = "#1a1a1a"
PILL_BG       = "#2b2b2b"
CARD_BG       = "#202020"
TABLE_BG      = "#1e1e1e"
TABLE_HEADER  = "#252525"
ROW_DIVIDER   = "#2a2a2a"
CARD_BORDER   = "rgba(66, 165, 245, 0.5)"
TEXT_PRIMARY  = "#ffffff"
TEXT_MUTED    = "rgba(255, 255, 255, 0.6)"
TEXT_DIM      = "rgba(255, 255, 255, 0.4)"
GREEN         = "#66bb6a"
RED           = "#ef5350"
BLUE_ACCENT   = "#42a5f5"


# ------------------------------------------------------------------
# Configuración
# ------------------------------------------------------------------

GAP_PRESETS = ["1/4", "1/6", "1/8", "1/12", "1/16"]
CUSTOM_LABEL = "custom…"
DEFAULT_GAP_LABEL = "1/4"
DEFAULT_MIN_LN_MS = 30
DEFAULT_DIFF_NAME = "Inverse"

POLL_INTERVAL_MS = 2000  # cada 2 segundos


def parse_gap_label(label):
    if not label.startswith("1/"):
        return None
    try:
        return int(label[2:])
    except ValueError:
        return None


def normalize_path(p):
    """
    Normaliza un path para comparar sin importar / vs \\ y mayúsculas.
    tosu manda paths con /, Python en Windows usa \\, así que comparamos
    pasados por aquí.
    """
    if p is None:
        return None
    return os.path.normcase(os.path.normpath(str(p)))


# ------------------------------------------------------------------
# StatusPill
# ------------------------------------------------------------------

class StatusPill(QWidget):
    def __init__(self, label_text):
        super().__init__()
        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color: {RED}; font-size: 12px;")
        self.label = QLabel(label_text)
        self.label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)
        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        self.setStyleSheet(f"""
            StatusPill {{
                background-color: {PILL_BG};
                border-radius: 10px;
            }}
        """)

    def set_connected(self, is_connected):
        color = GREEN if is_connected else RED
        self.dot.setStyleSheet(f"color: {color}; font-size: 12px;")


# ------------------------------------------------------------------
# BeatmapCard
# ------------------------------------------------------------------

class BeatmapCard(QWidget):
    def __init__(self):
        super().__init__()
        self.title_label = QLabel("No map detected")
        self.title_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 15px; font-weight: 500;"
        )
        self.subtitle_label = QLabel("Open tosu and osu! to enable auto-detection")
        self.subtitle_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px;")
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        text_col.addWidget(self.title_label)
        text_col.addWidget(self.subtitle_label)
        text_col.addWidget(self.stats_label)

        self.load_button = QPushButton("Load this map")
        self.load_button.setEnabled(False)
        self.load_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {BLUE_ACCENT}; color: white; border: none;
                border-radius: 6px; padding: 8px 16px;
                font-size: 13px; font-weight: 500;
            }}
            QPushButton:hover {{ background-color: #5fb1f7; }}
            QPushButton:disabled {{
                background-color: #3a3a3a; color: rgba(255, 255, 255, 0.4);
            }}
        """)

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 14, 16, 14)
        row.addLayout(text_col, stretch=1)
        row.addWidget(self.load_button, alignment=Qt.AlignTop)

        self.setStyleSheet(f"""
            BeatmapCard {{
                background-color: {CARD_BG};
                border: 2px solid {CARD_BORDER};
                border-radius: 10px;
            }}
        """)

    def set_state_message(self, title, subtitle, stats="", load_enabled=False):
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)
        self.stats_label.setText(stats)
        self.load_button.setEnabled(load_enabled)


# ------------------------------------------------------------------
# Dropdown helper
# ------------------------------------------------------------------

def build_gap_dropdown(width=90):
    cb = QComboBox()
    cb.addItems(GAP_PRESETS)
    cb.addItem(CUSTOM_LABEL)
    cb.setCurrentText(DEFAULT_GAP_LABEL)
    cb.setFixedWidth(width)
    cb.setStyleSheet(f"""
        QComboBox {{
            background-color: {PILL_BG}; color: {TEXT_PRIMARY};
            border: 1px solid #3a3a3a; border-radius: 4px;
            padding: 3px 6px; font-size: 12px;
        }}
        QComboBox:hover {{ border-color: #4a4a4a; }}
        QComboBox::drop-down {{ border: none; }}
    """)
    return cb


# ------------------------------------------------------------------
# SectionRow
# ------------------------------------------------------------------

class SectionRow(QWidget):
    COL_WIDTHS = {"check": 40, "num": 24, "duration": 70, "bpm": 50, "gap": 90}

    def __init__(self, index, start_ms, end_ms, bpm, parent_app):
        super().__init__()
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.parent_app = parent_app

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.setFixedWidth(self.COL_WIDTHS["check"])

        num_label = QLabel(str(index))
        num_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        num_label.setFixedWidth(self.COL_WIDTHS["num"])

        range_text = f"{start_ms:,} → {end_ms:,}".replace(",", " ")
        range_label = QLabel(range_text)
        range_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px; "
            f"font-family: 'Consolas', monospace;"
        )

        duration_s = (end_ms - start_ms) / 1000
        duration_label = QLabel(f"{duration_s:.1f} s")
        duration_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        duration_label.setFixedWidth(self.COL_WIDTHS["duration"])

        bpm_label = QLabel(f"{bpm:.1f}")
        bpm_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        bpm_label.setFixedWidth(self.COL_WIDTHS["bpm"])

        self.gap_dropdown = build_gap_dropdown(self.COL_WIDTHS["gap"])
        self.gap_dropdown.currentTextChanged.connect(self._on_gap_changed)

        if end_ms <= start_ms:
            self.checkbox.setChecked(False)
            self.checkbox.setEnabled(False)
            range_label.setStyleSheet(
                f"color: {RED}; font-size: 12px; "
                f"font-family: 'Consolas', monospace;"
            )
            duration_label.setText("invalid")
            duration_label.setStyleSheet(f"color: {RED}; font-size: 12px;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)
        layout.addWidget(self.checkbox)
        layout.addWidget(num_label)
        layout.addWidget(range_label, stretch=1)
        layout.addWidget(duration_label)
        layout.addWidget(bpm_label)
        layout.addWidget(self.gap_dropdown)
        self.setStyleSheet(f"SectionRow {{ border-top: 1px solid {ROW_DIVIDER}; }}")

    def _on_gap_changed(self, new_text):
        if new_text == CUSTOM_LABEL:
            value, ok = QInputDialog.getInt(
                self.parent_app, "Custom LN gap", "Enter denominator (1/n):",
                value=4, minValue=2, maxValue=64,
            )
            if ok:
                self.set_gap_label(f"1/{value}")
            else:
                self.set_gap_label(DEFAULT_GAP_LABEL)

    def set_gap_label(self, label):
        self.gap_dropdown.blockSignals(True)
        if self.gap_dropdown.findText(label) == -1:
            custom_idx = self.gap_dropdown.findText(CUSTOM_LABEL)
            self.gap_dropdown.insertItem(custom_idx, label)
        self.gap_dropdown.setCurrentText(label)
        self.gap_dropdown.blockSignals(False)

    def is_included(self):
        return self.checkbox.isChecked()

    def get_gap_denominator(self):
        return parse_gap_label(self.gap_dropdown.currentText())


# ------------------------------------------------------------------
# SectionsTable
# ------------------------------------------------------------------

class SectionsTable(QWidget):
    def __init__(self, parent_app):
        super().__init__()
        self.parent_app = parent_app
        self.rows = []
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self._build_empty_state()
        self.setStyleSheet(f"""
            SectionsTable {{
                background-color: {TABLE_BG};
                border: 1px solid #2a2a2a;
                border-radius: 8px;
            }}
        """)

    def _clear(self):
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.rows = []

    def _build_empty_state(self):
        self._clear()
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.setContentsMargins(30, 40, 30, 40)
        el.setAlignment(Qt.AlignCenter)
        el.setSpacing(8)
        icon = QLabel("♪")
        icon.setStyleSheet(f"color: {TEXT_DIM}; font-size: 32px;")
        icon.setAlignment(Qt.AlignCenter)
        msg = QLabel("Load a beatmap to see its bookmarks")
        msg.setStyleSheet(f"color: {TEXT_DIM}; font-size: 13px;")
        msg.setAlignment(Qt.AlignCenter)
        el.addWidget(icon)
        el.addWidget(msg)
        self.layout.addWidget(empty)

    def _build_header(self):
        header = QWidget()
        header.setStyleSheet(f"background-color: {TABLE_HEADER};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 8, 12, 8)
        hl.setSpacing(8)
        labels = [
            ("on",       SectionRow.COL_WIDTHS["check"]),
            ("#",        SectionRow.COL_WIDTHS["num"]),
            ("Range",    None),
            ("Duration", SectionRow.COL_WIDTHS["duration"]),
            ("BPM",      SectionRow.COL_WIDTHS["bpm"]),
            ("LN gap",   SectionRow.COL_WIDTHS["gap"]),
        ]
        for text, width in labels:
            label = QLabel(text)
            label.setStyleSheet(
                f"color: {TEXT_DIM}; font-size: 11px; font-weight: 500;"
            )
            if width is None:
                hl.addWidget(label, stretch=1)
            else:
                label.setFixedWidth(width)
                hl.addWidget(label)
        self.layout.addWidget(header)

    def populate(self, bookmarks, bpm_lookup):
        self._clear()
        self._build_header()
        for i, (start, end) in enumerate(bookmarks, start=1):
            row = SectionRow(i, start, end, bpm_lookup(start), self.parent_app)
            self.rows.append(row)
            self.layout.addWidget(row)

    def show_empty(self):
        self._build_empty_state()

    def apply_gap_to_all(self, label):
        for row in self.rows:
            row.set_gap_label(label)


# ------------------------------------------------------------------
# Ventana principal
# ------------------------------------------------------------------

class InverseGeneratorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mania Inverse Generator")
        self.resize(780, 800)
        self.setStyleSheet(f"QMainWindow {{ background-color: {DARK_BG}; }}")

        self.loaded_beatmap = None
        self.last_output_path = None
        self.tosu_status = {"connected": False}
        self.detected_path = None

        central = QWidget()
        self.setCentralWidget(central)
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(12)

        self._build_header()
        self._build_beatmap_section()
        self._build_sections_area()
        self._build_output_section()
        self.main_layout.addStretch()

        self._start_polling()

    # ---------- HEADER ----------

    def _build_header(self):
        title_icon = QLabel("🎵")
        title_icon.setStyleSheet("font-size: 22px;")
        title_text = QLabel("mania inverse generator")
        title_text.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 500;"
        )
        left = QHBoxLayout()
        left.setSpacing(10)
        left.addWidget(title_icon)
        left.addWidget(title_text)

        self.tosu_pill = StatusPill("tosu")
        self.osu_pill  = StatusPill("osu!")
        right = QHBoxLayout()
        right.setSpacing(6)
        right.addWidget(self.tosu_pill)
        right.addWidget(self.osu_pill)

        header = QHBoxLayout()
        header.addLayout(left)
        header.addStretch()
        header.addLayout(right)
        self.main_layout.addLayout(header)

    # ---------- BEATMAP SECTION ----------

    def _build_beatmap_section(self):
        self.beatmap_card = BeatmapCard()
        self.beatmap_card.load_button.clicked.connect(self._on_load_clicked)
        self.main_layout.addWidget(self.beatmap_card)

        self.browse_button = QPushButton("📁 or browse manually…")
        self.browse_button.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_MUTED};
                border: none; font-size: 12px; padding: 4px;
            }}
            QPushButton:hover {{ color: {TEXT_PRIMARY}; }}
        """)
        self.browse_button.setCursor(Qt.PointingHandCursor)
        self.browse_button.clicked.connect(self._on_browse_clicked)

        browse_row = QHBoxLayout()
        browse_row.addStretch()
        browse_row.addWidget(self.browse_button)
        browse_row.addStretch()
        self.main_layout.addLayout(browse_row)

    # ---------- SECTIONS AREA ----------

    def _build_sections_area(self):
        sections_title = QLabel("Sections")
        sections_title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 500;"
        )
        sections_subtitle = QLabel("from bookmarks · uncheck to skip")
        sections_subtitle.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        label_row = QHBoxLayout()
        label_row.addWidget(sections_title)
        label_row.addStretch()
        label_row.addWidget(sections_subtitle)
        self.main_layout.addLayout(label_row)

        apply_label = QLabel("Apply gap to all:")
        apply_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self.apply_gap_dropdown = build_gap_dropdown(100)
        self.apply_gap_dropdown.currentTextChanged.connect(self._on_apply_gap_changed)

        apply_button = QPushButton("Apply")
        apply_button.setCursor(Qt.PointingHandCursor)
        apply_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {PILL_BG}; color: {TEXT_PRIMARY};
                border: 1px solid #3a3a3a; border-radius: 4px;
                padding: 4px 12px; font-size: 12px;
            }}
            QPushButton:hover {{ background-color: #353535; }}
        """)
        apply_button.clicked.connect(self._on_apply_all_clicked)

        apply_row = QHBoxLayout()
        apply_row.addWidget(apply_label)
        apply_row.addWidget(self.apply_gap_dropdown)
        apply_row.addWidget(apply_button)
        apply_row.addStretch()
        self.main_layout.addLayout(apply_row)

        self.sections_table = SectionsTable(self)
        self.main_layout.addWidget(self.sections_table)

    # ---------- OUTPUT SECTION ----------

    def _build_output_section(self):
        output_title = QLabel("Output")
        output_title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 500;"
        )
        self.main_layout.addWidget(output_title)

        diff_label = QLabel("Diff name:")
        diff_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self.diff_name_field = QLineEdit(DEFAULT_DIFF_NAME)
        self.diff_name_field.setFixedWidth(200)
        self.diff_name_field.setStyleSheet(f"""
            QLineEdit {{
                background-color: {PILL_BG}; color: {TEXT_PRIMARY};
                border: 1px solid #3a3a3a; border-radius: 4px;
                padding: 4px 8px; font-size: 12px;
            }}
            QLineEdit:focus {{ border-color: {BLUE_ACCENT}; }}
        """)

        min_ln_label = QLabel("Min LN (ms):")
        min_ln_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self.min_ln_field = QLineEdit(str(DEFAULT_MIN_LN_MS))
        self.min_ln_field.setFixedWidth(60)
        self.min_ln_field.setStyleSheet(self.diff_name_field.styleSheet())

        config_row = QHBoxLayout()
        config_row.setSpacing(8)
        config_row.addWidget(diff_label)
        config_row.addWidget(self.diff_name_field)
        config_row.addSpacing(16)
        config_row.addWidget(min_ln_label)
        config_row.addWidget(self.min_ln_field)
        config_row.addStretch()
        self.main_layout.addLayout(config_row)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")

        self.open_folder_button = QPushButton("📂 Open file location")
        self.open_folder_button.setCursor(Qt.PointingHandCursor)
        self.open_folder_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {PILL_BG}; color: {TEXT_PRIMARY};
                border: 1px solid #3a3a3a; border-radius: 4px;
                padding: 6px 14px; font-size: 12px;
            }}
            QPushButton:hover {{ background-color: #353535; }}
        """)
        self.open_folder_button.clicked.connect(self._on_open_folder_clicked)
        self.open_folder_button.hide()

        self.generate_button = QPushButton("Generate inverse")
        self.generate_button.setEnabled(False)
        self.generate_button.setCursor(Qt.PointingHandCursor)
        self.generate_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {BLUE_ACCENT}; color: white;
                border: none; border-radius: 6px;
                padding: 8px 20px; font-size: 13px; font-weight: 500;
            }}
            QPushButton:hover {{ background-color: #5fb1f7; }}
            QPushButton:disabled {{
                background-color: #3a3a3a; color: rgba(255, 255, 255, 0.4);
            }}
        """)
        self.generate_button.clicked.connect(self._on_generate_clicked)

        gen_row = QHBoxLayout()
        gen_row.addWidget(self.status_label)
        gen_row.addStretch()
        gen_row.addWidget(self.open_folder_button)
        gen_row.addWidget(self.generate_button)
        self.main_layout.addLayout(gen_row)

    # ==================================================================
    # POLLING DE TOSU
    # ==================================================================

    def _start_polling(self):
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_tosu)
        self.poll_timer.start(POLL_INTERVAL_MS)
        self._poll_tosu()

    def _poll_tosu(self):
        self.tosu_status = fetch_status()
        self._update_pills()
        self._update_card_from_tosu()

    def _update_pills(self):
        s = self.tosu_status
        self.tosu_pill.set_connected(s.get("connected", False))
        self.osu_pill.set_connected(
            s.get("connected", False) and s.get("osu_running", False)
        )

    def _update_card_from_tosu(self):
        """
        Actualiza el card con lo que reporta tosu.
        Si hay mapa cargado: mostramos el detectado y etiquetamos el botón
        como 'Switch to this map' si es distinto al cargado.
        Si no hay mapa cargado: card muestra info normal de detección.
        """
        s = self.tosu_status

        # Caso 1: tosu no responde
        if not s.get("connected"):
            if self.loaded_beatmap is None:
                self.beatmap_card.set_state_message(
                    title="tosu not running",
                    subtitle="Start tosu.exe to enable auto-detection",
                    stats="",
                    load_enabled=False,
                )
            self.detected_path = None
            return

        # Caso 2: tosu OK pero osu! no abierto
        if not s.get("osu_running"):
            if self.loaded_beatmap is None:
                self.beatmap_card.set_state_message(
                    title="osu! not detected",
                    subtitle="Open osu! to detect the current map",
                    stats="",
                    load_enabled=False,
                )
            self.detected_path = None
            return

        # Caso 3: osu! abierto pero sin mapa seleccionado
        if not s.get("map_loaded"):
            if self.loaded_beatmap is None:
                self.beatmap_card.set_state_message(
                    title="No map loaded",
                    subtitle=f"osu! state: {s.get('osu_state', '?')}",
                    stats="",
                    load_enabled=False,
                )
            self.detected_path = None
            return

        # Caso 4: tosu detectó un mapa. Construimos info y decidimos qué mostrar.
        m = s.get("metadata", {})
        st = s.get("stats", {})
        bpm_str = (f"{st.get('bpm_common', 0)} BPM"
                   if st.get('bpm_min') == st.get('bpm_max')
                   else f"{st.get('bpm_min', 0)}–{st.get('bpm_max', 0)} BPM")

        detected_path = s.get("path")
        self.detected_path = detected_path

        title_text = f"{m.get('artist', '?')} — {m.get('title', '?')}"
        subtitle_text = f"[{m.get('difficulty', '?')}] · mapped by {m.get('mapper', '?')}"
        stats_text = f"{st.get('key_count', '?')}K  ·  {bpm_str}  ·  {st.get('notes_total', '?')} notes"

        # Caso 4a: hay mapa cargado en la app
        if self.loaded_beatmap is not None:
            loaded_path = normalize_path(self.loaded_beatmap.path)
            detected_norm = normalize_path(detected_path)

            if loaded_path == detected_norm:
                # Es el mismo mapa que tenemos cargado: no tocamos el card
                return

            # Mapa distinto: ofrecemos cambiar
            self.beatmap_card.set_state_message(
                title=title_text,
                subtitle=subtitle_text,
                stats=f"Detected in osu! · {bpm_str}",
                load_enabled=True,
            )
            self.beatmap_card.load_button.setText("Switch to this map")
            return

        # Caso 4b: no hay mapa cargado, mostramos info de detección normal
        self.beatmap_card.set_state_message(
            title=title_text,
            subtitle=subtitle_text,
            stats=stats_text,
            load_enabled=True,
        )
        self.beatmap_card.load_button.setText("Load this map")

    # ---------- HANDLERS ----------

    def _on_load_clicked(self):
        if self.detected_path:
            self._load_beatmap(self.detected_path)

    def _on_browse_clicked(self):
        # Intentamos abrir el diálogo en la carpeta Songs/ de osu!
        # Si no la encontramos, abre donde Windows quiera (string vacío).
        start_dir = find_songs_folder() or ""

        path, _ = QFileDialog.getOpenFileName(
            self, "Select a beatmap", start_dir,
            "osu! beatmaps (*.osu);;All files (*)",
        )
        if path:
            self._load_beatmap(path)

    def _on_apply_gap_changed(self, new_text):
        if new_text == CUSTOM_LABEL:
            value, ok = QInputDialog.getInt(
                self, "Custom LN gap", "Enter denominator (1/n):",
                value=4, minValue=2, maxValue=64,
            )
            if ok:
                label = f"1/{value}"
                if self.apply_gap_dropdown.findText(label) == -1:
                    custom_idx = self.apply_gap_dropdown.findText(CUSTOM_LABEL)
                    self.apply_gap_dropdown.blockSignals(True)
                    self.apply_gap_dropdown.insertItem(custom_idx, label)
                    self.apply_gap_dropdown.blockSignals(False)
                self.apply_gap_dropdown.setCurrentText(label)
            else:
                self.apply_gap_dropdown.blockSignals(True)
                self.apply_gap_dropdown.setCurrentText(DEFAULT_GAP_LABEL)
                self.apply_gap_dropdown.blockSignals(False)

    def _on_apply_all_clicked(self):
        label = self.apply_gap_dropdown.currentText()
        if label == CUSTOM_LABEL:
            return
        self.sections_table.apply_gap_to_all(label)

    def _on_open_folder_clicked(self):
        if self.last_output_path and os.path.exists(self.last_output_path):
            subprocess.run(["explorer", "/select,", str(self.last_output_path)])

    def _on_generate_clicked(self):
        bm = self.loaded_beatmap
        if bm is None:
            return

        selected = [
            (r.start_ms, r.end_ms, r.get_gap_denominator())
            for r in self.sections_table.rows if r.is_included()
        ]
        if not selected:
            self._show_status("No sections selected.", error=True)
            return
        if any(denom is None for _, _, denom in selected):
            self._show_status("Some sections have invalid gaps.", error=True)
            return

        try:
            min_ln = int(self.min_ln_field.text())
            if min_ln < 0:
                raise ValueError
        except ValueError:
            self._show_status("Min LN must be a positive number.", error=True)
            return

        diff_name = self.diff_name_field.text().strip() or DEFAULT_DIFF_NAME

        try:
            for start, end, denom in selected:
                bm.hit_objects = invert_section(
                    bm, start, end, denom, min_ln_ms=min_ln
                )
            out_path = bm.save(new_difficulty=diff_name)
        except Exception as ex:
            self._show_status(f"Generation failed: {ex}", error=True)
            return

        self.last_output_path = out_path
        self.open_folder_button.show()
        self._show_status(f"✓ Saved: {os.path.basename(out_path)}", error=False)

    def _show_status(self, msg, error=False):
        color = RED if error else GREEN
        self.status_label.setText(msg)
        self.status_label.setStyleSheet(f"color: {color}; font-size: 12px;")

    # ---------- CARGA DEL BEATMAP ----------

    def _load_beatmap(self, path):
        try:
            bm = Beatmap(path)
        except Exception as ex:
            self.beatmap_card.set_state_message(
                title="Failed to read map", subtitle=str(ex),
                stats="", load_enabled=False,
            )
            return

        if not bm.is_mania():
            self.beatmap_card.set_state_message(
                title="Not a mania map",
                subtitle=f"[{bm.metadata.get('Version', '?')}] · only osu!mania maps are supported",
                stats="", load_enabled=False,
            )
            self.sections_table.show_empty()
            self.generate_button.setEnabled(False)
            return

        # Decidir qué secciones usar: bookmarks o auto-detected
        if bm.bookmarks:
            sections_to_use = bm.bookmarks
            used_auto = False
        else:
            sections_to_use = auto_detect_sections(bm)
            used_auto = True
            if not sections_to_use:
                self.beatmap_card.set_state_message(
                    title=bm.title(),
                    subtitle="No bookmarks · couldn't auto-detect sections either",
                    stats="", load_enabled=False,
                )
                self.sections_table.show_empty()
                self.generate_button.setEnabled(False)
                return

        self.loaded_beatmap = bm
        artist = bm.metadata.get("Artist", "?")
        title = bm.metadata.get("Title", "?")
        diff = bm.metadata.get("Version", "?")
        mapper = bm.metadata.get("Creator", "?")

        section_origin = "auto-detected" if used_auto else "bookmarks"
        self.beatmap_card.set_state_message(
            title=f"{artist} — {title}",
            subtitle=f"[{diff}] · mapped by {mapper}",
            stats=(
                f"{bm.key_count()}K · "
                f"{len(sections_to_use)} sections ({section_origin}) · "
                f"{len(bm.hit_objects)} notes"
            ),
            load_enabled=False,
        )

        self.sections_table.populate(sections_to_use, bm.bpm_at)
        self.generate_button.setEnabled(True)
        self.open_folder_button.hide()
        self.beatmap_card.load_button.setText("Load this map")

        if used_auto:
            self._show_status(
                "Auto-detected sections — review the table before generating.",
                error=False,
            )
            self.status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        else:
            self._show_status("")


def main():
    app = QApplication(sys.argv)
    window = InverseGeneratorApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()