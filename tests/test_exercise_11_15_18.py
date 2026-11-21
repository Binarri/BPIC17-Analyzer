import pandas as pd
import pytest

from modules.exercise_11_15_18 import (
    ALL_LIFECYCLES_LABEL,
    analyze_1115_1118,
    detect_target_activity,
)

FRAUD = "W_Assess potential fraud"  # ejaan seperti pada file BPIC17


def make_log(rows, with_resource=True):
    columns = [
        "case:concept:name", "concept:name", "lifecycle:transition",
        "org:resource", "time:timestamp",
    ]
    df = pd.DataFrame(rows, columns=columns)
    df["time:timestamp"] = pd.to_datetime(df["time:timestamp"], utc=True)
    if not with_resource:
        df = df.drop(columns="org:resource")
    return df


def fraud(case, lifecycle, resource, ts):
    return (case, FRAUD, lifecycle, resource, ts)


def test_deteksi_nama_aktivitas_tanpa_membedakan_huruf():
    df = make_log([fraud("A", "complete", "U1", "2026-01-01")])
    assert detect_target_activity(df) == FRAUD
    assert detect_target_activity(df, "w_assess  POTENTIAL fraud") == FRAUD
    assert detect_target_activity(df, "W_Tidak Ada") is None


def test_dijadwalkan_dua_kali_complete_sekali_tidak_lolos_1115():
    df = make_log([
        fraud("A", "schedule", "U1", "2026-01-01"),
        fraud("A", "start", "U1", "2026-01-02"),
        fraud("A", "complete", "U1", "2026-01-03"),
        fraud("A", "schedule", "U1", "2026-01-04"),
        fraud("A", "start", "U1", "2026-01-05"),
        fraud("A", "ate_abort", "U1", "2026-01-06"),
    ])
    result = analyze_1115_1118(df)
    assert result["ex_1115"]["case_ids"] == []
    assert result["ex_1118"]["case_ids"] == []


def test_dua_complete_resource_berbeda_lolos_1115_tidak_lolos_1118():
    df = make_log([
        fraud("A", "complete", "U1", "2026-01-01"),
        fraud("A", "complete", "U2", "2026-01-02"),
    ])
    result = analyze_1115_1118(df)
    assert result["ex_1115"]["case_ids"] == ["A"]
    assert result["ex_1118"]["case_ids"] == []


def test_dua_complete_resource_sama_lolos_1115_dan_1118():
    df = make_log([
        fraud("A", "complete", "U1", "2026-01-01"),
        ("A", "O_Created", "complete", "U9", "2026-01-02"),
        fraud("A", "complete", "U1", "2026-01-03"),
    ])
    result = analyze_1115_1118(df)
    assert result["ex_1115"]["case_ids"] == ["A"]
    assert result["ex_1118"]["case_ids"] == ["A"]
    per_case = result["ex_1118"]["per_case"]
    assert per_case.iloc[0]["org:resource"] == "U1"
    assert per_case.iloc[0]["complete_count"] == 2


def test_resource_kosong_tidak_dianggap_sama():
    df = make_log([
        fraud("A", "complete", None, "2026-01-01"),
        fraud("A", "complete", None, "2026-01-02"),
        fraud("B", "complete", "", "2026-01-01"),
        fraud("B", "complete", "  ", "2026-01-02"),
        fraud("C", "complete", "UNKNOWN", "2026-01-01"),
        fraud("C", "complete", "UNKNOWN", "2026-01-02"),
    ])
    result = analyze_1115_1118(df)
    assert result["ex_1115"]["case_ids"] == ["A", "B", "C"]
    assert result["ex_1118"]["case_ids"] == []
    assert result["ex_1118"]["unidentified_resource_events"] == 6


def test_case_dihitung_sekali_dan_jumlah_complete_per_case():
    df = make_log([
        fraud("A", "complete", "U1", "2026-01-01"),
        fraud("A", "complete", "U1", "2026-01-02"),
        fraud("A", "complete", "U1", "2026-01-03"),
        fraud("A", "complete", "U2", "2026-01-04"),
        fraud("B", "complete", "U1", "2026-01-01"),
    ])
    result = analyze_1115_1118(df)
    assert result["ex_1115"]["total_cases"] == 1
    assert result["ex_1115"]["per_case"].iloc[0]["complete_count"] == 4
    assert result["ex_1118"]["total_cases"] == 1
    assert result["ex_1118"]["per_case"].iloc[0]["complete_count"] == 3


def test_lifecycle_dibandingkan_tanpa_membedakan_huruf():
    df = make_log([
        fraud("A", "Complete", "U1", "2026-01-01"),
        fraud("A", " COMPLETE ", "U1", "2026-01-02"),
    ])
    assert analyze_1115_1118(df)["ex_1115"]["case_ids"] == ["A"]


def test_evidence_memuat_semua_lifecycle_dengan_penanda_counted():
    df = make_log([
        ("A", "A_Create Application", "complete", "U0", "2026-01-01"),
        fraud("A", "schedule", "U1", "2026-01-02"),
        fraud("A", "complete", "U1", "2026-01-03"),
        fraud("A", "complete", "U1", "2026-01-04"),
    ])
    evidence = analyze_1115_1118(df)["ex_1115"]["evidence"]
    assert evidence["lifecycle:transition"].tolist() == ["schedule", "complete", "complete"]
    assert evidence["counted"].tolist() == [False, True, True]
    # posisi dalam trace lengkap (event pertama A_Create Application = 1)
    assert evidence["trace_position"].tolist() == [2, 3, 4]


def test_pembanding_tanpa_filter_lifecycle_lebih_banyak():
    df = make_log([
        fraud("A", "schedule", "U1", "2026-01-01"),
        fraud("A", "schedule", "U1", "2026-01-02"),
        fraud("A", "complete", "U1", "2026-01-03"),
    ])
    result = analyze_1115_1118(df)
    comparison = result["comparison"].set_index("lifecycle")
    assert result["ex_1115"]["total_cases"] == 0
    assert comparison.loc["complete", "cases_min_occurrences"] == 0
    assert comparison.loc["schedule", "cases_min_occurrences"] == 1
    assert comparison.loc[ALL_LIFECYCLES_LABEL, "cases_min_occurrences"] == 1
    assert comparison.loc[ALL_LIFECYCLES_LABEL, "cases_min_same_resource"] == 1


def test_tanpa_resource_1115_tetap_jalan():
    df = make_log([
        fraud("A", "complete", None, "2026-01-01"),
        fraud("A", "complete", None, "2026-01-02"),
    ], with_resource=False)
    result = analyze_1115_1118(df)
    assert result["ex_1115"]["case_ids"] == ["A"]
    assert result["resource_available"] is False
    assert result["ex_1118"]["case_ids"] == []


def test_error_kolom_lifecycle_hilang_dan_aktivitas_tidak_ada():
    df = make_log([fraud("A", "complete", "U1", "2026-01-01")])
    with pytest.raises(ValueError, match="lifecycle"):
        analyze_1115_1118(df.drop(columns="lifecycle:transition"))
    with pytest.raises(ValueError, match="tidak ditemukan"):
        analyze_1115_1118(df, activity="W_Tidak Ada")
    other = make_log([("A", "O_Created", "complete", "U1", "2026-01-01")])
    with pytest.raises(ValueError, match="tidak ditemukan"):
        analyze_1115_1118(other)
    with pytest.raises(ValueError, match="tidak memiliki event"):
        analyze_1115_1118(df.iloc[0:0])
