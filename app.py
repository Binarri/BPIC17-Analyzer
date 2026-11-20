from pathlib import Path
import importlib.metadata
import platform
import sys

import pandas as pd

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    QThread,
    Signal,
    Qt,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QStackedWidget,
    QPushButton,
    QLabel,
    QFileDialog,
    QMessageBox,
    QListWidget,
    QProgressBar,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QTableView,
    QHeaderView,
    QFrame,
    QScrollArea,
    QDialog,
)

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from modules.importer import import_xes
from modules.overview import generate_overview
from modules.exercise_11_7_ab import (
    CASE_COLUMN,
    TIMESTAMP_COLUMN,
    count_unique_cases,
    calculate_case_durations,
    summarize_cases,
)

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


# ======================================================================
# HELPER
# ======================================================================
def pd_not_null(value):
    """True jika nilai bukan None / NaN / NaT."""
    if value is None:
        return False
    try:
        return not bool(pd.isna(value))
    except (TypeError, ValueError):
        return True


def format_datetime_series(series):
    """Format Series timestamp jadi teks; NaT menjadi '-'."""
    converted = pd.to_datetime(series, errors="coerce", utc=True)
    return converted.dt.strftime(DATETIME_FORMAT).fillna("-")


# ======================================================================
# MODEL TABEL CASE (dipakai Overview dan Exercise 11.7)
# ======================================================================
class CaseTableModel(QAbstractTableModel):
    HEADERS = ["Case ID", "Start Time", "End Time", "Duration (Days)"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._display = []
        self._sort = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._display)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return section + 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display[row][col]
        if role == Qt.ItemDataRole.UserRole:  # nilai untuk sorting
            return self._sort[row][col]
        if role == Qt.ItemDataRole.TextAlignmentRole and col == 3:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def set_data(self, case_ids, starts, ends, days):
        """Isi model dari 4 deret data (Series/list) yang sama panjang."""
        self.beginResetModel()

        ids = [str(value) for value in pd.Series(case_ids).tolist()]
        start_text = format_datetime_series(pd.Series(starts)).tolist()
        end_text = format_datetime_series(pd.Series(ends)).tolist()
        day_values = pd.Series(days, dtype="float64").tolist()

        day_text = [
            f"{value:.2f}" if pd_not_null(value) else "Tidak tersedia"
            for value in day_values
        ]
        day_sort = [
            float(value) if pd_not_null(value) else -1.0 for value in day_values
        ]

        self._display = list(zip(ids, start_text, end_text, day_text))
        self._sort = list(zip(ids, start_text, end_text, day_sort))
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._display = []
        self._sort = []
        self.endResetModel()


# ======================================================================
# DIALOG RINCIAN CASE (reusable untuk semua panel / Case Explorer)
# ======================================================================
class CaseDetailDialog(QDialog):
    COLUMN_LABELS = [
        (TIMESTAMP_COLUMN, "Timestamp"),
        ("concept:name", "Activity"),
        ("lifecycle:transition", "Lifecycle"),
        ("org:resource", "Resource"),
    ]

    def __init__(self, parent, case_id, events):
        super().__init__(parent)
        self.setWindowTitle(f"Rincian Case: {case_id}")
        self.resize(780, 440)

        layout = QVBoxLayout(self)

        # Ringkasan case
        timestamps = pd.to_datetime(events[TIMESTAMP_COLUMN], errors="coerce", utc=True)
        has_nat = bool(timestamps.isna().any())
        if has_nat or timestamps.empty:
            duration_text = "tidak tersedia (ada timestamp kosong)"
        else:
            days = (timestamps.max() - timestamps.min()).total_seconds() / 86400
            duration_text = f"{days:.2f} hari"

        summary = QLabel(
            f"Jumlah event: {len(events):,}   |   Durasi case: {duration_text}\n"
            "Urutan event: berdasarkan timestamp; jika timestamp sama, "
            "mengikuti urutan baris pada file XES (sort stabil)."
        )
        summary.setStyleSheet("color: #4A5568;")
        layout.addWidget(summary)

        # Tabel event
        columns = [(c, label) for c, label in self.COLUMN_LABELS if c in events.columns]

        table = QTableWidget(len(events), len(columns))
        table.setHorizontalHeaderLabels([label for _, label in columns])
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        for col_index, (column, _) in enumerate(columns):
            if column == TIMESTAMP_COLUMN:
                values = format_datetime_series(events[column]).tolist()
            else:
                values = [
                    str(v) if pd_not_null(v) else "-" for v in events[column].tolist()
                ]
            for row_index, value in enumerate(values):
                table.setItem(row_index, col_index, QTableWidgetItem(value))

        layout.addWidget(table)

        close_button = QPushButton("Tutup")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)


