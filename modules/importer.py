from pathlib import Path
from time import perf_counter

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
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"File tidak ditemukan: {path}")

    if path.suffix.lower() != ".xes":
        raise ValueError("File harus berformat .xes.")

    started = perf_counter()

    # 1. Membaca XES menggunakan PM4Py
    df = pm4py.read_xes(
        str(path),
        return_legacy_log=False,
    )

    print(
        f"[PERFORMANCE] XES reading: "
        f"{perf_counter() - started:.2f} detik"
    )

    if df.empty:
        raise ValueError("Event log tidak memiliki event.")

    # 2. Memeriksa atribut wajib
    missing = [
        col for col in REQUIRED_COLUMNS
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            "Atribut wajib tidak ditemukan: "
            + ", ".join(missing)
        )

    # 3. Memvalidasi Case ID dan Activity
    for col in ["case:concept:name", "concept:name"]:
        empty_values = (
            df[col].isna()
            | df[col].astype("string").str.strip().eq("")
        )

        if empty_values.any():
            raise ValueError(
                f"Atribut {col} memiliki "
                f"{int(empty_values.sum()):,} nilai kosong."
            )

    # 4. Mengonversi timestamp
    t0 = perf_counter()

    df["time:timestamp"] = pd.to_datetime(
        df["time:timestamp"],
        errors="coerce",
        utc=True,
    )

    invalid_timestamps = int(
        df["time:timestamp"].isna().sum()
    )

    if invalid_timestamps == len(df):
        raise ValueError(
            "Semua timestamp tidak valid atau kosong."
        )

    print(
        f"[PERFORMANCE] Validation: "
        f"{perf_counter() - t0:.2f} detik"
    )

    # 5. Mendeteksi atribut opsional
    optional = [
        col for col in OPTIONAL_COLUMNS
        if col in df.columns
    ]

    # 6. Membuat hasil import
    result = {
        "event_log": None,
        "dataframe": df,
        "file_name": path.name,
        "file_path": str(path.resolve()),
        "total_cases": int(
            df["case:concept:name"].nunique()
        ),
        "total_events": len(df),
        "available_columns": list(df.columns),
        "available_optional": optional,
        "invalid_timestamp_events": invalid_timestamps,
    }

    print(
        f"[PERFORMANCE] Total import: "
        f"{perf_counter() - started:.2f} detik"
    )

    return result
