import pandas as pd

from modules.exercise_11_7_ab import (
    CASE_COLUMN,
    TIMESTAMP_COLUMN,
)

ACTIVITY_COLUMN = "concept:name"
CANCELLED = "O_Cancelled"
ACCEPTED = "O_Accepted"


def _ordered_trace(group):
    """Urutkan trace berdasarkan timestamp secara stabil."""
    return group.sort_values(
        TIMESTAMP_COLUMN,
        kind="stable",
        na_position="last",
    )


def _find_matching_cases(dataframe):
    """Cari case yang memiliki O_Cancelled sebelum O_Accepted."""
    matched_cases = []
    evidence_rows = []

    for case_id, group in dataframe.groupby(CASE_COLUMN, sort=False):
        ordered = _ordered_trace(group)

        cancelled_row = None

        for _, row in ordered.iterrows():
            activity = row[ACTIVITY_COLUMN]

            if activity == CANCELLED:
                cancelled_row = row

            elif activity == ACCEPTED and cancelled_row is not None:
                matched_cases.append(case_id)

                evidence_rows.append({
                    CASE_COLUMN: case_id,
                    "cancelled_timestamp": cancelled_row[TIMESTAMP_COLUMN],
                    "cancelled_activity": CANCELLED,
                    "accepted_timestamp": row[TIMESTAMP_COLUMN],
                    "accepted_activity": ACCEPTED,
                })

                break

    return matched_cases, evidence_rows


def analyze_1122(dataframe):
    """
    Menganalisis Exercise 11.22.

    Sebuah case termasuk jika O_Cancelled terjadi lebih dahulu
    daripada O_Accepted dalam trace yang sama.
    """
    required = {
        CASE_COLUMN,
        ACTIVITY_COLUMN,
        TIMESTAMP_COLUMN,
    }

    missing = required.difference(dataframe.columns)

    if missing:
        raise ValueError(
            "Kolom wajib tidak ditemukan: " + ", ".join(sorted(missing))
        )

    if dataframe.empty:
        raise ValueError("Event log tidak memiliki event.")

    matched_cases, evidence_rows = _find_matching_cases(dataframe)

    total_cases = dataframe[CASE_COLUMN].nunique()
    matched_cases_count = len(matched_cases)

    percentage = (matched_cases_count / total_cases) * 100

    evidence = pd.DataFrame(
        evidence_rows,
        columns=[
            CASE_COLUMN,
            "cancelled_timestamp",
            "cancelled_activity",
            "accepted_timestamp",
            "accepted_activity",
        ],
    )

    return {
        "rule": (
            "Case memiliki O_Cancelled yang terjadi lebih dahulu "
            "daripada O_Accepted."
        ),
        "case_ids": matched_cases,
        "summary": {
            "matched_cases": matched_cases_count,
            "total_cases": total_cases,
            "percentage": percentage,
        },
        "evidence": evidence,
    }