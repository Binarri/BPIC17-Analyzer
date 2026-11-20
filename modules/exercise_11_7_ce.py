"""
Modul Exercise 11.7 C-E — Hana.

C: case mengandung minimal satu O_Accepted (contains).
D: case mengandung minimal satu O_Refused (contains).
E: event terakhir pada trace adalah O_Cancelled (endpoint).

Cycle time dihitung dari trace lengkap melalui summarize_cases milik Tiwi.
Urutan event mengikuti timestamp secara stabil; timestamp yang sama mempertahankan
urutan baris asal. Event dengan timestamp kosong diletakkan di akhir untuk
konsisten dengan tampilan detail case aplikasi.
"""

import pandas as pd

from modules.exercise_11_7_ab import (
    CASE_COLUMN,
    TIMESTAMP_COLUMN,
    calculate_case_durations,
    summarize_cases,
)

ACTIVITY_COLUMN = "concept:name"
ACCEPTED = "O_Accepted"
REFUSED = "O_Refused"
CANCELLED = "O_Cancelled"


def _ordered_trace(group):
    """Urutkan trace berdasarkan timestamp secara stabil."""
    return group.sort_values(
        TIMESTAMP_COLUMN,
        kind="stable",
        na_position="last",
    )


def _case_ids_containing(dataframe, activity):
    mask = dataframe[ACTIVITY_COLUMN].eq(activity)
    return dataframe.loc[mask, CASE_COLUMN].drop_duplicates().tolist()


def _case_ids_ending_with(dataframe, activity):
    matched = []
    for case_id, group in dataframe.groupby(CASE_COLUMN, sort=False):
        ordered = _ordered_trace(group)
        if not ordered.empty and ordered.iloc[-1][ACTIVITY_COLUMN] == activity:
            matched.append(case_id)
    return matched


def _evidence(dataframe, case_ids, activity=None, endpoint_only=False):
    selected = dataframe[dataframe[CASE_COLUMN].isin(case_ids)]
    rows = []

    for case_id, group in selected.groupby(CASE_COLUMN, sort=False):
        ordered = _ordered_trace(group)
        if endpoint_only:
            event = ordered.iloc[[-1]]
        elif activity is not None:
            event = ordered[ordered[ACTIVITY_COLUMN].eq(activity)]
        else:
            event = ordered

        for _, row in event.iterrows():
            rows.append({
                CASE_COLUMN: case_id,
                TIMESTAMP_COLUMN: row[TIMESTAMP_COLUMN],
                ACTIVITY_COLUMN: row[ACTIVITY_COLUMN],
                "lifecycle:transition": row.get("lifecycle:transition", None),
                "org:resource": row.get("org:resource", None),
            })

    return pd.DataFrame(rows, columns=[
        CASE_COLUMN, TIMESTAMP_COLUMN, ACTIVITY_COLUMN,
        "lifecycle:transition", "org:resource",
    ])


def _build_result(dataframe, durations, case_ids, activity, rule, endpoint_only=False):
    summary = summarize_cases(durations, case_ids)
    return {
        "rule": rule,
        "activity": activity,
        "case_ids": list(case_ids),
        "summary": summary,
        "evidence": _evidence(
            dataframe, case_ids, activity=activity, endpoint_only=endpoint_only
        ),
    }


def analyze_117_ce(dataframe):
    """
    Menghasilkan analisis 11.7 C, D, dan E dari DataFrame log aktif.

    Output setiap kategori memuat case_ids, jumlah case, valid/invalid
    duration, rata-rata cycle time (hari), tabel durasi, dan evidence event.
    """
    required = {CASE_COLUMN, ACTIVITY_COLUMN, TIMESTAMP_COLUMN}
    missing = required.difference(dataframe.columns)
    if missing:
        raise ValueError("Kolom wajib tidak ditemukan: " + ", ".join(sorted(missing)))
    if dataframe.empty:
        raise ValueError("Event log tidak memiliki event.")

    # Durasi dihitung dari trace lengkap sebelum pemfilteran case.
    durations = calculate_case_durations(dataframe)

    successful_ids = _case_ids_containing(dataframe, ACCEPTED)
    unsuccessful_ids = _case_ids_containing(dataframe, REFUSED)
    canceled_ids = _case_ids_ending_with(dataframe, CANCELLED)

    return {
        "successful": _build_result(
            dataframe, durations, successful_ids, ACCEPTED,
            "Case mengandung minimal satu O_Accepted.",
        ),
        "unsuccessful": _build_result(
            dataframe, durations, unsuccessful_ids, REFUSED,
            "Case mengandung minimal satu O_Refused.",
        ),
        "canceled": _build_result(
            dataframe, durations, canceled_ids, CANCELLED,
            "Event terakhir pada trace adalah O_Cancelled.",
            endpoint_only=True,
        ),
    }
