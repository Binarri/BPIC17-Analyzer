"""
Modul Analisis Exercise 11.7 A-B
Penanggung Jawab: Tiwi

Perlakuan timestamp tidak lengkap: case yang memiliki >= 1 event dengan
timestamp kosong (NaT) ditandai is_valid=False, tetap dihitung pada
jumlah case (11.7 A), tetapi dikecualikan dari rata-rata cycle time (11.7 B).
"""

import pandas as pd

CASE_COLUMN = "case:concept:name"
TIMESTAMP_COLUMN = "time:timestamp"
SECONDS_PER_DAY = 86400


def count_unique_cases(dataframe):
    """11.7 A: jumlah case unik pada seluruh log."""
    if dataframe.empty:
        raise ValueError("Event log tidak memiliki event.")
    return int(dataframe[CASE_COLUMN].nunique())


def calculate_case_durations(dataframe):
    """
    Durasi per case = timestamp terakhir - timestamp pertama.
    Kolom keluaran: case:concept:name, start_time, end_time,
    valid_count, total_events, duration, duration_days, is_valid
    """
    if dataframe.empty:
        raise ValueError("Event log tidak memiliki event.")

    grouped = (
        dataframe.groupby(CASE_COLUMN, sort=False)[TIMESTAMP_COLUMN]
        .agg(
            start_time="min",
            end_time="max",
            valid_count="count",   # tidak menghitung NaT
            total_events="size",   # menghitung semua event
        )
        .reset_index()
    )

    grouped["is_valid"] = grouped["valid_count"] == grouped["total_events"]
    grouped["duration"] = grouped["end_time"] - grouped["start_time"]
    grouped.loc[~grouped["is_valid"], "duration"] = pd.NaT
    grouped["duration_days"] = (
        grouped["duration"].dt.total_seconds() / SECONDS_PER_DAY
    )
    return grouped


def summarize_cases(durations, case_ids=None):
    """
    Ringkasan jumlah case dan rata-rata cycle time (hari) dari tabel durasi
    yang sudah dihitung. Jika case_ids diberikan, hanya case tersebut.
    Dipakai ulang oleh Hana (11.7 C-E) tanpa menghitung ulang groupby.
    """
    subset = durations
    if case_ids is not None:
        subset = durations[durations[CASE_COLUMN].isin(set(case_ids))]

    valid = subset["duration_days"].dropna()
    return {
        "total_cases": int(len(subset)),
        "valid_cases": int(valid.count()),
        "invalid_cases": int(len(subset) - valid.count()),
        "average_cycle_time_days": float(valid.mean()) if not valid.empty else None,
        "case_durations": subset,
    }


def calculate_average_cycle_time(dataframe):
    """11.7 B: rata-rata cycle time seluruh case (hari)."""
    return summarize_cases(calculate_case_durations(dataframe))