# ======================================================================
# WORKER
# ======================================================================
class ImportWorker(QThread):
    imported = Signal(object)
    overview_ready = Signal(object)
    import_failed = Signal(str)
    overview_failed = Signal(str)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            result = import_xes(self.file_path)
            self.imported.emit(result)
        except Exception as error:
            self.import_failed.emit(f"{type(error).__name__}: {error}")
            return

        try:
            overview = generate_overview(result["dataframe"])
            self.overview_ready.emit(overview)
        except Exception as error:
            self.overview_failed.emit(f"{type(error).__name__}: {error}")


class Exercise117Worker(QThread):
    """Menghitung 11.7 A-B di background thread."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, dataframe):
        super().__init__()
        self.dataframe = dataframe

    def run(self):
        try:
            total_cases = count_unique_cases(self.dataframe)  # 11.7 A
            durations = calculate_case_durations(self.dataframe)  # durasi per case
            summary = summarize_cases(durations)  # 11.7 B
            self.succeeded.emit(
                {
                    "total_cases": total_cases,
                    "summary": summary,
                    "durations": durations,
                }
            )
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")


# ======================================================================
# MAIN WINDOW
# ======================================================================
class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("BPIC17 Analyzer")
        self.resize(1450, 900)
        self.setMinimumSize(1100, 700)

        self.active_data = None
        self.worker = None
        self.worker_117 = None
        self.case_data = None
        self.result_117 = None      # hasil analisis 11.7 A-B yang sedang tampil
        self._case_groups = None    # cache: case ID -> posisi baris di dataframe

        self.build_interface()

    # ------------------------------------------------------------------
    # MAIN INTERFACE
    # ------------------------------------------------------------------
    def build_interface(self):
        central = QWidget()
        self.setCentralWidget(central)

        # Menu About (versi Python / PM4Py / dependency)
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("About", self.show_about)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # TOP NAVBAR
        navbar = QWidget()
        navbar.setObjectName("navbar")
        navbar.setFixedHeight(58)

        nav_layout = QHBoxLayout(navbar)
        nav_layout.setContentsMargins(20, 0, 20, 0)
        nav_layout.setSpacing(10)

        brand = QLabel("BPIC17 Analyzer")
        brand.setObjectName("brand")
        brand.setAutoFillBackground(False)
        nav_layout.addWidget(brand)
        nav_layout.addStretch()

        self.nav_overview = QPushButton("Overview")
        self.nav_117 = QPushButton("Exercise 11.7")
        self.nav_1518 = QPushButton("Exercise 11.15 & 11.18")
        self.nav_1122 = QPushButton("Exercise 11.22")
        self.nav_explorer = QPushButton("Case Explorer")
        self.nav_dataset = QPushButton("Dataset")

        self.nav_overview.clicked.connect(lambda: self.show_page(0))
        self.nav_dataset.clicked.connect(lambda: self.show_page(1))
        self.nav_117.clicked.connect(lambda: self.show_page(2))

        # Fitur anggota lain (diaktifkan saat modulnya digabung)
        placeholders = (
            (self.nav_1518, "Reserved: Exercise 11.15 & 11.18 (Binar)"),
            (self.nav_1122, "Reserved: Exercise 11.22 (Kayla)"),
            (self.nav_explorer, "Reserved: Case Explorer (Kayla)"),
        )
        for button, tooltip in placeholders:
            button.setEnabled(False)
            button.setToolTip(tooltip)

        for button in (
            self.nav_overview,
            self.nav_117,
            self.nav_1518,
            self.nav_1122,
            self.nav_explorer,
            self.nav_dataset,
        ):
            button.setObjectName("navButton")
            button.setCheckable(True)
            nav_layout.addWidget(button)

        root.addWidget(navbar)

        # MAIN BODY
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.sidebar = self.create_sidebar()
        body.addWidget(self.sidebar)

        self.pages = QStackedWidget()
        self.overview_page = self.create_overview_page()
        self.dataset_page = self.create_dataset_page()
        self.exercise_117_page = self.create_exercise_117_page()

        self.pages.addWidget(self.overview_page)       # index 0
        self.pages.addWidget(self.dataset_page)        # index 1
        self.pages.addWidget(self.exercise_117_page)   # index 2

        body.addWidget(self.pages, 1)
        root.addLayout(body)

        self.apply_styles()
        self.show_page(0)

    # ------------------------------------------------------------------
    # STYLESHEET
    # ------------------------------------------------------------------
    def apply_styles(self):
        self.setStyleSheet("""
            QWidget {
                font-family: Segoe UI;
                font-size: 9pt;
                color: #273444;
                background-color: #F1F4F8;
            }
            QMainWindow { background-color: #F1F4F8; }
            QWidget#navbar { background-color: #354252; }

            QLabel#brand {
                color: white; background: transparent; border: none;
                padding: 0px; font-size: 15px; font-weight: bold;
            }

            QPushButton#navButton {
                background-color: transparent; color: #DCE3EA; border: none;
                padding: 9px 17px; border-radius: 4px; min-width: 75px;
            }
            QPushButton#navButton:hover { background-color: #526174; }
            QPushButton#navButton:checked {
                background-color: #E8EDF3; color: #354252; font-weight: bold;
            }
            QPushButton#navButton:disabled {
                color: #AAB4C0; background-color: transparent;
            }

            QWidget#sidebar {
                background-color: #E5EAF0; border-right: 1px solid #D1D9E2;
            }
            QLabel#sectionTitle {
                background: transparent; color: #354252;
                font-size: 10pt; font-weight: bold; padding: 3px 0px;
            }
            QLabel#sidebarKey { background: transparent; color: #526174; font-size: 8pt; }
            QLabel#sidebarValue { background: transparent; color: #354252; font-size: 8pt; }

            QFrame#metricCard {
                background-color: #EAF2FA; border: 1px solid #D3DFEB; border-radius: 5px;
            }
            QLabel#metricTitle { background: transparent; color: #64748B; font-size: 8pt; }
            QLabel#metricValue {
                background: transparent; color: #263548;
                font-size: 15px; font-weight: bold;
            }

            QFrame#panel {
                background-color: white; border: 1px solid #D7DEE7; border-radius: 5px;
            }
            QLabel#panelTitle {
                background: transparent; color: #354252;
                font-size: 10pt; font-weight: bold;
            }

            QPushButton {
                background-color: #526A82; color: white; border: none;
                border-radius: 4px; padding: 9px 14px;
            }
            QPushButton:hover { background-color: #40566D; }
            QPushButton:disabled { background-color: #AAB4C0; }

            QLineEdit {
                background-color: white; border: 1px solid #C9D2DD;
                padding: 8px; border-radius: 4px;
            }

            QListWidget, QTableView {
                background-color: white; alternate-background-color: #F0F3F7;
                gridline-color: #DCE3EB; border: 1px solid #D7DEE7;
                selection-background-color: #DCE7F2; selection-color: #263548;
            }
            QHeaderView::section {
                background-color: #DFE8F2; color: #344A60; padding: 8px;
                border: none; border-bottom: 1px solid #C9D4E0; font-weight: bold;
            }
            QTableView QTableCornerButton::section {
                background-color: #DFE8F2; border: none;
            }

            QScrollArea { background-color: #F1F4F8; border: none; }
            QScrollBar:vertical { background: #E5EAF0; width: 10px; margin: 0px; }
            QScrollBar::handle:vertical {
                background: #9AA9B9; min-height: 25px; border-radius: 4px;
            }
            QScrollBar:horizontal { background: #E5EAF0; height: 10px; }
            QScrollBar::handle:horizontal {
                background: #9AA9B9; min-width: 25px; border-radius: 4px;
            }

            QProgressBar { background: #DFE5EC; border: none; border-radius: 4px; height: 8px; }
            QProgressBar::chunk { background: #607D98; border-radius: 4px; }

            QFrame#sidebarLine { background-color: #C7D0DA; border: none; max-height: 1px; }
        """)

    # ------------------------------------------------------------------
    # SIDEBAR
    # ------------------------------------------------------------------
    def create_sidebar(self):
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(225)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(9)

        event_title = QLabel("▤  Event Log")
        event_title.setObjectName("sectionTitle")
        layout.addWidget(event_title)

        self.sidebar_file = QLabel("No dataset selected")
        self.sidebar_file.setObjectName("sidebarValue")
        self.sidebar_file.setWordWrap(True)
        layout.addWidget(self.sidebar_file)

        line = QFrame()
        line.setObjectName("sidebarLine")
        line.setFixedHeight(1)
        layout.addWidget(line)

        statistics_title = QLabel("Statistics")
        statistics_title.setObjectName("sectionTitle")
        layout.addWidget(statistics_title)

        self.side_cases = self.add_sidebar_stat(layout, "Cases", "-")
        self.side_events = self.add_sidebar_stat(layout, "Events", "-")
        self.side_activities = self.add_sidebar_stat(layout, "Activities", "-")
        self.side_cycle = self.add_sidebar_stat(layout, "Avg. Cycle Time", "-")
        self.side_start = self.add_sidebar_stat(layout, "Start", "-")
        self.side_end = self.add_sidebar_stat(layout, "End", "-")

        layout.addStretch()
        return sidebar

    def add_sidebar_stat(self, parent_layout, title, value):
        row = QWidget()
        row.setStyleSheet("background: transparent;")

        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(5)

        key_label = QLabel(title)
        key_label.setObjectName("sidebarKey")
        key_label.setMinimumWidth(92)

        value_label = QLabel(value)
        value_label.setObjectName("sidebarValue")
        value_label.setWordWrap(True)

        row_layout.addWidget(key_label)
        row_layout.addWidget(value_label, 1)
        parent_layout.addWidget(row)
        return value_label

    # ------------------------------------------------------------------
    # PAGE NAVIGATION
    # ------------------------------------------------------------------
    def show_page(self, index):
        self.pages.setCurrentIndex(index)
        self.nav_overview.setChecked(index == 0)
        self.nav_dataset.setChecked(index == 1)
        self.nav_117.setChecked(index == 2)

    # ------------------------------------------------------------------
    # KOMPONEN BERSAMA
    # ------------------------------------------------------------------
    def create_metric_card(self, grid, column, title):
        card = QFrame()
        card.setObjectName("metricCard")
        card.setFixedHeight(82)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(11, 8, 11, 8)
        card_layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setObjectName("metricTitle")

        value_label = QLabel("-")
        value_label.setObjectName("metricValue")
        value_label.setWordWrap(True)

        card_layout.addWidget(title_label)
        card_layout.addWidget(value_label)
        grid.addWidget(card, 0, column)
        return value_label

    def create_panel(self, title):
        panel = QFrame()
        panel.setObjectName("panel")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(9, 8, 9, 9)
        layout.setSpacing(7)

        heading = QLabel(title)
        heading.setObjectName("panelTitle")
        layout.addWidget(heading)
        return panel

    def create_case_table(self, parent_layout, min_height, max_height=None):
        """
        Kotak pencarian + QTableView (model + proxy) untuk tabel case.
        Mengembalikan (model, proxy, view, search_box).
        """
        search = QLineEdit()
        search.setPlaceholderText("Search Case ID...")
        parent_layout.addWidget(search)

        model = CaseTableModel(self)
        proxy = QSortFilterProxyModel(self)
        proxy.setSourceModel(model)
        proxy.setFilterKeyColumn(0)
        proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        proxy.setSortRole(Qt.ItemDataRole.UserRole)

        search.textChanged.connect(lambda text: proxy.setFilterFixedString(text.strip()))

        view = QTableView()
        view.setModel(proxy)
        view.setAlternatingRowColors(True)
        view.setSortingEnabled(True)
        view.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        view.verticalHeader().setDefaultSectionSize(25)
        view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 4):
            view.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        view.setMinimumHeight(min_height)
        if max_height:
            view.setMaximumHeight(max_height)
        view.doubleClicked.connect(self.on_case_double_clicked)

        parent_layout.addWidget(view)
        return model, proxy, view, search

    # ------------------------------------------------------------------
    # OVERVIEW PAGE - F02
    # ------------------------------------------------------------------
    def create_overview_page(self):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)

        heading = QLabel("Overview")
        heading.setStyleSheet("font-size: 17px; font-weight: bold;")
        layout.addWidget(heading)

        subtitle = QLabel("Global statistics about the event log.")
        subtitle.setStyleSheet("color: #718096;")
        layout.addWidget(subtitle)

        # Metric cards
        metrics_layout = QGridLayout()
        metrics_layout.setSpacing(10)

        self.metric_cases = self.create_metric_card(metrics_layout, 0, "Total Cases")
        self.metric_events = self.create_metric_card(metrics_layout, 1, "Total Events")
        self.metric_cycle = self.create_metric_card(metrics_layout, 2, "Average Cycle Time")
        self.metric_range = self.create_metric_card(metrics_layout, 3, "Date Range")

        for column in range(4):
            metrics_layout.setColumnStretch(column, 1)
        layout.addLayout(metrics_layout)

        # Chart + activity table
        analysis_layout = QHBoxLayout()
        analysis_layout.setSpacing(10)

        chart_panel = self.create_panel("Most Frequent Activities (Top 15)")
        chart_layout = chart_panel.layout()

        self.activity_figure = Figure(figsize=(6, 2.7), dpi=100)
        self.activity_canvas = FigureCanvasQTAgg(self.activity_figure)
        self.activity_canvas.setMinimumHeight(230)
        self.activity_canvas.setMaximumHeight(270)
        chart_layout.addWidget(self.activity_canvas)
        analysis_layout.addWidget(chart_panel, 3)

        activity_panel = self.create_panel("All Activity Frequency")
        activity_layout = activity_panel.layout()

        self.activity_table = QTableWidget(0, 2)
        self.activity_table.setHorizontalHeaderLabels(["Activity", "Frequency"])
        self.activity_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.activity_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.activity_table.setAlternatingRowColors(True)
        self.activity_table.verticalHeader().setDefaultSectionSize(25)
        self.activity_table.setFixedHeight(270)
        activity_layout.addWidget(self.activity_table)
        analysis_layout.addWidget(activity_panel, 2)

        layout.addLayout(analysis_layout)

        # Case duration
        case_panel = self.create_panel("Case Duration")
        (
            self.case_model,
            self.case_proxy,
            self.case_view,
            self.case_search,
        ) = self.create_case_table(case_panel.layout(), 180, 230)
        layout.addWidget(case_panel)
        layout.addStretch()

        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        return page

    # ------------------------------------------------------------------
    # EXERCISE 11.7 PAGE (A-B: Tiwi; C-E: Hana)
    # ------------------------------------------------------------------
    def create_exercise_117_page(self):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget()
        # Hana: tambahkan panel 11.7 C-E lewat self.layout_117 (sebelum addStretch).
        layout = QVBoxLayout(content)
        self.layout_117 = layout
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)

        heading = QLabel("Exercise 11.7")
        heading.setStyleSheet("font-size: 17px; font-weight: bold;")
        layout.addWidget(heading)

        # ---------------- Bagian A-B ----------------
        section = QLabel("Bagian A–B: Jumlah case dan rata-rata cycle time")
        section.setObjectName("sectionTitle")
        layout.addWidget(section)

        rules_label = QLabel(
            "Aturan 11.7 A: menghitung seluruh unique case (case ID unik) pada log aktif.\n"
            "Aturan 11.7 B: rata-rata cycle time = rata-rata (timestamp terakhir − timestamp "
            "pertama) per case, tanpa menghapus event apa pun.\n"
            "Satuan: hari (ketelitian 2 desimal). Case yang memiliki timestamp kosong tetap "
            "dihitung di 11.7 A, tetapi dikecualikan dari rata-rata 11.7 B (denominator B = "
            "valid cases)."
        )
        rules_label.setWordWrap(True)
        rules_label.setStyleSheet("color: #4A5568; font-style: italic; margin-bottom: 6px;")
        layout.addWidget(rules_label)

        # Tombol aksi
        action_layout = QHBoxLayout()

        self.run_117_button = QPushButton("Hitung 11.7 A–B")
        self.run_117_button.setEnabled(False)
        self.run_117_button.clicked.connect(self.run_exercise_117)
        action_layout.addWidget(self.run_117_button)

        self.reset_117_button = QPushButton("Reset")
        self.reset_117_button.setEnabled(False)
        self.reset_117_button.clicked.connect(self.reset_117)
        action_layout.addWidget(self.reset_117_button)

        self.export_117_button = QPushButton("Export to CSV")
        self.export_117_button.setEnabled(False)
        self.export_117_button.clicked.connect(self.export_117_csv)
        action_layout.addWidget(self.export_117_button)

        layout.addLayout(action_layout)

        self.progress_117 = QProgressBar()
        self.progress_117.setRange(0, 1)
        self.progress_117.setValue(0)
        self.progress_117.setVisible(False)
        layout.addWidget(self.progress_117)

        self.status_117 = QLabel("Status: Impor dataset terlebih dahulu.")
        self.status_117.setWordWrap(True)
        self.status_117.setStyleSheet("color: #718096;")
        layout.addWidget(self.status_117)

        # Metrics
        metrics_layout = QGridLayout()
        metrics_layout.setSpacing(10)

        self.metric_117_cases = self.create_metric_card(metrics_layout, 0, "11.7 A — Total Cases")
        self.metric_117_avg = self.create_metric_card(metrics_layout, 1, "11.7 B — Avg. Cycle Time")
        self.metric_117_valid = self.create_metric_card(metrics_layout, 2, "Valid Cases")
        self.metric_117_invalid = self.create_metric_card(metrics_layout, 3, "Invalid Cases")

        for column in range(4):
            metrics_layout.setColumnStretch(column, 1)
        layout.addLayout(metrics_layout)

        # Tabel bukti
        case_panel = self.create_panel("Case Duration (Bukti 11.7 A–B) — double-click untuk rincian case")
        (
            self.case_117_model,
            self.case_117_proxy,
            self.case_117_view,
            self.case_117_search,
        ) = self.create_case_table(case_panel.layout(), 300)
        layout.addWidget(case_panel)

        # Placeholder bagian C-E (Hana)
        placeholder = self.create_panel("11.7 C–E — Successful, Unsuccessful, Canceled")
        note = QLabel("Bagian ini dikerjakan Hana dan akan ditambahkan pada halaman ini.")
        note.setStyleSheet("color: #718096;")
        placeholder.layout().addWidget(note)
        layout.addWidget(placeholder)

        layout.addStretch()

        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        return page

    # ------------------------------------------------------------------
    # DATASET PAGE - F01
    # ------------------------------------------------------------------
    def create_dataset_page(self):
        page = QWidget()

        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        heading = QLabel("Dataset Management")
        heading.setStyleSheet("font-size: 19px; font-weight: bold;")
        layout.addWidget(heading)

        description = QLabel("Import and validate BPIC17 event log in XES format.")
        layout.addWidget(description)

        self.choose_button = QPushButton("Choose XES File")
        self.choose_button.clicked.connect(self.choose_xes_file)
        layout.addWidget(self.choose_button)

        self.file_label = QLabel("No dataset selected")
        self.file_label.setWordWrap(True)

        self.status_label = QLabel("Status: Waiting for dataset")

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setVisible(False)

        self.case_label = QLabel("Total Cases: -")
        self.event_label = QLabel("Total Events: -")
        self.timestamp_label = QLabel("Invalid timestamps: -")
        self.optional_label = QLabel("Optional Attributes: -")

        for widget in (
            self.file_label,
            self.status_label,
            self.progress,
            self.case_label,
            self.event_label,
            self.timestamp_label,
            self.optional_label,
        ):
            layout.addWidget(widget)

        layout.addWidget(QLabel("Available Attributes:"))

        self.attribute_list = QListWidget()
        layout.addWidget(self.attribute_list)

        layout.addStretch()
        return page

    # ------------------------------------------------------------------
    # IMPORT XES
    # ------------------------------------------------------------------
    def choose_xes_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select BPIC17 XES Dataset",
            str(Path.cwd()),
            "XES Files (*.xes)",
        )

        if not file_path:
            return

        self.choose_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)

        self.status_label.setText("Status: Reading and validating dataset...")
        self.file_label.setText(f"Selected file: {Path(file_path).name}")

        self.worker = ImportWorker(file_path)
        self.worker.imported.connect(self.import_succeeded)
        self.worker.overview_ready.connect(self.display_overview)
        self.worker.import_failed.connect(self.import_failed)
        self.worker.overview_failed.connect(self.overview_failed)
        self.worker.finished.connect(self.import_finished)
        self.worker.start()

    def import_succeeded(self, imported):
        self.active_data = {"import": imported, "overview": None}
        self._case_groups = None  # cache lama tidak berlaku untuk dataset baru

        self.file_label.setText(f"Active Dataset: {imported['file_name']}")
        self.status_label.setText("Status: Import successful — calculating overview...")
        self.case_label.setText(f"Total Cases: {imported['total_cases']:,}")
        self.event_label.setText(f"Total Events: {imported['total_events']:,}")
        self.timestamp_label.setText(
            f"Invalid timestamps: {imported['invalid_timestamp_events']:,}"
        )

        optional = imported["available_optional"]
        self.optional_label.setText(
            "Optional Attributes: " + (", ".join(optional) if optional else "None detected")
        )

        self.attribute_list.clear()
        self.attribute_list.addItems(imported["available_columns"])

        # Sidebar
        self.sidebar_file.setText(imported["file_name"])
        self.side_cases.setText(f"{imported['total_cases']:,}")
        self.side_events.setText(f"{imported['total_events']:,}")

        # Exercise 11.7: bersihkan hasil lama, aktifkan tombol hitung
        self.reset_117(clear_status=False)
        self.run_117_button.setEnabled(True)
        self.status_117.setText(
            f"Status: Dataset siap ({imported['total_cases']:,} case). "
            "Klik tombol untuk menghitung."
        )

    def import_failed(self, message):
        self.status_label.setText("Status: Import failed")
        QMessageBox.critical(self, "Import Failed", "Dataset tidak dapat diimpor.\n\n" + message)

    def import_finished(self):
        self.choose_button.setEnabled(True)
        self.progress.setVisible(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)

    def overview_failed(self, message):
        self.status_label.setText("Status: Import successful — Overview failed")
        QMessageBox.warning(self, "Overview Failed", message)

    # ------------------------------------------------------------------
    # DISPLAY OVERVIEW
    # ------------------------------------------------------------------
    def display_overview(self, overview):
        if self.active_data is not None:
            self.active_data["overview"] = overview

        total_cases = overview["total_cases"]
        total_events = overview["total_events"]
        average = overview["average_cycle_time_days"]

        self.metric_cases.setText(f"{total_cases:,}")
        self.metric_events.setText(f"{total_events:,}")
        self.metric_cycle.setText(
            f"{average:.2f} days" if average is not None else "Not available"
        )

        start = overview["start_date"]
        end = overview["end_date"]
        start_text = start.strftime(DATETIME_FORMAT) if pd_not_null(start) else "-"
        end_text = end.strftime(DATETIME_FORMAT) if pd_not_null(end) else "-"
        self.metric_range.setText(f"{start_text} — {end_text}")

        # Sidebar statistics
        activity = overview["activity_frequency"]
        self.side_activities.setText(str(len(activity)))
        self.side_cycle.setText(f"{average:.2f} days" if average is not None else "-")
        self.side_start.setText(start_text)
        self.side_end.setText(end_text)

        # Top 15 activity chart
        top_activity = activity.head(15).iloc[::-1]

        self.activity_figure.clear()
        ax = self.activity_figure.add_subplot(111)
        bars = ax.barh(
            top_activity["Activity"].astype(str),
            top_activity["Frequency"],
            color="#6485A5",
            height=0.62,
        )
        ax.bar_label(
            bars,
            labels=[f"{int(v):,}" for v in top_activity["Frequency"]],
            padding=3,
            fontsize=6,
        )
        ax.set_xlabel("Number of Events", fontsize=7)
        ax.tick_params(axis="both", labelsize=7)
        ax.grid(axis="x", linestyle="--", alpha=0.25)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)

        self.activity_figure.subplots_adjust(left=0.34, right=0.98, top=0.97, bottom=0.17)
        self.activity_canvas.draw()

        # All activity frequency
        self.activity_table.setUpdatesEnabled(False)
        self.activity_table.setRowCount(len(activity))
        try:
            for row, record in enumerate(activity.itertuples(index=False)):
                self.activity_table.setItem(row, 0, QTableWidgetItem(str(record[0])))
                self.activity_table.setItem(row, 1, QTableWidgetItem(f"{record[1]:,}"))
        finally:
            self.activity_table.setUpdatesEnabled(True)

        # Case duration (kolom: 0=case, 1=start, 2=end, 6=durasi hari, dari modul overview)
        cases = overview["case_durations"]
        self.case_data = cases
        self.case_model.set_data(
            cases.iloc[:, 0], cases.iloc[:, 1], cases.iloc[:, 2], cases.iloc[:, 6]
        )

        self.status_label.setText("Status: Import and overview successful")
        self.show_page(0)

    # ------------------------------------------------------------------
    # CASE DETAIL (cache groupby + urutan stabil)
    # ------------------------------------------------------------------
    def get_case_groups(self):
        """groupby dibuat sekali per dataset, lalu dipakai ulang tiap double-click."""
        if self._case_groups is None:
            dataframe = self.active_data["import"]["dataframe"]
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                self._case_groups = dataframe.groupby(CASE_COLUMN, sort=False).indices
            finally:
                QApplication.restoreOverrideCursor()
        return self._case_groups

    def on_case_double_clicked(self, index):
        if self.active_data is None or not index.isValid():
            return
        case_id = index.sibling(index.row(), 0).data(Qt.ItemDataRole.DisplayRole)
        self.open_case_detail(case_id)

    def open_case_detail(self, case_id):
        dataframe = self.active_data["import"]["dataframe"]
        positions = self.get_case_groups().get(case_id)
        if positions is None:
            QMessageBox.warning(self, "Case Tidak Ditemukan", f"Case {case_id} tidak ada pada log aktif.")
            return

        # Sort stabil: timestamp sama tetap mengikuti urutan baris file XES.
        events = dataframe.iloc[positions].sort_values(TIMESTAMP_COLUMN, kind="stable")
        CaseDetailDialog(self, case_id, events).exec()

    # ------------------------------------------------------------------
    # EXERCISE 11.7 A-B HANDLERS
    # ------------------------------------------------------------------
    def run_exercise_117(self):
        if self.active_data is None:
            QMessageBox.warning(self, "Dataset Belum Ada", "Impor dataset XES terlebih dahulu.")
            return

        dataframe = self.active_data["import"]["dataframe"]

        self.run_117_button.setEnabled(False)
        self.reset_117_button.setEnabled(False)
        self.export_117_button.setEnabled(False)
        self.progress_117.setVisible(True)
        self.progress_117.setRange(0, 0)
        self.status_117.setText("Status: Menghitung 11.7 A–B...")

        self.worker_117 = Exercise117Worker(dataframe)
        self.worker_117.succeeded.connect(self.on_117_succeeded)
        self.worker_117.failed.connect(self.on_117_failed)
        self.worker_117.finished.connect(self.on_117_finished)
        self.worker_117.start()

    def on_117_succeeded(self, result):
        self.result_117 = result

        summary = result["summary"]
        durations = result["durations"]
        average = summary["average_cycle_time_days"]

        self.metric_117_cases.setText(f"{result['total_cases']:,}")
        self.metric_117_avg.setText(
            f"{average:.2f} days" if average is not None else "Not available"
        )
        self.metric_117_valid.setText(f"{summary['valid_cases']:,}")
        self.metric_117_invalid.setText(f"{summary['invalid_cases']:,}")

        self.case_117_model.set_data(
            durations[CASE_COLUMN],
            durations["start_time"],
            durations["end_time"],
            durations["duration_days"],
        )

        self.status_117.setText(
            f"Status: Selesai — 11.7 A: {result['total_cases']:,} case. "
            f"11.7 B: rata-rata dari {summary['valid_cases']:,} case valid "
            f"(dikecualikan karena timestamp kosong: {summary['invalid_cases']:,})."
        )
        self.export_117_button.setEnabled(True)

    def on_117_failed(self, message):
        self.status_117.setText("Status: Analisis gagal")
        QMessageBox.critical(self, "Analisis Gagal", message)

    def on_117_finished(self):
        self.progress_117.setVisible(False)
        self.progress_117.setRange(0, 1)
        self.progress_117.setValue(0)
        self.run_117_button.setEnabled(self.active_data is not None)
        self.reset_117_button.setEnabled(self.result_117 is not None)

    def reset_117(self, clear_status=True):
        """Kosongkan hasil 11.7 A-B (data log tetap aktif, bisa dihitung ulang)."""
        self.result_117 = None
        for label in (
            self.metric_117_cases,
            self.metric_117_avg,
            self.metric_117_valid,
            self.metric_117_invalid,
        ):
            label.setText("-")

        self.case_117_model.clear()
        self.case_117_search.clear()
        self.export_117_button.setEnabled(False)
        self.reset_117_button.setEnabled(False)

        if clear_status:
            if self.active_data is None:
                self.status_117.setText("Status: Impor dataset terlebih dahulu.")
            else:
                self.status_117.setText("Status: Hasil direset. Klik tombol untuk menghitung ulang.")

    def export_117_csv(self):
        if self.result_117 is None:
            QMessageBox.warning(self, "Belum Ada Data", "Jalankan analisis terlebih dahulu.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Simpan Ringkasan 11.7 A-B", "hasil_11_7_ab.csv", "CSV Files (*.csv)"
        )
        if not file_path:
            return

        summary_path = Path(file_path).with_suffix(".csv")
        cases_path = summary_path.with_name(summary_path.stem + "_case.csv")

        result = self.result_117
        summary = result["summary"]
        average = summary["average_cycle_time_days"]
        dataset_name = self.active_data["import"]["file_name"]

        summary_rows = pd.DataFrame(
            [
                ["Dataset", "File aktif", dataset_name, "", ""],
                ["11.7 A", "Jumlah keseluruhan case", result["total_cases"], "case",
                 "Unique case ID pada log aktif"],
                ["11.7 B", "Rata-rata cycle time",
                 round(average, 4) if average is not None else "", "hari",
                 "Rata-rata (timestamp terakhir - pertama) per case; "
                 f"denominator = {summary['valid_cases']} valid case"],
                ["Info", "Valid cases", summary["valid_cases"], "case",
                 "Semua event case memiliki timestamp"],
                ["Info", "Invalid cases", summary["invalid_cases"], "case",
                 "Memiliki timestamp kosong; dikecualikan dari rata-rata"],
            ],
            columns=["Kode", "Pertanyaan", "Hasil", "Satuan", "Aturan / Denominator"],
        )

        case_rows = result["durations"][
            [CASE_COLUMN, "start_time", "end_time", "duration_days", "is_valid"]
        ]

        try:
            summary_rows.to_csv(summary_path, index=False)
            case_rows.to_csv(cases_path, index=False)
        except Exception as error:
            QMessageBox.critical(self, "Gagal", f"Gagal menyimpan file: {error}")
            return

        QMessageBox.information(
            self,
            "Sukses",
            f"Ringkasan jawaban:\n{summary_path}\n\nDaftar case:\n{cases_path}",
        )

    # ------------------------------------------------------------------
    # ABOUT
    # ------------------------------------------------------------------
    def show_about(self):
        def version(package):
            try:
                return importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                return "tidak terpasang"

        QMessageBox.information(
            self,
            "About BPIC17 Analyzer",
            f"Python: {platform.python_version()}\n"
            f"PM4Py: {version('pm4py')}\n"
            f"pandas: {version('pandas')}\n"
            f"PySide6: {version('PySide6')}\n"
            f"matplotlib: {version('matplotlib')}",
        )


# ======================================================================
# RUN APPLICATION
# ======================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())