
from pathlib import Path
import sys

from PySide6.QtCore import QThread, Signal, Qt
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
    QHeaderView,
    QFrame,
    QScrollArea,
)

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from modules.importer import import_xes
from modules.overview import generate_overview


# IMPORT WORKER
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
            self.import_failed.emit(
                f"{type(error).__name__}: {error}"
            )
            return

        try:
            overview = generate_overview(result["dataframe"])
            self.overview_ready.emit(overview)
        except Exception as error:
            self.overview_failed.emit(
                f"{type(error).__name__}: {error}"
            )


# MAIN WINDOW
class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("BPIC17 Analyzer")
        self.resize(1450, 900)
        self.setMinimumSize(1100, 700)

        self.active_data = None
        self.worker = None
        self.case_data = None

        self.build_interface()


    # MAIN INTERFACE
    def build_interface(self):
        central = QWidget()
        self.setCentralWidget(central)

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
        self.nav_process = QPushButton("Process Map")
        self.nav_cases = QPushButton("Case Details")
        self.nav_dataset = QPushButton("Dataset")

        self.nav_overview.clicked.connect(
            lambda: self.show_page(0)
        )
        self.nav_dataset.clicked.connect(
            lambda: self.show_page(1)
        )

        # Fitur anggota kelompok lain.
        # Tidak diimplementasikan oleh ANNIS.
        self.nav_process.setEnabled(False)
        self.nav_cases.setEnabled(False)

        self.nav_process.setToolTip(
            "Reserved for the Process Map task"
        )
        self.nav_cases.setToolTip(
            "Reserved for the Case Details task"
        )

        for button in (
            self.nav_overview,
            self.nav_process,
            self.nav_cases,
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

        self.pages.addWidget(self.overview_page)
        self.pages.addWidget(self.dataset_page)

        body.addWidget(self.pages, 1)
        root.addLayout(body)

        self.apply_styles()
        self.show_page(0)


    # STYLESHEET
    def apply_styles(self):
        self.setStyleSheet("""
            QWidget {
                font-family: Segoe UI;
                font-size: 9pt;
                color: #273444;
                background-color: #F1F4F8;
            }

            QMainWindow {
                background-color: #F1F4F8;
            }

            QWidget#navbar {
                background-color: #354252;
            }

            QLabel#brand {
                color: white;
                background: transparent;
                border: none;
                padding: 0px;
                font-size: 15px;
                font-weight: bold;
            }

            QPushButton#navButton {
                background-color: transparent;
                color: #DCE3EA;
                border: none;
                padding: 9px 17px;
                border-radius: 4px;
                min-width: 75px;
            }

            QPushButton#navButton:hover {
                background-color: #526174;
            }

            QPushButton#navButton:checked {
                background-color: #E8EDF3;
                color: #354252;
                font-weight: bold;
            }

            QPushButton#navButton:disabled {
                color: #AAB4C0;
                background-color: transparent;
            }

            QWidget#sidebar {
                background-color: #E5EAF0;
                border-right: 1px solid #D1D9E2;
            }

            QLabel#sectionTitle {
                background: transparent;
                color: #354252;
                font-size: 10pt;
                font-weight: bold;
                padding: 3px 0px;
            }

            QLabel#sidebarKey {
                background: transparent;
                color: #526174;
                font-size: 8pt;
            }

            QLabel#sidebarValue {
                background: transparent;
                color: #354252;
                font-size: 8pt;
            }

            QFrame#metricCard {
                background-color: #EAF2FA;
                border: 1px solid #D3DFEB;
                border-radius: 5px;
            }

            QLabel#metricTitle {
                background: transparent;
                color: #64748B;
                font-size: 8pt;
            }

            QLabel#metricValue {
                background: transparent;
                color: #263548;
                font-size: 15px;
                font-weight: bold;
            }

            QFrame#panel {
                background-color: white;
                border: 1px solid #D7DEE7;
                border-radius: 5px;
            }

            QLabel#panelTitle {
                background: transparent;
                color: #354252;
                font-size: 10pt;
                font-weight: bold;
            }

            QPushButton {
                background-color: #526A82;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 9px 14px;
            }

            QPushButton:hover {
                background-color: #40566D;
            }

            QPushButton:disabled {
                background-color: #AAB4C0;
            }

            QLineEdit {
                background-color: white;
                border: 1px solid #C9D2DD;
                padding: 8px;
                border-radius: 4px;
            }

            QListWidget, QTableWidget {
                background-color: white;
                alternate-background-color: #F0F3F7;
                gridline-color: #DCE3EB;
                border: 1px solid #D7DEE7;
                selection-background-color: #DCE7F2;
                selection-color: #263548;
            }

            QHeaderView::section {
                background-color: #DFE8F2;
                color: #344A60;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #C9D4E0;
                font-weight: bold;
            }

            QTableWidget QTableCornerButton::section {
                background-color: #DFE8F2;
                border: none;
            }

            QScrollArea {
                background-color: #F1F4F8;
                border: none;
            }

            QScrollBar:vertical {
                background: #E5EAF0;
                width: 10px;
                margin: 0px;
            }

            QScrollBar::handle:vertical {
                background: #9AA9B9;
                min-height: 25px;
                border-radius: 4px;
            }

            QScrollBar:horizontal {
                background: #E5EAF0;
                height: 10px;
            }

            QScrollBar::handle:horizontal {
                background: #9AA9B9;
                min-width: 25px;
                border-radius: 4px;
            }

            QProgressBar {
                background: #DFE5EC;
                border: none;
                border-radius: 4px;
                height: 8px;
            }

            QProgressBar::chunk {
                background: #607D98;
                border-radius: 4px;
            }

            QFrame#sidebarLine {
                background-color: #C7D0DA;
                border: none;
                max-height: 1px;
            }
        """)


    # SIDEBAR
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

        self.side_cases = self.add_sidebar_stat(
            layout, "Cases", "-"
        )
        self.side_events = self.add_sidebar_stat(
            layout, "Events", "-"
        )
        self.side_activities = self.add_sidebar_stat(
            layout, "Activities", "-"
        )
        self.side_cycle = self.add_sidebar_stat(
            layout, "Avg. Cycle Time", "-"
        )
        self.side_start = self.add_sidebar_stat(
            layout, "Start", "-"
        )
        self.side_end = self.add_sidebar_stat(
            layout, "End", "-"
        )

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


    # PAGE NAVIGATION
    def show_page(self, index):
        self.pages.setCurrentIndex(index)

        self.nav_overview.setChecked(index == 0)
        self.nav_dataset.setChecked(index == 1)


    # OVERVIEW PAGE - F02
    def create_overview_page(self):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)

        # Heading
        heading = QLabel("Overview")
        heading.setStyleSheet(
            "font-size: 17px; font-weight: bold;"
        )
        layout.addWidget(heading)

        subtitle = QLabel(
            "Global statistics about the event log."
        )
        subtitle.setStyleSheet("color: #718096;")
        layout.addWidget(subtitle)

        # METRIC CARDS
        metrics_layout = QGridLayout()
        metrics_layout.setSpacing(10)

        self.metric_cases = self.create_metric_card(
            metrics_layout, 0, "Total Cases"
        )
        self.metric_events = self.create_metric_card(
            metrics_layout, 1, "Total Events"
        )
        self.metric_cycle = self.create_metric_card(
            metrics_layout, 2, "Average Cycle Time"
        )
        self.metric_range = self.create_metric_card(
            metrics_layout, 3, "Date Range"
        )

        for column in range(4):
            metrics_layout.setColumnStretch(column, 1)

        layout.addLayout(metrics_layout)

        # CHART AND ACTIVITY TABLE
        analysis_layout = QHBoxLayout()
        analysis_layout.setSpacing(10)

        # Chart panel
        chart_panel = self.create_panel(
            "Most Frequent Activities (Top 15)"
        )
        chart_layout = chart_panel.layout()

        self.activity_figure = Figure(
            figsize=(6, 2.7),
            dpi=100,
        )

        self.activity_canvas = FigureCanvasQTAgg(
            self.activity_figure
        )
        self.activity_canvas.setMinimumHeight(230)
        self.activity_canvas.setMaximumHeight(270)

        chart_layout.addWidget(self.activity_canvas)
        analysis_layout.addWidget(chart_panel, 3)

        # Activity table panel
        activity_panel = self.create_panel(
            "All Activity Frequency"
        )
        activity_layout = activity_panel.layout()

        self.activity_table = QTableWidget(0, 2)
        self.activity_table.setHorizontalHeaderLabels([
            "Activity",
            "Frequency",
        ])

        self.activity_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.activity_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )

        self.activity_table.setAlternatingRowColors(True)
        self.activity_table.setSortingEnabled(False)
        self.activity_table.verticalHeader().setVisible(True)
        self.activity_table.verticalHeader().setDefaultSectionSize(25)
        self.activity_table.setFixedHeight(270)

        activity_layout.addWidget(self.activity_table)
        analysis_layout.addWidget(activity_panel, 2)

        layout.addLayout(analysis_layout)

        # CASE DURATION
        case_panel = self.create_panel("Case Duration")
        case_layout = case_panel.layout()

        self.case_search = QLineEdit()
        self.case_search.setPlaceholderText("Search Case ID...")
        self.case_search.textChanged.connect(
            self.filter_case_table
        )
        case_layout.addWidget(self.case_search)

        self.case_table = QTableWidget(0, 4)
        self.case_table.setHorizontalHeaderLabels([
            "Case ID",
            "Start Time",
            "End Time",
            "Duration (Days)",
        ])

        self.case_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )

        for column in range(1, 4):
            self.case_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )

        self.case_table.setAlternatingRowColors(True)
        self.case_table.setSortingEnabled(False)
        self.case_table.verticalHeader().setVisible(True)
        self.case_table.verticalHeader().setDefaultSectionSize(25)
        self.case_table.setMinimumHeight(180)
        self.case_table.setMaximumHeight(230)

        case_layout.addWidget(self.case_table)
        layout.addWidget(case_panel)

        layout.addStretch()

        scroll.setWidget(content)
        page_layout.addWidget(scroll)

        return page


    # METRIC CARD
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


    # PANEL
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


    # DATASET PAGE - F01
    def create_dataset_page(self):
        page = QWidget()

        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        heading = QLabel("Dataset Management")
        heading.setStyleSheet(
            "font-size: 19px; font-weight: bold;"
        )
        layout.addWidget(heading)

        description = QLabel(
            "Import and validate BPIC17 event log in XES format."
        )
        layout.addWidget(description)

        self.choose_button = QPushButton("Choose XES File")
        self.choose_button.clicked.connect(
            self.choose_xes_file
        )
        layout.addWidget(self.choose_button)

        self.file_label = QLabel("No dataset selected")
        self.file_label.setWordWrap(True)

        self.status_label = QLabel(
            "Status: Waiting for dataset"
        )

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

    # IMPORT XES
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

        self.status_label.setText(
            "Status: Reading and validating dataset..."
        )
        self.file_label.setText(
            f"Selected file: {Path(file_path).name}"
        )

        self.worker = ImportWorker(file_path)

        self.worker.imported.connect(self.import_succeeded)
        self.worker.overview_ready.connect(self.display_overview)
        self.worker.import_failed.connect(self.import_failed)
        self.worker.overview_failed.connect(self.overview_failed)
        self.worker.finished.connect(self.import_finished)

        self.worker.start()

    def import_succeeded(self, imported):
        self.active_data = {
            "import": imported,
            "overview": None,
        }

        self.file_label.setText(
            f"Active Dataset: {imported['file_name']}"
        )

        self.status_label.setText(
            "Status: Import successful — calculating overview..."
        )

        self.case_label.setText(
            f"Total Cases: {imported['total_cases']:,}"
        )
        self.event_label.setText(
            f"Total Events: {imported['total_events']:,}"
        )
        self.timestamp_label.setText(
            f"Invalid timestamps: "
            f"{imported['invalid_timestamp_events']:,}"
        )

        optional = imported["available_optional"]
        self.optional_label.setText(
            "Optional Attributes: "
            + (", ".join(optional) if optional else "None detected")
        )

        self.attribute_list.clear()
        self.attribute_list.addItems(
            imported["available_columns"]
        )

        # Sidebar
        self.sidebar_file.setText(imported["file_name"])

        self.side_cases.setText(
            f"{imported['total_cases']:,}"
        )
        self.side_events.setText(
            f"{imported['total_events']:,}"
        )

    def import_failed(self, message):
        self.status_label.setText("Status: Import failed")

        QMessageBox.critical(
            self,
            "Import Failed",
            "Dataset tidak dapat diimpor.\n\n" + message,
        )

    def import_finished(self):
        self.choose_button.setEnabled(True)
        self.progress.setVisible(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)


    # DISPLAY OVERVIEW
    def display_overview(self, overview):
        if self.active_data is not None:
            self.active_data["overview"] = overview

        total_cases = overview["total_cases"]
        total_events = overview["total_events"]
        average = overview["average_cycle_time_days"]

        # Metric cards
        self.metric_cases.setText(f"{total_cases:,}")
        self.metric_events.setText(f"{total_events:,}")

        self.metric_cycle.setText(
            f"{average:.2f} days"
            if average is not None else "Not available"
        )

        start = overview["start_date"]
        end = overview["end_date"]

        start_text = (
            start.strftime("%Y-%m-%d %H:%M:%S")
            if pd_not_null(start) else "-"
        )
        end_text = (
            end.strftime("%Y-%m-%d %H:%M:%S")
            if pd_not_null(end) else "-"
        )

        self.metric_range.setText(
            f"{start_text} — {end_text}"
        )

        # Sidebar statistics
        activity = overview["activity_frequency"]

        self.side_activities.setText(str(len(activity)))

        self.side_cycle.setText(
            f"{average:.2f} days"
            if average is not None else "-"
        )

        self.side_start.setText(start_text)
        self.side_end.setText(end_text)

        # TOP 15 ACTIVITY CHART
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
            labels=[
                f"{int(value):,}"
                for value in top_activity["Frequency"]
            ],
            padding=3,
            fontsize=6,
        )

        ax.set_xlabel("Number of Events", fontsize=7)
        ax.tick_params(axis="both", labelsize=7)

        ax.grid(
            axis="x",
            linestyle="--",
            alpha=0.25,
        )
        ax.set_axisbelow(True)

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)

        self.activity_figure.subplots_adjust(
            left=0.34,
            right=0.98,
            top=0.97,
            bottom=0.17,
        )

        self.activity_canvas.draw()

        # ALL ACTIVITY FREQUENCY
        self.activity_table.setUpdatesEnabled(False)
        self.activity_table.setRowCount(len(activity))

        try:
            for row, record in enumerate(
                activity.itertuples(index=False)
            ):
                self.activity_table.setItem(
                    row,
                    0,
                    QTableWidgetItem(str(record[0])),
                )

                self.activity_table.setItem(
                    row,
                    1,
                    QTableWidgetItem(f"{record[1]:,}"),
                )
        finally:
            self.activity_table.setUpdatesEnabled(True)

        # CASE DURATION
        cases = overview["case_durations"]
        self.case_data = cases

        self.case_table.setUpdatesEnabled(False)
        self.case_table.setRowCount(len(cases))

        try:
            for row, record in enumerate(
                cases.itertuples(index=False)
            ):
                case_id = str(record[0])

                start_time = (
                    record[1].strftime("%Y-%m-%d %H:%M:%S")
                    if pd_not_null(record[1]) else "-"
                )

                end_time = (
                    record[2].strftime("%Y-%m-%d %H:%M:%S")
                    if pd_not_null(record[2]) else "-"
                )

                duration = record[6]
                duration_text = (
                    f"{duration:.2f}"
                    if pd_not_null(duration) else "Not available"
                )

                values = [
                    case_id,
                    start_time,
                    end_time,
                    duration_text,
                ]

                for column, value in enumerate(values):
                    self.case_table.setItem(
                        row,
                        column,
                        QTableWidgetItem(value),
                    )

        finally:
            self.case_table.setUpdatesEnabled(True)

        self.status_label.setText(
            "Status: Import and overview successful"
        )

        self.show_page(0)


    # CASE SEARCH
    def filter_case_table(self, keyword):
        keyword = keyword.lower().strip()

        for row in range(self.case_table.rowCount()):
            item = self.case_table.item(row, 0)

            if item is None:
                continue

            visible = keyword in item.text().lower()
            self.case_table.setRowHidden(row, not visible)

    # OVERVIEW ERROR
    def overview_failed(self, message):
        self.status_label.setText(
            "Status: Import successful — Overview failed"
        )

        QMessageBox.warning(
            self,
            "Overview Failed",
            message,
        )


# HELPER
def pd_not_null(value):
    return (
        value is not None
        and str(value) != "NaT"
        and str(value) != "nan"
    )


# RUN APPLICATION
if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
