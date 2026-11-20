import pandas as pd
import pytest
import sys
import types

# Stub ringan agar unit test importer tetap bisa diuji tanpa instalasi PM4Py;
# fungsi read_xes selalu dimock pada test yang memerlukannya.
sys.modules.setdefault('pm4py', types.SimpleNamespace(read_xes=None))

from modules import importer


def valid_df():
    return pd.DataFrame({
        "case:concept:name": ["A", "A", "B"],
        "concept:name": ["Start", "O_Accepted", "O_Refused"],
        "time:timestamp": pd.to_datetime(
            ["2026-01-01", "2026-01-02", "2026-01-03"], utc=True
        ),
        "lifecycle:transition": ["complete"] * 3,
        "org:resource": ["R1"] * 3,
    })


def test_importer_membaca_dan_mengembalikan_ringkasan(tmp_path, monkeypatch):
    file_path = tmp_path / "sample.xes"
    file_path.write_text("dummy")
    monkeypatch.setattr(importer.pm4py, "read_xes", lambda *a, **k: valid_df())
    result = importer.import_xes(file_path)
    assert result["total_cases"] == 2
    assert result["total_events"] == 3
    assert "lifecycle:transition" in result["available_optional"]
    assert "org:resource" in result["available_optional"]


def test_importer_file_tidak_ditemukan(tmp_path):
    with pytest.raises(FileNotFoundError):
        importer.import_xes(tmp_path / "missing.xes")


def test_importer_menolak_ekstensi_selain_xes(tmp_path):
    file_path = tmp_path / "sample.csv"
    file_path.write_text("x")
    with pytest.raises(ValueError, match=r"\.xes"):
        importer.import_xes(file_path)


def test_importer_menolak_log_kosong(tmp_path, monkeypatch):
    file_path = tmp_path / "empty.xes"
    file_path.write_text("dummy")
    monkeypatch.setattr(importer.pm4py, "read_xes", lambda *a, **k: pd.DataFrame())
    with pytest.raises(ValueError, match="tidak memiliki event"):
        importer.import_xes(file_path)


@pytest.mark.parametrize("missing_column", [
    "case:concept:name", "concept:name", "time:timestamp"
])
def test_importer_menolak_atribut_wajib_hilang(tmp_path, monkeypatch, missing_column):
    file_path = tmp_path / "sample.xes"
    file_path.write_text("dummy")
    df = valid_df().drop(columns=[missing_column])
    monkeypatch.setattr(importer.pm4py, "read_xes", lambda *a, **k: df)
    with pytest.raises(ValueError, match="Atribut wajib"):
        importer.import_xes(file_path)


def test_importer_mendeteksi_timestamp_tidak_valid(tmp_path, monkeypatch):
    file_path = tmp_path / "sample.xes"
    file_path.write_text("dummy")
    df = valid_df()
    df["time:timestamp"] = [None, None, None]
    monkeypatch.setattr(importer.pm4py, "read_xes", lambda *a, **k: df)
    with pytest.raises(ValueError, match="Semua timestamp"):
        importer.import_xes(file_path)


def test_importer_tetap_menerima_atribut_opsional_tidak_tersedia(tmp_path, monkeypatch):
    file_path = tmp_path / "sample.xes"
    file_path.write_text("dummy")
    df = valid_df().drop(columns=["lifecycle:transition", "org:resource"])
    monkeypatch.setattr(importer.pm4py, "read_xes", lambda *a, **k: df)
    result = importer.import_xes(file_path)
    assert result["available_optional"] == []
