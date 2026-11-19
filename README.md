# BPIC17 Analyzer

Desktop application for event log analysis using Python, PM4Py, PySide6, and Matplotlib.

## Features

### F01 - Dataset Import and Validation
- Import event logs in XES format.
- Validate required event attributes.
- Detect optional attributes.
- Display dataset information.
- Handle invalid or incomplete timestamps.

### F02 - Event Log Overview
- Display total cases and events.
- Display activity frequency.
- Visualize the 15 most frequent activities.
- Display event log date range.
- Calculate average cycle time.
- Display duration for each case.
- Search cases using Case ID.

## Technologies
- Python
- PM4Py
- Pandas
- PySide6
- Matplotlib

## Project Structure

```text
BPIC17-Analyzer/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
└── modules/
    ├── __init__.py
    ├── importer.py
    └── overview.py
```

## Installation

1. Clone this repository.

```bash
git clone YOUR_REPOSITORY_URL
cd BPIC17-Analyzer
```

2. Create a virtual environment.

```bash
python -m venv .venv
```

3. Activate the environment.

Windows:

```bash
.venv\Scripts\activate
```

4. Install dependencies.

```bash
pip install -r requirements.txt
```

## Run Application

```bash
python app.py
```

Select an XES dataset through the Choose XES File button.

## Dataset

Provide your own XES event log dataset. Dataset files are not included in this repository.
