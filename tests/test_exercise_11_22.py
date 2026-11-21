import pandas as pd
import pytest

from modules.exercise_11_22 import analyze_1122

def make_log(rows):
    df = pd.DataFrame(rows, columns=[
        "case:concept:name", "concept:name", "time:timestamp"
    ])
    df["time:timestamp"] = pd.to_datetime(df["time:timestamp"], utc=True)
    return df


def test_cancelled_lalu_accepted_termasuk():
    df = make_log([
        ("A", "O_Cancelled", "2026-01-01"),
        ("A", "O_Accepted", "2026-01-02"),
        ("B", "O_Accepted", "2026-01-01"),
        ("B", "O_Cancelled", "2026-01-02"),
    ])

    result = analyze_1122(df)

    assert result["case_ids"] == ["A"]


def test_cancelled_lalu_accepted_tidak_harus_berurutan():
    df = make_log([
        ("A", "O_Cancelled", "2026-01-01"),
        ("A", "O_Create", "2026-01-02"),
        ("A", "O_Complete", "2026-01-03"),
        ("A", "O_Accepted", "2026-01-04"),
    ])

    result = analyze_1122(df)

    assert result["case_ids"] == ["A"]


def test_accepted_lalu_cancelled_tidak_termasuk():
    df = make_log([
        ("A", "O_Accepted", "2026-01-01"),
        ("A", "O_Cancelled", "2026-01-02"),
    ])

    result = analyze_1122(df)

    assert result["case_ids"] == []


def test_beberapa_pasangan_dalam_satu_case_dihitung_satu_kali():
    df = make_log([
        ("A", "O_Cancelled", "2026-01-01"),
        ("A", "O_Accepted", "2026-01-02"),
        ("A", "O_Cancelled", "2026-01-03"),
        ("A", "O_Accepted", "2026-01-04"),
        ("B", "O_Create", "2026-01-01"),
    ])

    result = analyze_1122(df)

    assert result["case_ids"] == ["A"]
    assert result["summary"]["matched_cases"] == 1


def test_persentase_menggunakan_semua_active_cases():
    df = make_log([
        ("A", "O_Cancelled", "2026-01-01"),
        ("A", "O_Accepted", "2026-01-02"),
        ("B", "O_Accepted", "2026-01-01"),
        ("C", "O_Create", "2026-01-01"),
        ("D", "O_Cancelled", "2026-01-01"),
    ])

    result = analyze_1122(df)

    assert result["summary"]["matched_cases"] == 1
    assert result["summary"]["total_cases"] == 4
    assert result["summary"]["percentage"] == 25.0


def test_evidence_menampilkan_cancelled_dan_accepted():
    df = make_log([
        ("A", "O_Cancelled", "2026-01-01"),
        ("A", "O_Create", "2026-01-02"),
        ("A", "O_Accepted", "2026-01-03"),
    ])

    result = analyze_1122(df)

    evidence = result["evidence"]

    assert evidence.iloc[0]["cancelled_activity"] == "O_Cancelled"
    assert evidence.iloc[0]["accepted_activity"] == "O_Accepted"
    
def test_kolom_wajib_hilang_dan_log_kosong():
    with pytest.raises(ValueError, match="Kolom wajib"):
        analyze_1122(pd.DataFrame({
            "concept:name": ["O_Cancelled"]
        }))

    with pytest.raises(ValueError, match="tidak memiliki event"):
        analyze_1122(pd.DataFrame(columns=[
            "case:concept:name",
            "concept:name",
            "time:timestamp",
        ]))