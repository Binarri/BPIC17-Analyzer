from pathlib import Path

import pandas as pd
import pm4py


REQUIRED_COLUMNS = [
    "case:concept:name",
    "concept:name",
    "time:timestamp",
]

OPTIONAL_COLUMNS = [
    "lifecycle:transition",
    "org:resource",
]


def import_xes(file_path):
    """
    Membaca dan memvalidasi event log XES
    menggunakan PM4Py.
    """

    path = Path(file_path)

    # 1. Validasi lokasi dan format file
    if not path.exists():
        raise FileNotFoundError(f"File tidak ditemukan: {path}")

    if not path.is_file():
        raise ValueError("Lokasi yang dipilih bukan file.")

    if path.suffix.lower() != ".xes":
        raise ValueError("File harus berformat .xes.")

    # 2. Membaca XES menggunakan PM4Py
    event_log = pm4py.read_xes(str(path))

    # 3. Mengubah EventLog menjadi DataFrame
    dataframe = pm4py.convert_to_dataframe(event_log)

    if dataframe.empty:
        raise ValueError("Event log tidak memiliki event.")

    # 4. Memeriksa atribut wajib
    missing_columns = [
        col for col in REQUIRED_COLUMNS
        if col not in dataframe.columns
    ]

    if missing_columns:
        raise ValueError("Atribut wajib tidak ditemukan: " + ", ".join(missing_columns))

    # 5. Memeriksa nilai kosong pada Case ID dan Activity
    for column in ["case:concept:name", "concept:name"]:
        if dataframe[column].isna().any():
            raise ValueError(f"Atribut {column} memiliki nilai kosong.")

    # 6. Mengubah timestamp menjadi datetime
    dataframe["time:timestamp"] = pd.to_datetime(
        dataframe["time:timestamp"],
        errors="coerce",
        utc=True,
    )

    invalid_timestamp_events = int(dataframe["time:timestamp"].isna().sum())

    if invalid_timestamp_events == len(dataframe):
        raise ValueError("Semua timestamp tidak valid atau kosong.")

    # 7. Mengurutkan event berdasarkan case dan waktu
    dataframe = dataframe.sort_values(
        by=["case:concept:name", "time:timestamp"],
        na_position="last",
        kind="stable",
    ).reset_index(drop=True)

    # 8. Mendeteksi atribut opsional
    available_optional = [
        col for col in OPTIONAL_COLUMNS
        if col in dataframe.columns
    ]

    # 9. Menyiapkan informasi hasil import
    return {
        "event_log": event_log,
        "dataframe": dataframe,
        "file_name": path.name,
        "file_path": str(path.resolve()),
        "total_cases": int(dataframe["case:concept:name"].nunique()),
        "total_events": len(dataframe),
        "available_columns": list(dataframe.columns),
        "available_optional": available_optional,
        "invalid_timestamp_events": invalid_timestamp_events,
    }
