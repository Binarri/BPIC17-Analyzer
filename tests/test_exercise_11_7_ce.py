import pandas as pd
import pytest

from modules.exercise_11_7_ce import analyze_117_ce


def make_log(rows):
    df = pd.DataFrame(rows, columns=[
        "case:concept:name", "concept:name", "time:timestamp"
    ])
    df["time:timestamp"] = pd.to_datetime(df["time:timestamp"], utc=True)
    return df


def test_contains_accepted_dan_refused_boleh_overlap():
    df = make_log([
        ("A", "O_Accepted", "2026-01-01"),
        ("A", "O_Refused", "2026-01-02"),
        ("B", "O_Accepted", "2026-01-01"),
        ("B", "O_Accepted", "2026-01-03"),
        ("C", "O_Refused", "2026-01-01"),
    ])
    result = analyze_117_ce(df)
    assert result["successful"]["case_ids"] == ["A", "B"]
    assert result["unsuccessful"]["case_ids"] == ["A", "C"]


def test_accepted_dan_refused_berulang_case_dihitung_satu_kali():
    df = make_log([
        ("A", "O_Accepted", "2026-01-01"),
        ("A", "O_Accepted", "2026-01-02"),
        ("A", "O_Refused", "2026-01-03"),
        ("A", "O_Refused", "2026-01-04"),
    ])
    result = analyze_117_ce(df)
    assert result["successful"]["summary"]["total_cases"] == 1
    assert result["unsuccessful"]["summary"]["total_cases"] == 1


def test_canceled_hanya_jika_event_terakhir():
    df = make_log([
        ("A", "O_Create", "2026-01-01"),
        ("A", "O_Cancelled", "2026-01-02"),
        ("B", "O_Cancelled", "2026-01-01"),
        ("B", "O_Accepted", "2026-01-02"),
        ("C", "O_Cancelled", "2026-01-01"),
        ("C", "O_Complete", "2026-01-02"),
        ("D", "O_Create", "2026-01-01"),
        ("D", "O_Cancelled", "2026-01-03"),
    ])
    result = analyze_117_ce(df)
    assert result["canceled"]["case_ids"] == ["A", "D"]


def test_canceled_mengikuti_timestamp_dan_stabil_pada_timestamp_sama():
    df = make_log([
        ("A", "O_Cancelled", "2026-01-02"),
        ("A", "O_Complete", "2026-01-01"),
        ("B", "O_Cancelled", "2026-01-01"),
        ("B", "O_Complete", "2026-01-01"),
    ])
    result = analyze_117_ce(df)
    assert result["canceled"]["case_ids"] == ["A"]


def test_cycle_time_dihitung_dari_trace_lengkap():
    df = make_log([
        ("A", "O_Create", "2026-01-01"),
        ("A", "O_Accepted", "2026-01-03"),
        ("B", "O_Create", "2026-01-01"),
        ("B", "O_Refused", "2026-01-02"),
    ])
    result = analyze_117_ce(df)
    # A dua hari dan B satu hari; rata-rata semua trace = 1.5 hari.
    assert result["successful"]["summary"]["average_cycle_time_days"] == 2.0
    assert result["unsuccessful"]["summary"]["average_cycle_time_days"] == 1.0


def test_evidence_tersedia_dan_canceled_menampilkan_endpoint():
    df = make_log([
        ("A", "O_Create", "2026-01-01"),
        ("A", "O_Cancelled", "2026-01-02"),
    ])
    result = analyze_117_ce(df)
    assert list(result["successful"]["evidence"].columns)
    assert result["canceled"]["evidence"].iloc[0]["concept:name"] == "O_Cancelled"


def test_kolom_wajib_hilang_dan_log_kosong():
    with pytest.raises(ValueError, match="Kolom wajib"):
        analyze_117_ce(pd.DataFrame({"concept:name": ["O_Accepted"]}))
    with pytest.raises(ValueError, match="tidak memiliki event"):
        analyze_117_ce(pd.DataFrame(columns=[
            "case:concept:name", "concept:name", "time:timestamp"
        ]))
