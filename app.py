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
    QTabWidget,
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
)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from modules.importer import import_xes
from modules.overview import generate_overview



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
        except Exception as error:
            self.import_failed.emit(f"{type(error).__name__}: {error}")
            return

        self.imported.emit(result)

        try:
            overview = generate_overview(result["dataframe"])
            self.overview_ready.emit(overview)
        except Exception as error:
            self.overview_failed.emit(f"{type(error).__name__}: {error}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("BPIC17 Analyzer")
        self.resize(1200, 780)

        self.active_data = None
        self.worker = None

        self.build_interface()

    # MAIN INTERFACE
    def build_interface(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        title = QLabel("BPIC17 Analyzer")
        title.setStyleSheet(
            "font-size: 26px; font-weight: bold;"
        )

        subtitle = QLabel(
            "Desktop Application for Event Log Analysis"
        )
        subtitle.setStyleSheet("color: gray;")

        main_layout.addWidget(title)
        main_layout.addWidget(subtitle)

        self.tabs = QTabWidget()

        self.dataset_tab = self.create_dataset_tab()
        self.overview_tab = self.create_overview_tab()

        self.tabs.addTab(self.dataset_tab, "Dataset")
        self.tabs.addTab(self.overview_tab, "Overview")

        main_layout.addWidget(self.tabs)
    
        self.setStyleSheet("""
            QWidget {
                font-family: Segoe UI;
                font-size: 10pt;
                background-color: #F8FAFC;
                color: #1E293B;
            }

            QMainWindow {
                background-color: #F8FAFC;
            }

            QTabWidget::pane {
                border: 1px solid #E2E8F0;
                background-color: white;
                border-radius: 8px;
            }

            QTabBar::tab {
                background-color: #E2E8F0;
                color: #475569;
                padding: 11px 22px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }

            QTabBar::tab:selected {
                background-color: #2563EB;
                color: white;
                font-weight: bold;
            }

            QPushButton {
                background-color: #2563EB;
                color: white;
                padding: 10px 18px;
                border: none;
                border-radius: 7px;
                font-weight: bold;
            }

            QPushButton:hover {
                background-color: #1D4ED8;
            }

            QPushButton:disabled {
                background-color: #94A3B8;
            }

            QLineEdit {
                background-color: white;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 9px;
            }

            QListWidget {
                background-color: white;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                padding: 5px;
            }

            QTableWidget {
                background-color: white;
                alternate-background-color: #F1F5F9;
                gridline-color: #E2E8F0;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                selection-background-color: #DBEAFE;
                selection-color: #1E40AF;
            }

            QHeaderView::section {
                background-color: #EFF6FF;
                color: #1E40AF;
                padding: 9px;
                border: none;
                border-bottom: 1px solid #CBD5E1;
                font-weight: bold;
            }

            QFrame {
                background-color: white;
                border: 1px solid #E2E8F0;
                border-radius: 9px;
            }

            QProgressBar {
                border: none;
                background-color: #E2E8F0;
                border-radius: 5px;
                height: 9px;
            }

            QProgressBar::chunk {
                background-color: #2563EB;
                border-radius: 5px;
            }
        """)


    # DATASET TAB - F01
    def create_dataset_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(15)

        heading = QLabel("Dataset Management")
        heading.setStyleSheet("font-size: 20px; font-weight: bold;")

        description = QLabel("Import and validate BPIC17 event log in XES format.")

        self.choose_button = QPushButton("Choose XES File")
        self.choose_button.clicked.connect(self.choose_xes_file)

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
        self.optional_label = QLabel("Lifecycle / Resource: -")

        self.attribute_list = QListWidget()

        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addWidget(self.choose_button)
        layout.addWidget(self.file_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.case_label)
        layout.addWidget(self.event_label)
        layout.addWidget(self.timestamp_label)
        layout.addWidget(self.optional_label)
        layout.addWidget(QLabel("Available Attributes:"))
        layout.addWidget(self.attribute_list)

        layout.addStretch()

        return page

    # OVERVIEW TAB - F02
    def create_overview_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(15)

        heading = QLabel("Event Log Overview")
        heading.setStyleSheet("font-size: 20px; font-weight: bold;")

        self.overview_cases = QLabel("Total Cases: -")
        self.overview_events = QLabel("Total Events: -")
        self.overview_cycle = QLabel("Average Cycle Time: -")
        self.overview_range = QLabel("Date Range: -")

        metrics_layout = QGridLayout()

        metrics = [
            self.overview_cases,
            self.overview_events,
            self.overview_cycle,
            self.overview_range,
        ]

        for index, label in enumerate(metrics):
            card = QFrame()
            card.setFrameShape(QFrame.Shape.StyledPanel)

            card_layout = QVBoxLayout(card)
            label.setWordWrap(True)
            label.setStyleSheet("font-size: 13px; font-weight: bold;")
            card_layout.addWidget(label)

            metrics_layout.addWidget(card, index // 2, index % 2)

        layout.addWidget(heading)
        layout.addLayout(metrics_layout)

        layout.addWidget(QLabel("Top 15 Activity Frequency"))

        self.activity_figure = Figure(figsize=(9, 4))
        self.activity_canvas = FigureCanvasQTAgg(self.activity_figure)
        self.activity_canvas.setMinimumHeight(320)

        layout.addWidget(self.activity_canvas)

        layout.addWidget(QLabel("All Activity Frequency"))

        self.activity_table = QTableWidget(0, 2)
        self.activity_table.setHorizontalHeaderLabels(["Activity", "Frequency"])

        self.activity_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.activity_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.activity_table)
        layout.addWidget(QLabel("Case Duration"))

        self.case_search = QLineEdit()
        self.case_search.setPlaceholderText("Search Case ID...")
        self.case_search.textChanged.connect(self.filter_case_table)

        self.case_table = QTableWidget(0, 4)
        self.case_table.setHorizontalHeaderLabels([
            "Case ID",
            "Start Time",
            "End Time",
            "Duration (Days)",
        ])

        self.case_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        for column in range(1, 4):
            self.case_table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )

        self.case_table.setSortingEnabled(True)

        layout.addWidget(self.case_search)
        layout.addWidget(self.case_table)

        return page

    # SELECT AND IMPORT XES
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

    # IMPORT SUCCESS
    def import_succeeded(self, imported):
        self.active_data = {"import": imported, "overview": None}

        self.status_label.setText("Status: Import successful — calculating overview...")
        self.file_label.setText(f"Active Dataset: {imported['file_name']}")
        self.case_label.setText(f"Total Cases: {imported['total_cases']:,}")
        self.event_label.setText(f"Total Events: {imported['total_events']:,}")
        self.timestamp_label.setText(f"Invalid timestamps: {imported['invalid_timestamp_events']:,}")

        self.attribute_list.clear()
        self.attribute_list.addItems(imported["available_columns"])

        optional = imported["available_optional"]

        self.optional_label.setText(
            "Optional Attributes: "
            + (", ".join(optional) if optional else "None detected")
        )

    # IMPORT FAILED
    def import_failed(self, message):
        self.status_label.setText("Status: Import failed")

        QMessageBox.critical(
            self,
            "Import Failed",
            "Dataset tidak dapat diimpor.\n\n"
            + message,
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

        self.overview_cases.setText(
            f"Total Cases: {overview['total_cases']:,}"
        )
        self.overview_events.setText(
            f"Total Events: {overview['total_events']:,}"
        )

        average = overview["average_cycle_time_days"]
        cycle_text = (
            f"{average:,.2f} days"
            if average is not None else "Not available"
        )
        self.overview_cycle.setText(f"Average Cycle Time: {cycle_text}")

        start = overview["start_date"]
        end = overview["end_date"]
        self.overview_range.setText(f"Date Range: {start} — {end}")

        # Activity frequency
        activity = overview["activity_frequency"]
        self.activity_table.setSortingEnabled(False)

        # Activity frequency chart - Top 15
        top_activity = activity.head(15).iloc[::-1]

        self.activity_figure.clear()
        ax = self.activity_figure.add_subplot(111)

        ax.barh(
            top_activity["Activity"].astype(str),
            top_activity["Frequency"],
            color="#3B82F6",
        )

        ax.set_xlabel("Number of Events")
        ax.set_ylabel("Activity")
        ax.set_title("Most Frequent Activities")
        ax.grid(axis="x", linestyle="--", alpha=0.3)
        ax.set_axisbelow(True)

        self.activity_figure.tight_layout()
        self.activity_canvas.draw()
        self.activity_table.setRowCount(len(activity))

        for row, record in enumerate(activity.itertuples(index=False)):
            self.activity_table.setItem(
                row, 0, QTableWidgetItem(str(record[0]))
            )
            self.activity_table.setItem(
                row, 1, QTableWidgetItem(f"{record[1]:,}")
            )

        self.activity_table.setSortingEnabled(True)

        # Case duration
        cases = overview["case_durations"]

        self.case_table.setUpdatesEnabled(False)
        self.case_table.setSortingEnabled(False)
        self.case_table.setRowCount(len(cases))

        try:
            for row, record in enumerate(cases.itertuples(index=False)):
                case_id = str(record[0])
                start_time = str(record[1]) if pd_not_null(record[1]) else "-"
                end_time = str(record[2]) if pd_not_null(record[2]) else "-"
                duration = record[6]

                duration_text = (
                    f"{duration:.2f}"
                    if pd_not_null(duration) else "Not available"
                )

                values = [case_id, start_time, end_time, duration_text]

                for column, value in enumerate(values):
                    self.case_table.setItem(
                        row, column, QTableWidgetItem(value)
                    )
        finally:
            self.case_table.setUpdatesEnabled(True)

        self.case_table.setSortingEnabled(True)

        self.status_label.setText("Status: Import and overview successful")
        self.tabs.setCurrentWidget(self.overview_tab)


    # SEARCH CASE ID
    def filter_case_table(self, keyword):
        keyword = keyword.lower().strip()

        for row in range(self.case_table.rowCount()):
            item = self.case_table.item(row, 0)

            if item is None:
                continue

            visible = keyword in item.text().lower()

            self.case_table.setRowHidden(row, not visible)

    # OVERFIEW FAILED
    def overview_failed(self, message):
        self.status_label.setText("Status: Import successful — Overview failed")
        QMessageBox.warning(self, "Overview Failed", message)


def pd_not_null(value):
    return value is not None and str(value) != "NaT" and str(value) != "nan"

if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
