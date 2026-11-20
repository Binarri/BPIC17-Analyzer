import pandas as pd

from modules.overview import generate_overview


def test_overview_statistik_dan_durasi_case():
    df = pd.DataFrame({
        "case:concept:name": ["A", "A", "B", "B"],
        "concept:name": ["Start", "O_Accepted", "Start", "O_Refused"],
        "time:timestamp": pd.to_datetime(
            ["2026-01-01", "2026-01-03", "2026-01-01", "2026-01-02"], utc=True
        ),
    })
    result = generate_overview(df)
    assert result["total_cases"] == 2
    assert result["total_events"] == 4
    assert result["average_cycle_time_days"] == 1.5
    assert result["valid_duration_cases"] == 2
    assert result["invalid_duration_cases"] == 0
    assert result["activity_frequency"]["Frequency"].sum() == 4


def test_overview_timestamp_tidak_lengkap_dikecualikan_dari_rata_rata():
    df = pd.DataFrame({
        "case:concept:name": ["A", "A", "B", "B"],
        "concept:name": ["Start", "End", "Start", "End"],
        "time:timestamp": pd.to_datetime(
            ["2026-01-01", None, "2026-01-01", "2026-01-02"], utc=True
        ),
    })
    result = generate_overview(df)
    assert result["total_cases"] == 2
    assert result["valid_duration_cases"] == 1
    assert result["invalid_duration_cases"] == 1
    assert result["average_cycle_time_days"] == 1.0


def test_overview_menolak_dataframe_kosong():
    import pytest
    with pytest.raises(ValueError):
        generate_overview(pd.DataFrame())
