"""
Unit test Exercise 11.7 A-B (Tiwi) memakai log sintetis.
Jalankan dari folder proyek:  python -m pytest tests -v
"""

import pandas as pd
import pytest

from modules.exercise_11_7_ab import (
    CASE_COLUMN,
    TIMESTAMP_COLUMN,
    calculate_average_cycle_time,
    calculate_case_durations,
    count_unique_cases,
    summarize_cases,
)


def make_log(rows):
    df = pd.DataFrame(rows, columns=[CASE_COLUMN, TIMESTAMP_COLUMN])
    df[TIMESTAMP_COLUMN] = pd.to_datetime(df[TIMESTAMP_COLUMN], utc=True)
    return df


def test_case_dihitung_sekali_walau_banyak_event():
    df = make_log([("A", "2026-01-01"), ("A", "2026-01-02"), ("A", "2026-01-03")])
    assert count_unique_cases(df) == 1


def test_durasi_dan_rata_rata_dalam_hari():
    df = make_log([
        ("A", "2026-01-01"), ("A", "2026-01-03"),
        ("B", "2026-01-01"), ("B", "2026-01-02"),
    ])
    result = calculate_average_cycle_time(df)
    assert result["average_cycle_time_days"] == 1.5  # (2 + 1) / 2


def test_urutan_baris_tidak_mempengaruhi_durasi():
    df = make_log([("A", "2026-01-03"), ("A", "2026-01-01"), ("A", "2026-01-02")])
    durations = calculate_case_durations(df)
    assert durations.loc[0, "duration_days"] == 2.0


def test_timestamp_kosong_dikecualikan_dari_rata_rata_tapi_tetap_dihitung():
    df = make_log([
        ("A", "2026-01-01"), ("A", None),
        ("B", "2026-01-01"), ("B", "2026-01-02"),
    ])
    result = calculate_average_cycle_time(df)
    assert count_unique_cases(df) == 2
    assert result["total_cases"] == 2
    assert result["invalid_cases"] == 1
    assert result["valid_cases"] == 1
    assert result["average_cycle_time_days"] == 1.0


def test_kolom_is_valid():
    df = make_log([("A", "2026-01-01"), ("A", None), ("B", "2026-01-01")])
    durations = calculate_case_durations(df).set_index(CASE_COLUMN)
    assert not durations.loc["A", "is_valid"]
    assert durations.loc["B", "is_valid"]


def test_subset_case_ids_untuk_hana():
    df = make_log([
        ("A", "2026-01-01"), ("A", "2026-01-03"),
        ("B", "2026-01-01"), ("B", "2026-01-02"),
    ])
    result = summarize_cases(calculate_case_durations(df), ["A"])
    assert result["total_cases"] == 1
    assert result["average_cycle_time_days"] == 2.0


def test_semua_invalid_menghasilkan_none():
    df = make_log([("A", None), ("A", "2026-01-01")])
    result = calculate_average_cycle_time(df)
    assert result["average_cycle_time_days"] is None


def test_log_kosong_error():
    df = make_log([])
    with pytest.raises(ValueError):
        count_unique_cases(df)
    with pytest.raises(ValueError):
        calculate_case_durations(df)