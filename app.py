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
from PySide6.QtGui import QFont, QFontMetrics
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
    QComboBox,
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
from modules.exercise_11_7_ce import analyze_117_ce
from modules.exercise_11_15_18 import (
    analyze_1115_1118,
    detect_target_activity,
    list_activities,
)
from modules.exercise_11_22 import analyze_1122

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



class Exercise117CEWorker(QThread):
    """Menghitung Exercise 11.7 C-E di background thread."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, dataframe):
        super().__init__()
        self.dataframe = dataframe

    def run(self):
        try:
            self.succeeded.emit(analyze_117_ce(self.dataframe))
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")


class Exercise1518Worker(QThread):
    """Menghitung Exercise 11.15 & 11.18 di background thread (Annis)."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, dataframe, activity):
        super().__init__()
        self.dataframe = dataframe
        self.activity = activity

    def run(self):
        try:
            self.succeeded.emit(analyze_1115_1118(self.dataframe, self.activity))
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")

class Exercise1122Worker(QThread):
    """Menghitung Exercise 11.22 di background thread (Kayla)."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, dataframe):
        super().__init__()
        self.dataframe = dataframe

    def run(self):
        try:
            self.succeeded.emit(analyze_1122(self.dataframe))
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")

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
        self.worker_117_ce = None
        self.case_data = None
        self.result_117 = None      # hasil analisis 11.7 A-B yang sedang tampil
        self.result_117_ce = None   # hasil analisis 11.7 C-E milik Hana
        self.worker_1518 = None
        self.result_1518 = None     # hasil analisis 11.15 & 11.18 milik Annis
        self.worker_1122 = None
        self.result_1122 = None     
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
        self.nav_1518 = QPushButton("Exercise 11.15 && 11.18")  # && = '&' literal
        self.nav_1122 = QPushButton("Exercise 11.22")
        self.nav_explorer = QPushButton("Case Explorer")
        self.nav_dataset = QPushButton("Dataset")

        self.nav_overview.clicked.connect(lambda: self.show_page(0))
        self.nav_dataset.clicked.connect(lambda: self.show_page(1))
        self.nav_117.clicked.connect(lambda: self.show_page(2))
        self.nav_1518.clicked.connect(lambda: self.show_page(3))
        self.nav_1122.clicked.connect(lambda: self.show_page(4))
        self.nav_explorer.clicked.connect(lambda: self.show_page(5))

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
            # Tombol aktif memakai teks bold; beri lebar minimum agar teks tidak terpotong.
            bold = QFont("Segoe UI", 9)
            bold.setBold(True)
            label = button.text().replace("&&", "&")
            text_width = QFontMetrics(bold).horizontalAdvance(label) + 6
            button.setStyleSheet(f"min-width: {max(75, text_width)}px;")
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
        self.exercise_1518_page = self.create_exercise_1518_page()
        self.exercise_1122_page = self.create_exercise_1122_page()
        self.case_explorer_page = self.create_case_explorer_page()

        self.pages.addWidget(self.overview_page)       # index 0
        self.pages.addWidget(self.dataset_page)        # index 1
        self.pages.addWidget(self.exercise_117_page)   # index 2
        self.pages.addWidget(self.exercise_1518_page)  # index 3
        self.pages.addWidget(self.exercise_1122_page)  # index 4
        self.pages.addWidget(self.case_explorer_page)  # index 5

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

            QLineEdit, QComboBox {
                background-color: white; border: 1px solid #C9D2DD;
                padding: 8px; border-radius: 4px;
            }
            QComboBox:disabled { color: #AAB4C0; }

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
        self.nav_1518.setChecked(index == 3)
        self.nav_1122.setChecked(index == 4)
        self.nav_explorer.setChecked(index == 5)

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

        # ---------------- Bagian C-E (Hana) ----------------
        section_ce = QLabel("Bagian C–E: Successful, Unsuccessful, dan Canceled Cases")
        section_ce.setObjectName("sectionTitle")
        layout.addWidget(section_ce)

        rules_ce = QLabel(
            "11.7 C: case mengandung minimal satu O_Accepted (contains).  "
            "11.7 D: case mengandung minimal satu O_Refused (contains).  "
            "11.7 E: event terakhir pada trace harus O_Cancelled (endpoint). "
            "Successful dan unsuccessful tidak harus saling eksklusif."
        )
        rules_ce.setWordWrap(True)
        rules_ce.setStyleSheet("color: #4A5568; font-style: italic;")
        layout.addWidget(rules_ce)

        ce_actions = QHBoxLayout()
        self.run_117_ce_button = QPushButton("Hitung 11.7 C–E")
        self.run_117_ce_button.setEnabled(False)
        self.run_117_ce_button.clicked.connect(self.run_exercise_117_ce)
        ce_actions.addWidget(self.run_117_ce_button)

        self.reset_117_ce_button = QPushButton("Reset C–E")
        self.reset_117_ce_button.setEnabled(False)
        self.reset_117_ce_button.clicked.connect(self.reset_117_ce)
        ce_actions.addWidget(self.reset_117_ce_button)

        self.export_117_ce_button = QPushButton("Export C–E to CSV")
        self.export_117_ce_button.setEnabled(False)
        self.export_117_ce_button.clicked.connect(self.export_117_ce_csv)
        ce_actions.addWidget(self.export_117_ce_button)
        layout.addLayout(ce_actions)

        self.status_117_ce = QLabel("Status: Impor dataset terlebih dahulu.")
        self.status_117_ce.setWordWrap(True)
        self.status_117_ce.setStyleSheet("color: #718096;")
        layout.addWidget(self.status_117_ce)

        ce_metrics = QGridLayout()
        ce_metrics.setSpacing(10)
        self.metric_ce_success = self.create_metric_card(ce_metrics, 0, "Successful Cases")
        self.metric_ce_success_avg = self.create_metric_card(ce_metrics, 1, "Successful Avg. Days")
        self.metric_ce_refused = self.create_metric_card(ce_metrics, 2, "Unsuccessful Cases")
        self.metric_ce_refused_avg = self.create_metric_card(ce_metrics, 3, "Unsuccessful Avg. Days")
        self.metric_ce_canceled = self.create_metric_card(ce_metrics, 4, "Canceled Cases")
        self.metric_ce_canceled_avg = self.create_metric_card(ce_metrics, 5, "Canceled Avg. Days")
        for column in range(6):
            ce_metrics.setColumnStretch(column, 1)
        layout.addLayout(ce_metrics)

        evidence_panel = self.create_panel(
            "Hasil Kategori dan Bukti Event — double-click Case ID untuk melihat seluruh urutan event"
        )
        self.table_117_ce = QTableWidget(0, 5)
        self.table_117_ce.setHorizontalHeaderLabels([
            "Kategori", "Case ID", "Evidence Activity", "Timestamp", "Resource"
        ])
        self.table_117_ce.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table_117_ce.setAlternatingRowColors(True)
        self.table_117_ce.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_117_ce.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table_117_ce.setMinimumHeight(300)
        self.table_117_ce.doubleClicked.connect(
            self.open_117_ce_case_detail
        )
        evidence_panel.layout().addWidget(self.table_117_ce)
        layout.addWidget(evidence_panel)

        layout.addStretch()

        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        return page

    # ------------------------------------------------------------------
    # EXERCISE 11.15 & 11.18 PAGE (Annis) - F04, F05
    # ------------------------------------------------------------------
    def create_simple_table(self, headers, min_height, on_double_click=None):
        """QTableWidget read-only dengan header (dipakai halaman 11.15 & 11.18)."""
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.verticalHeader().setDefaultSectionSize(25)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setMinimumHeight(min_height)
        if on_double_click is not None:
            table.doubleClicked.connect(on_double_click)
        return table

    @staticmethod
    def fill_table(table, rows):
        """Isi QTableWidget dari list of list (nilai sudah berupa teks)."""
        table.setUpdatesEnabled(False)
        try:
            table.clearContents()
            table.setRowCount(len(rows))
            for row_index, values in enumerate(rows):
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(value)
                    cell.setToolTip(value)  # teks panjang tetap terbaca utuh
                    table.setItem(row_index, column, cell)
        finally:
            table.setUpdatesEnabled(True)

    def create_exercise_1518_page(self):
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

        heading = QLabel("Exercise 11.15 & 11.18")
        heading.setStyleSheet("font-size: 17px; font-weight: bold;")
        layout.addWidget(heading)

        rules = QLabel(
            "11.15: case di mana aktivitas target diselesaikan minimal 2× — hanya event dengan "
            "lifecycle:transition = complete yang dihitung (schedule, start, suspend, resume, "
            "ate_abort, withdraw diabaikan).\n"
            "11.18: dari case 11.15, minimal 2 complete occurrence dilakukan oleh org:resource "
            "yang sama. Resource kosong/UNKNOWN tidak pernah dianggap sebagai resource yang sama.\n"
            "Setiap case dihitung satu kali; tidak ada event yang dihapus dari trace. Catatan: "
            "pada BPIC17 ejaan aktivitasnya 'W_Assess potential fraud' (huruf kecil), sehingga "
            "aktivitas target dipilih dari daftar aktivitas log dengan deteksi otomatis."
        )
        rules.setWordWrap(True)
        rules.setStyleSheet("color: #4A5568; font-style: italic; margin-bottom: 6px;")
        layout.addWidget(rules)

        # Pilihan aktivitas + tombol aksi
        action_layout = QHBoxLayout()
        activity_label = QLabel("Aktivitas target:")
        activity_label.setStyleSheet("background: transparent;")
        action_layout.addWidget(activity_label)

        self.activity_1518_combo = QComboBox()
        self.activity_1518_combo.setEnabled(False)
        self.activity_1518_combo.setMinimumWidth(280)
        action_layout.addWidget(self.activity_1518_combo, 1)

        self.run_1518_button = QPushButton("Hitung 11.15 && 11.18")  # && = '&' literal
        self.run_1518_button.setEnabled(False)
        self.run_1518_button.clicked.connect(self.run_exercise_1518)
        action_layout.addWidget(self.run_1518_button)

        self.reset_1518_button = QPushButton("Reset")
        self.reset_1518_button.setEnabled(False)
        self.reset_1518_button.clicked.connect(self.reset_1518)
        action_layout.addWidget(self.reset_1518_button)

        self.export_1518_button = QPushButton("Export to CSV")
        self.export_1518_button.setEnabled(False)
        self.export_1518_button.clicked.connect(self.export_1518_csv)
        action_layout.addWidget(self.export_1518_button)
        layout.addLayout(action_layout)

        self.progress_1518 = QProgressBar()
        self.progress_1518.setRange(0, 1)
        self.progress_1518.setVisible(False)
        layout.addWidget(self.progress_1518)

        self.status_1518 = QLabel("Status: Impor dataset terlebih dahulu.")
        self.status_1518.setWordWrap(True)
        self.status_1518.setStyleSheet("color: #718096;")
        layout.addWidget(self.status_1518)

        metrics_layout = QGridLayout()
        metrics_layout.setSpacing(10)
        self.metric_1515_cases = self.create_metric_card(
            metrics_layout, 0, "11.15 — Case complete ≥ 2×"
        )
        self.metric_1518_cases = self.create_metric_card(
            metrics_layout, 1, "11.18 — Case resource sama"
        )
        self.metric_1518_events = self.create_metric_card(
            metrics_layout, 2, "Event target (semua / complete)"
        )
        self.metric_1518_total = self.create_metric_card(
            metrics_layout, 3, "Total case log aktif"
        )
        for column in range(4):
            metrics_layout.setColumnStretch(column, 1)
        layout.addLayout(metrics_layout)

        # ---------------- 11.15 ----------------
        panel_1515 = self.create_panel(
            "11.15 — Case terpilih (klik untuk melihat bukti event, double-click untuk seluruh trace)"
        )
        self.table_1515_cases = self.create_simple_table(
            ["Case ID", "Jumlah complete", "Semua event target", "Rincian lifecycle"],
            170,
            self.open_1518_case_detail,
        )
        self.table_1515_cases.itemSelectionChanged.connect(
            lambda: self.show_1518_evidence("ex_1115")
        )
        panel_1515.layout().addWidget(self.table_1515_cases)

        evidence_note = QLabel(
            "Bukti event 11.15: seluruh event aktivitas target pada case terpilih. "
            "Kolom 'Dihitung' = Ya hanya untuk lifecycle complete."
        )
        evidence_note.setWordWrap(True)
        evidence_note.setStyleSheet("color: #4A5568; background: transparent;")
        panel_1515.layout().addWidget(evidence_note)

        self.table_1515_evidence = self.create_simple_table(
            ["Posisi di trace", "Timestamp", "Activity", "Lifecycle", "Resource", "Dihitung"],
            200,
        )
        panel_1515.layout().addWidget(self.table_1515_evidence)
        layout.addWidget(panel_1515)

        # ---------------- 11.18 ----------------
        panel_1518 = self.create_panel(
            "11.18 — Case dengan resource sama (klik untuk bukti, double-click untuk seluruh trace)"
        )
        self.table_1518_cases = self.create_simple_table(
            ["Case ID", "Resource ID", "Jumlah complete oleh resource"],
            120,
            self.open_1518_case_detail,
        )
        self.table_1518_cases.itemSelectionChanged.connect(
            lambda: self.show_1518_evidence("ex_1118")
        )
        panel_1518.layout().addWidget(self.table_1518_cases)

        self.table_1518_evidence = self.create_simple_table(
            ["Posisi di trace", "Timestamp", "Activity", "Lifecycle", "Resource", "Dihitung"],
            120,
        )
        panel_1518.layout().addWidget(self.table_1518_evidence)
        layout.addWidget(panel_1518)

        # ---------------- Pembanding ----------------
        panel_compare = self.create_panel(
            "Analisis tambahan — pembanding per lifecycle"
        )
        compare_note = QLabel(
            "Tabel ini menunjukkan mengapa pembatasan lifecycle penting. Buku FBPM (Solution "
            "11.15/11.18) melaporkan Celonis 13 dan 3 case (complete saja), sedangkan Disco 20 "
            "dan 8 case karena ikut menghitung event schedule/start/abort."
        )
        compare_note.setWordWrap(True)
        compare_note.setStyleSheet("color: #4A5568; background: transparent;")
        panel_compare.layout().addWidget(compare_note)

        self.table_1518_compare = self.create_simple_table(
            ["Lifecycle", "Jumlah event", "Case memuat event", "Case ≥ 2 event",
             "Case ≥ 2 oleh resource sama"],
            265,
        )
        panel_compare.layout().addWidget(self.table_1518_compare)
        layout.addWidget(panel_compare)

        layout.addStretch()
        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        return page

    # ------------------------------------------------------------------
    # EXERCISE 11.22 PAGE - Kayla
    # ------------------------------------------------------------------
    def create_exercise_1122_page(self):
        page = QWidget()

        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(22, 20, 22, 20)
        page_layout.setSpacing(12)

        heading = QLabel("Exercise 11.22")
        heading.setStyleSheet("font-size: 19px; font-weight: bold;")
        page_layout.addWidget(heading)

        description = QLabel(
            "Mencari case yang memiliki O_Cancelled kemudian O_Accepted "
            "dalam trace yang sama."
        )
        description.setWordWrap(True)
        page_layout.addWidget(description)

        rule = QLabel(
            "Aturan: O_Cancelled harus terjadi lebih dahulu daripada O_Accepted. "
            "Kedua event tidak harus berurutan langsung."
        )
        rule.setWordWrap(True)
        rule.setStyleSheet(
            "color: #4A5568; background: #E9EEF5; "
            "padding: 10px; border-radius: 6px;"
        )
        page_layout.addWidget(rule)

        # ---------------- ACTIONS ----------------
        action_layout = QHBoxLayout()

        self.run_1122_button = QPushButton("Hitung 11.22")
        self.run_1122_button.clicked.connect(self.run_exercise_1122)

        self.reset_1122_button = QPushButton("Reset")
        self.reset_1122_button.clicked.connect(self.reset_1122)
        self.reset_1122_button.setEnabled(False)

        self.export_1122_button = QPushButton("Export CSV")
        self.export_1122_button.clicked.connect(self.export_1122_csv)
        self.export_1122_button.setEnabled(False)

        action_layout.addWidget(self.run_1122_button)
        action_layout.addWidget(self.reset_1122_button)
        action_layout.addWidget(self.export_1122_button)
        action_layout.addStretch()

        page_layout.addLayout(action_layout)

        # ---------------- STATUS ----------------
        self.progress_1122 = QProgressBar()
        self.progress_1122.setRange(0, 1)
        self.progress_1122.setValue(0)
        self.progress_1122.setVisible(False)
        page_layout.addWidget(self.progress_1122)

        self.status_1122 = QLabel("Status: Impor dataset terlebih dahulu.")
        self.status_1122.setWordWrap(True)
        page_layout.addWidget(self.status_1122)

        # ---------------- METRICS ----------------
        metrics = QGridLayout()
        metrics.setSpacing(10)

        self.metric_1122_matched = self.create_metric_card(
            metrics, 0, "Case Memenuhi 11.22"
        )
        self.metric_1122_total = self.create_metric_card(
            metrics, 1, "Total Active Cases"
        )
        self.metric_1122_percentage = self.create_metric_card(
            metrics, 2, "Persentase"
        )

        self.metric_1122_matched.setText("-")
        self.metric_1122_total.setText("-")
        self.metric_1122_percentage.setText("-")

        page_layout.addLayout(metrics)

        # ---------------- EVIDENCE ----------------
        panel = self.create_panel(
            "Bukti Case — O_Cancelled kemudian O_Accepted "
            "(double-click untuk melihat seluruh trace)"
        )

        self.table_1122_cases = self.create_simple_table(
            [
                "Case ID",
                "O_Cancelled Timestamp",
                "O_Accepted Timestamp",
            ],
            350,
            self.open_1122_case_detail,
        )

        panel.layout().addWidget(self.table_1122_cases)
        page_layout.addWidget(panel)

        page_layout.addStretch()

        self.run_1122_button.setEnabled(False)

        return page

    # ------------------------------------------------------------------
    # CASE EXPLORER HANDLERS - Kayla
    # ------------------------------------------------------------------
    def filter_case_explorer(self, search_text):
        search_text = search_text.strip().lower()

        for row in range(self.case_explorer_table.rowCount()):
            item = self.case_explorer_table.item(row, 0)

            if item is not None:
                case_id = item.text().lower()

                self.case_explorer_table.setRowHidden(
                    row,
                    search_text not in case_id
                )

    def open_case_explorer_detail(self, index):
        if self.active_data is None or not index.isValid():
            return

        item = self.case_explorer_table.item(index.row(), 0)

        if item is not None:
            self.open_case_detail(item.text())

    def export_case_explorer_csv(self):
        if self.active_data is None:
            QMessageBox.warning(
                self,
                "Dataset Belum Ada",
                "Impor dataset XES terlebih dahulu.",
            )
            return

        case_ids = list(self.get_case_groups().keys())

        matched_cases = set()

        if self.result_1122 is not None:
            matched_cases = set(self.result_1122["case_ids"])

        statuses = []

        for case_id in case_ids:
            if self.result_1122 is None:
                status = "Belum Dianalisis"
            elif case_id in matched_cases:
                status = "Memenuhi"
            else:
                status = "Tidak Memenuhi"

            statuses.append(status)

        export_dataframe = pd.DataFrame({
            "Case ID": case_ids,
            "Status 11.22": statuses,
        })

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Daftar Case",
            "case_explorer.csv",
            "CSV Files (*.csv)",
        )

        if not file_path:
            return

        export_dataframe.to_csv(
            file_path,
            index=False,
            encoding="utf-8-sig",
        )

        QMessageBox.information(
            self,
            "Export Berhasil",
            f"Daftar {len(case_ids):,} case berhasil diekspor.",
        )

    # ------------------------------------------------------------------
    # EXERCISE 11.22 HANDLERS (Kayla)
    # ------------------------------------------------------------------
    def run_exercise_1122(self):
        if self.active_data is None:
            QMessageBox.warning(
                self,
                "Dataset Belum Ada",
                "Impor dataset XES terlebih dahulu.",
            )
            return

        self.reset_1122(clear_status=False)
        self.run_1122_button.setEnabled(False)
        self.progress_1122.setVisible(True)
        self.progress_1122.setRange(0, 0)
        self.status_1122.setText(
            "Status: Menghitung case O_Cancelled kemudian O_Accepted..."
        )

        dataframe = self.active_data["import"]["dataframe"]

        self.worker_1122 = Exercise1122Worker(dataframe)
        self.worker_1122.succeeded.connect(self.on_1122_succeeded)
        self.worker_1122.failed.connect(self.on_1122_failed)
        self.worker_1122.finished.connect(self.on_1122_finished)
        self.worker_1122.start()

    def on_1122_succeeded(self, result):
        self.result_1122 = result
        self.load_case_explorer()

        summary = result["summary"]
        evidence = result["evidence"]

        self.metric_1122_matched.setText(
            f"{summary['matched_cases']:,}"
        )
        self.metric_1122_total.setText(
            f"{summary['total_cases']:,}"
        )
        self.metric_1122_percentage.setText(
            f"{summary['percentage']:.2f}%"
        )

        timestamps_cancelled = format_datetime_series(
            evidence["cancelled_timestamp"]
        ).tolist()

        timestamps_accepted = format_datetime_series(
            evidence["accepted_timestamp"]
        ).tolist()

        self.fill_table(
            self.table_1122_cases,
            [
                [
                    str(row[CASE_COLUMN]),
                    cancelled_timestamp,
                    accepted_timestamp,
                ]
                for row, cancelled_timestamp, accepted_timestamp in zip(
                    evidence.to_dict("records"),
                    timestamps_cancelled,
                    timestamps_accepted,
                )
            ],
        )

        if self.table_1122_cases.rowCount():
            self.table_1122_cases.selectRow(0)

        self.status_1122.setText(
            f"Status: Selesai. Ditemukan {summary['matched_cases']:,} "
            f"case dari {summary['total_cases']:,} active cases "
            f"({summary['percentage']:.2f}%) yang memiliki "
            "O_Cancelled sebelum O_Accepted."
        )

        self.export_1122_button.setEnabled(True)

    def open_1122_case_detail(self, index):
        if self.active_data is None or not index.isValid():
            return

        table = self.sender()
        item = table.item(index.row(), 0) if table is not None else None

        if item is not None:
            self.open_case_detail(item.text())

    def on_1122_failed(self, message):
        self.status_1122.setText("Status: Analisis 11.22 gagal.")
        QMessageBox.critical(
            self,
            "Analisis 11.22 Gagal",
            message,
        )

    def on_1122_finished(self):
        self.progress_1122.setVisible(False)
        self.progress_1122.setRange(0, 1)

        self.run_1122_button.setEnabled(
            self.active_data is not None
        )

        self.reset_1122_button.setEnabled(
            self.result_1122 is not None
        )

    def reset_1122(self, clear_status=True):
        """Reset hasil 11.22 tanpa menghapus dataset aktif."""
        self.result_1122 = None

        if self.active_data is not None:
            self.load_case_explorer()

        self.metric_1122_matched.setText("-")
        self.metric_1122_total.setText("-")
        self.metric_1122_percentage.setText("-")

        self.table_1122_cases.setRowCount(0)

        self.export_1122_button.setEnabled(False)
        self.reset_1122_button.setEnabled(False)

        if clear_status:
            self.status_1122.setText(
                "Status: Impor dataset terlebih dahulu."
                if self.active_data is None
                else "Status: Hasil direset. Klik Hitung 11.22 untuk menghitung ulang."
            )

    def export_1122_csv(self):
        if self.result_1122 is None:
            QMessageBox.warning(
                self,
                "Belum Ada Data",
                "Jalankan analisis 11.22 terlebih dahulu.",
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Simpan Hasil 11.22",
            "hasil_11_22.csv",
            "CSV Files (*.csv)",
        )

        if not file_path:
            return

        summary_path = Path(file_path)
        evidence_path = summary_path.with_name(
            summary_path.stem + "_evidence.csv"
        )

        result = self.result_1122
        summary = result["summary"]

        summary_dataframe = pd.DataFrame([
            {
                "rule": result["rule"],
                "matched_cases": summary["matched_cases"],
                "total_active_cases": summary["total_cases"],
                "percentage": summary["percentage"],
            }
        ])

        summary_dataframe.to_csv(
            summary_path,
            index=False,
            encoding="utf-8-sig",
        )

        result["evidence"].to_csv(
            evidence_path,
            index=False,
            encoding="utf-8-sig",
        )

        QMessageBox.information(
            self,
            "Export Berhasil",
            f"Hasil 11.22 berhasil disimpan.\n\n"
            f"Ringkasan: {summary_path.name}\n"
            f"Bukti case: {evidence_path.name}",
        )

    # ------------------------------------------------------------------
    # CASE EXPLORER PAGE - Kayla
    # ------------------------------------------------------------------
    def create_case_explorer_page(self):
        page = QWidget()

        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(22, 20, 22, 20)
        page_layout.setSpacing(12)

        heading = QLabel("Case Explorer")
        heading.setStyleSheet("font-size: 19px; font-weight: bold;")
        page_layout.addWidget(heading)

        description = QLabel(
            "Digunakan untuk mencari dan melihat detail case "
            "dari event log yang sedang aktif."
        )
        description.setWordWrap(True)
        page_layout.addWidget(description)

        # ---------------- SEARCH ----------------
        search_layout = QHBoxLayout()

        search_label = QLabel("Cari Case ID:")
        self.case_explorer_search = QLineEdit()
        self.case_explorer_search.setPlaceholderText(
            "Masukkan Case ID..."
        )

        self.case_explorer_search.textChanged.connect(
            self.filter_case_explorer
        )

        self.export_case_explorer_button = QPushButton("Export CSV")
        self.export_case_explorer_button.clicked.connect(
            self.export_case_explorer_csv
        )
        self.export_case_explorer_button.setEnabled(False)

        search_layout.addWidget(search_label)
        search_layout.addWidget(self.case_explorer_search)
        search_layout.addWidget(self.export_case_explorer_button)

        page_layout.addLayout(search_layout)

        # ---------------- CASE TABLE ----------------
        panel = self.create_panel("Daftar Case")

        self.case_explorer_table = self.create_simple_table(
            ["Case ID", "Status 11.22"],
            400,
            self.open_case_explorer_detail,
        )

        panel.layout().addWidget(self.case_explorer_table)
        page_layout.addWidget(panel)

        page_layout.addStretch()

        return page

    def load_case_explorer(self):
        if self.active_data is None:
            return

        dataframe = self.active_data["import"]["dataframe"]
        case_ids = dataframe[CASE_COLUMN].dropna().unique()

        matched_cases = set()

        if self.result_1122 is not None:
            matched_cases = set(self.result_1122["case_ids"])

        rows = []

        for case_id in case_ids:
            if self.result_1122 is None:
                status = "Belum Dianalisis"
            elif case_id in matched_cases:
                status = "Memenuhi"
            else:
                status = "Tidak Memenuhi"

            rows.append([str(case_id), status])

        self.fill_table(self.case_explorer_table, rows)

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
        self.load_case_explorer()
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
        self.reset_117_ce(clear_status=False)

        self.reset_1122(clear_status=False)
        self.run_1122_button.setEnabled(True)
        self.status_1122.setText(
            "Status: Dataset siap. Klik Hitung 11.22 untuk menjalankan analisis."
        )
        
        self.run_117_button.setEnabled(True)
        self.run_117_ce_button.setEnabled(True)
        self.status_117.setText(
            f"Status: Dataset siap ({imported['total_cases']:,} case). "
            "Klik tombol untuk menghitung."
        )
        self.status_117_ce.setText(
            f"Status: Dataset siap ({imported['total_cases']:,} case). Klik Hitung 11.7 C–E."
        )

        # Exercise 11.15 & 11.18: isi daftar aktivitas, deteksi target otomatis
        self.prepare_1518(imported)

        self.export_case_explorer_button.setEnabled(True)

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

    # ------------------------------------------------------------------
    # EXERCISE 11.7 C-E HANDLERS (Hana)
    # ------------------------------------------------------------------
    def run_exercise_117_ce(self):
        if self.active_data is None:
            QMessageBox.warning(self, "Dataset Belum Ada", "Impor dataset XES terlebih dahulu.")
            return

        self.run_117_ce_button.setEnabled(False)
        self.reset_117_ce_button.setEnabled(False)
        self.export_117_ce_button.setEnabled(False)
        self.status_117_ce.setText(
            "Status: Menghitung successful, unsuccessful, dan canceled cases..."
        )

        dataframe = self.active_data["import"]["dataframe"]
        self.worker_117_ce = Exercise117CEWorker(dataframe)
        self.worker_117_ce.succeeded.connect(self.on_117_ce_succeeded)
        self.worker_117_ce.failed.connect(self.on_117_ce_failed)
        self.worker_117_ce.finished.connect(self.on_117_ce_finished)
        self.worker_117_ce.start()

    def on_117_ce_succeeded(self, result):
        self.result_117_ce = result
        categories = [
            ("successful", "Successful"),
            ("unsuccessful", "Unsuccessful"),
            ("canceled", "Canceled"),
        ]

        self.table_117_ce.setRowCount(0)
        for key, category_name in categories:
            item = result[key]
            summary = item["summary"]
            average = summary["average_cycle_time_days"]

            if key == "successful":
                count_label, avg_label = self.metric_ce_success, self.metric_ce_success_avg
            elif key == "unsuccessful":
                count_label, avg_label = self.metric_ce_refused, self.metric_ce_refused_avg
            else:
                count_label, avg_label = self.metric_ce_canceled, self.metric_ce_canceled_avg

            count_label.setText(f"{summary['total_cases']:,}")
            avg_label.setText(f"{average:.2f}" if average is not None else "N/A")

            # Satu tabel memuat kategori, Case ID, dan bukti event.
            # Case ID dapat di-double-click untuk membuka seluruh trace.
            for _, event in item["evidence"].iterrows():
                row = self.table_117_ce.rowCount()
                self.table_117_ce.insertRow(row)

                case_id = str(event[CASE_COLUMN])
                values = [
                    category_name,
                    case_id,
                    str(event["concept:name"]),
                    str(event[TIMESTAMP_COLUMN]) if pd_not_null(event[TIMESTAMP_COLUMN]) else "",
                    str(event["org:resource"]) if pd_not_null(event["org:resource"]) else "",
                ]
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(value)
                    if column == 1:
                        cell.setData(Qt.ItemDataRole.UserRole, case_id)
                        cell.setToolTip("Double-click untuk membuka seluruh urutan event case ini.")
                    self.table_117_ce.setItem(row, column, cell)

        self.status_117_ce.setText(
            "Status: Selesai. Setiap case dihitung satu kali per kategori; "
        )
        self.export_117_ce_button.setEnabled(True)
        self.reset_117_ce_button.setEnabled(True)

    def open_117_ce_case_detail(self, index):
        """Buka seluruh urutan event untuk Case ID yang dipilih."""
        if self.active_data is None or not index.isValid():
            return

        case_item = self.table_117_ce.item(index.row(), 1)
        if case_item is None:
            return

        case_id = case_item.data(Qt.ItemDataRole.UserRole)
        dataframe = self.active_data["import"]["dataframe"]
        events = dataframe.loc[dataframe[CASE_COLUMN].astype(str) == str(case_id)].copy()

        if events.empty:
            QMessageBox.information(
                self, "Case Tidak Ditemukan",
                f"Data untuk Case ID {case_id} tidak ditemukan pada dataset aktif."
            )
            return

        # Gunakan urutan timestamp stabil; timestamp sama mempertahankan urutan XES.
        events = events.sort_values(
            TIMESTAMP_COLUMN, kind="stable", na_position="last"
        )
        CaseDetailDialog(self, case_id, events).exec()

    def on_117_ce_failed(self, message):
        self.status_117_ce.setText("Status: Analisis 11.7 C–E gagal.")
        QMessageBox.critical(self, "Analisis 11.7 C–E Gagal", message)

    def on_117_ce_finished(self):
        self.run_117_ce_button.setEnabled(self.active_data is not None)

    def reset_117_ce(self, clear_status=True):
        self.result_117_ce = None
        for label in (
            self.metric_ce_success, self.metric_ce_success_avg,
            self.metric_ce_refused, self.metric_ce_refused_avg,
            self.metric_ce_canceled, self.metric_ce_canceled_avg,
        ):
            label.setText("-")
        self.table_117_ce.setRowCount(0)
        self.reset_117_ce_button.setEnabled(False)
        self.export_117_ce_button.setEnabled(False)
        if clear_status:
            self.status_117_ce.setText(
                "Status: Impor dataset terlebih dahulu."
                if self.active_data is None
                else "Status: Hasil C–E direset. Klik tombol untuk menghitung ulang."
            )

    def export_117_ce_csv(self):
        if self.result_117_ce is None:
            QMessageBox.warning(self, "Belum Ada Data", "Jalankan analisis terlebih dahulu.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Simpan Evidence 11.7 C-E", "hasil_11_7_ce.csv", "CSV Files (*.csv)"
        )
        if not file_path:
            return

        rows = []
        for key, label in (
            ("successful", "11.7 C — Successful"),
            ("unsuccessful", "11.7 D — Unsuccessful"),
            ("canceled", "11.7 E — Canceled"),
        ):
            item = self.result_117_ce[key]
            summary = item["summary"]
            for _, event in item["evidence"].iterrows():
                rows.append({
                    "Kategori": label,
                    "Jumlah case kategori": summary["total_cases"],
                    "Rata-rata cycle time (hari)": summary["average_cycle_time_days"],
                    "Case ID": event[CASE_COLUMN],
                    "Timestamp evidence": event[TIMESTAMP_COLUMN],
                    "Activity evidence": event["concept:name"],
                    "Resource": event["org:resource"],
                    "Aturan": item["rule"],
                })

        try:
            pd.DataFrame(rows).to_csv(Path(file_path).with_suffix(".csv"), index=False)
        except Exception as error:
            QMessageBox.critical(self, "Gagal", f"Gagal menyimpan CSV: {error}")
            return

        QMessageBox.information(self, "Sukses", "Evidence 11.7 C–E berhasil diekspor.")

    # ------------------------------------------------------------------
    # EXERCISE 11.15 & 11.18 HANDLERS (Annis)
    # ------------------------------------------------------------------
    def prepare_1518(self, imported):
        """Dipanggil setelah impor: isi dropdown aktivitas dan reset hasil lama."""
        self.reset_1518(clear_status=False)
        dataframe = imported["dataframe"]

        self.activity_1518_combo.clear()
        self.activity_1518_combo.addItems(list_activities(dataframe))
        detected = detect_target_activity(dataframe)
        if detected is not None:
            self.activity_1518_combo.setCurrentText(detected)

        has_lifecycle = "lifecycle:transition" in imported["available_optional"]
        self.activity_1518_combo.setEnabled(True)
        self.run_1518_button.setEnabled(has_lifecycle)

        if not has_lifecycle:
            self.status_1518.setText(
                "Status: Atribut lifecycle:transition tidak tersedia — complete occurrence "
                "tidak dapat diidentifikasi, 11.15 & 11.18 tidak dapat dihitung."
            )
        elif detected is None:
            self.status_1518.setText(
                "Status: 'W_Assess Potential Fraud' tidak ditemukan otomatis. "
                "Pilih aktivitas target secara manual, lalu klik Hitung."
            )
        else:
            self.status_1518.setText(
                f"Status: Dataset siap. Aktivitas target terdeteksi: '{detected}'. "
                "Klik Hitung 11.15 & 11.18."
            )

    def run_exercise_1518(self):
        if self.active_data is None:
            QMessageBox.warning(self, "Dataset Belum Ada", "Impor dataset XES terlebih dahulu.")
            return
        activity = self.activity_1518_combo.currentText()
        if not activity:
            QMessageBox.warning(self, "Aktivitas Belum Dipilih", "Pilih aktivitas target.")
            return

        self.reset_1518(clear_status=False)
        self.run_1518_button.setEnabled(False)
        self.activity_1518_combo.setEnabled(False)
        self.progress_1518.setVisible(True)
        self.progress_1518.setRange(0, 0)
        self.status_1518.setText(f"Status: Menghitung 11.15 & 11.18 untuk '{activity}'...")

        dataframe = self.active_data["import"]["dataframe"]
        self.worker_1518 = Exercise1518Worker(dataframe, activity)
        self.worker_1518.succeeded.connect(self.on_1518_succeeded)
        self.worker_1518.failed.connect(self.on_1518_failed)
        self.worker_1518.finished.connect(self.on_1518_finished)
        self.worker_1518.start()

    @staticmethod
    def _text(value):
        return str(value) if pd_not_null(value) else "-"

    def on_1518_succeeded(self, result):
        self.result_1518 = result
        ex_1515 = result["ex_1115"]
        ex_1518 = result["ex_1118"]
        total_cases = result["total_cases_log"]
        comparison = result["comparison"]
        complete_rows = comparison.loc[comparison["lifecycle"] == "complete", "event_count"]
        complete_events = int(complete_rows.iloc[0]) if not complete_rows.empty else 0

        self.metric_1515_cases.setText(f"{ex_1515['total_cases']:,}")
        self.metric_1518_cases.setText(
            f"{ex_1518['total_cases']:,}" if result["resource_available"] else "N/A"
        )
        self.metric_1518_events.setText(f"{result['target_events']:,} / {complete_events:,}")
        self.metric_1518_total.setText(f"{total_cases:,}")

        self.fill_table(self.table_1515_cases, [
            [str(row.iloc[0]), str(row["complete_count"]),
             str(row["target_events_all_lifecycle"]), str(row["lifecycle_detail"])]
            for _, row in ex_1515["per_case"].iterrows()
        ])
        self.fill_table(self.table_1518_cases, [
            [str(row.iloc[0]), self._text(row["org:resource"]), str(row["complete_count"])]
            for _, row in ex_1518["per_case"].iterrows()
        ])
        self.fill_table(self.table_1518_compare, [
            [str(row["lifecycle"]) + (" " if row["lifecycle"] == "complete" else ""),
             f"{row['event_count']:,}", f"{row['cases_with_event']:,}",
             f"{row['cases_min_occurrences']:,}",
             f"{row['cases_min_same_resource']:,}" if result["resource_available"] else "N/A"]
            for _, row in result["comparison"].iterrows()
        ])

        # Tampilkan bukti case pertama secara otomatis
        if self.table_1515_cases.rowCount():
            self.table_1515_cases.selectRow(0)
        if self.table_1518_cases.rowCount():
            self.table_1518_cases.selectRow(0)

        resource_note = (
            f"{ex_1518['unidentified_resource_events']:,} complete event tanpa resource "
            "teridentifikasi diabaikan pada 11.18."
            if result["resource_available"]
            else "org:resource tidak tersedia sehingga 11.18 tidak dapat dihitung."
        )
        self.status_1518.setText(
            f"Status: Selesai untuk '{result['activity']}'. "
            f"11.15: {ex_1515['total_cases']:,} dari {total_cases:,} case. "
            f"11.18: {ex_1518['total_cases']:,} dari {total_cases:,} case. {resource_note}"
        )
        self.export_1518_button.setEnabled(True)

    def show_1518_evidence(self, key):
        """Isi tabel bukti untuk case yang dipilih pada tabel 11.15 / 11.18."""
        if self.result_1518 is None:
            return
        if key == "ex_1115":
            case_table, evidence_table = self.table_1515_cases, self.table_1515_evidence
        else:
            case_table, evidence_table = self.table_1518_cases, self.table_1518_evidence

        row = case_table.currentRow()
        item = case_table.item(row, 0) if row >= 0 else None
        if item is None:
            evidence_table.setRowCount(0)
            return

        evidence = self.result_1518[key]["evidence"]
        selected = evidence[evidence[CASE_COLUMN].astype(str) == item.text()]
        if key == "ex_1118":
            resource = case_table.item(row, 1).text()
            selected = selected[selected["org:resource"].astype(str) == resource]

        timestamps = format_datetime_series(selected[TIMESTAMP_COLUMN]).tolist()
        self.fill_table(evidence_table, [
            [self._text(event["trace_position"]), timestamp,
             self._text(event["concept:name"]), self._text(event["lifecycle:transition"]),
             self._text(event["org:resource"]), "Ya" if event["counted"] else "Tidak"]
            for timestamp, (_, event) in zip(timestamps, selected.iterrows())
        ])

    def open_1518_case_detail(self, index):
        if self.active_data is None or not index.isValid():
            return
        table = self.sender()
        item = table.item(index.row(), 0) if table is not None else None
        if item is not None:
            self.open_case_detail(item.text())

    def on_1518_failed(self, message):
        self.status_1518.setText("Status: Analisis 11.15 & 11.18 gagal.")
        QMessageBox.critical(self, "Analisis 11.15 & 11.18 Gagal", message)

    def on_1518_finished(self):
        self.progress_1518.setVisible(False)
        self.progress_1518.setRange(0, 1)
        self.activity_1518_combo.setEnabled(self.active_data is not None)
        self.run_1518_button.setEnabled(
            self.active_data is not None
            and "lifecycle:transition" in self.active_data["import"]["available_optional"]
        )
        self.reset_1518_button.setEnabled(self.result_1518 is not None)

    def reset_1518(self, clear_status=True):
        """Kosongkan hasil 11.15 & 11.18 (log tetap aktif, bisa dihitung ulang)."""
        self.result_1518 = None
        for label in (
            self.metric_1515_cases, self.metric_1518_cases,
            self.metric_1518_events, self.metric_1518_total,
        ):
            label.setText("-")
        for table in (
            self.table_1515_cases, self.table_1515_evidence,
            self.table_1518_cases, self.table_1518_evidence, self.table_1518_compare,
        ):
            table.setRowCount(0)
        self.export_1518_button.setEnabled(False)
        self.reset_1518_button.setEnabled(False)
        if clear_status:
            self.status_1518.setText(
                "Status: Impor dataset terlebih dahulu."
                if self.active_data is None
                else "Status: Hasil direset. Klik Hitung 11.15 & 11.18 untuk menghitung ulang."
            )

    def export_1518_csv(self):
        if self.result_1518 is None:
            QMessageBox.warning(self, "Belum Ada Data", "Jalankan analisis terlebih dahulu.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Simpan Hasil 11.15 & 11.18", "hasil_11_15_18.csv", "CSV Files (*.csv)"
        )
        if not file_path:
            return

        summary_path = Path(file_path).with_suffix(".csv")
        cases_path = summary_path.with_name(summary_path.stem + "_case.csv")
        evidence_path = summary_path.with_name(summary_path.stem + "_evidence.csv")

        result = self.result_1518
        ex_1515, ex_1518 = result["ex_1115"], result["ex_1118"]
        total = result["total_cases_log"]
        dataset_name = self.active_data["import"]["file_name"]

        summary_rows = [
            ["Dataset", "File aktif", dataset_name, "", ""],
            ["Dataset", "Aktivitas target", result["activity"], "", ""],
            ["11.15", "Case dengan aktivitas target complete minimal 2x",
             ex_1515["total_cases"], "case", f"{ex_1515['rule']} Denominator log = {total} case."],
            ["11.18", "Case dengan minimal 2 complete oleh resource yang sama",
             ex_1518["total_cases"], "case", f"{ex_1518['rule']} Denominator log = {total} case."],
            ["Info", "Complete event tanpa resource teridentifikasi (11.18)",
             ex_1518["unidentified_resource_events"], "event",
             "Tidak dianggap sebagai resource yang sama"],
        ]
        for _, row in result["comparison"].iterrows():
            summary_rows.append([
                "Pembanding (bukan jawaban)", f"Lifecycle: {row['lifecycle']}",
                row["cases_min_occurrences"], "case ≥2 event",
                f"event={row['event_count']}; case memuat={row['cases_with_event']}; "
                f"case ≥2 resource sama={row['cases_min_same_resource']}",
            ])
        summary = pd.DataFrame(
            summary_rows, columns=["Kode", "Pertanyaan", "Hasil", "Satuan", "Aturan / Denominator"]
        )

        cases_1515 = ex_1515["per_case"].assign(Kode="11.15")
        cases_1518 = ex_1518["per_case"].assign(Kode="11.18")
        cases = pd.concat([cases_1515, cases_1518], ignore_index=True)
        cases = cases[["Kode"] + [c for c in cases.columns if c != "Kode"]]
        # Kolom jumlah tetap bilangan bulat walau kosong pada baris 11.18.
        for column in ("complete_count", "target_events_all_lifecycle"):
            if column in cases:
                cases[column] = cases[column].astype("Int64")

        evidence = pd.concat([
            ex_1515["evidence"].assign(Kode="11.15"),
            ex_1518["evidence"].assign(Kode="11.18"),
        ], ignore_index=True)
        evidence = evidence[["Kode"] + [c for c in evidence.columns if c != "Kode"]]

        try:
            summary.to_csv(summary_path, index=False)
            cases.to_csv(cases_path, index=False)
            evidence.to_csv(evidence_path, index=False)
        except Exception as error:
            QMessageBox.critical(self, "Gagal", f"Gagal menyimpan file: {error}")
            return

        QMessageBox.information(
            self,
            "Sukses",
            f"Ringkasan jawaban:\n{summary_path}\n\nDaftar case:\n{cases_path}\n\n"
            f"Bukti event:\n{evidence_path}",
        )

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