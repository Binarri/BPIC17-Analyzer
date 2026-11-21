"""
Modul Exercise 11.15 dan 11.18 — Annis.

11.15: case di mana aktivitas target (W_Assess Potential Fraud) diselesaikan
       minimal dua kali. Hanya event dengan lifecycle:transition = "complete"
       yang dihitung; schedule/start/suspend/resume/ate_abort/withdraw diabaikan.
11.18: lanjutan 11.15 — minimal dua complete occurrence aktivitas target dalam
       satu case dilakukan oleh resource (org:resource) yang SAMA dan teridentifikasi.

Identifikasi complete: nilai lifecycle:transition dibandingkan setelah di-strip
dan di-lowercase dengan "complete" (BPIC17 memakai "complete").

Resource tidak teridentifikasi: NaN/None, string kosong, atau "UNKNOWN"
(nilai default org:resource pada global attribute BPIC17). Event seperti ini
tetap dihitung pada 11.15, tetapi TIDAK pernah dianggap sebagai resource yang
sama pada 11.18.

Nama aktivitas: pada file BPIC17 ejaannya "W_Assess potential fraud", sedangkan
soal menulis "W_Assess Potential Fraud". Karena itu aktivitas target dipilih
pengguna dari daftar aktivitas log; default-nya dideteksi otomatis tanpa
membedakan huruf besar/kecil (detect_target_activity).

Urutan event dalam trace: diurutkan menurut timestamp secara stabil; timestamp
yang sama mempertahankan urutan baris asal XES; timestamp kosong di akhir
(konsisten dengan modul 11.7 C-E).

Tidak ada event yang dihapus dari log; filter hanya memilih case.
"""

import pandas as pd

CASE_COLUMN = "case:concept:name"
ACTIVITY_COLUMN = "concept:name"
TIMESTAMP_COLUMN = "time:timestamp"
LIFECYCLE_COLUMN = "lifecycle:transition"
RESOURCE_COLUMN = "org:resource"

DEFAULT_TARGET_ACTIVITY = "W_Assess Potential Fraud"
COMPLETE_VALUE = "complete"
MIN_OCCURRENCES = 2
UNIDENTIFIED_RESOURCES = {"", "UNKNOWN"}

ALL_LIFECYCLES_LABEL = "(semua lifecycle, tanpa filter)"

EVIDENCE_COLUMNS = [
    CASE_COLUMN,
    "trace_position",
    TIMESTAMP_COLUMN,
    ACTIVITY_COLUMN,
    LIFECYCLE_COLUMN,
    RESOURCE_COLUMN,
    "counted",
]


# ----------------------------------------------------------------------
# Helper umum
# ----------------------------------------------------------------------
def _normalize(text):
    return " ".join(str(text).split()).casefold()


def list_activities(dataframe):
    """Daftar nama aktivitas unik pada log (terurut alfabet)."""
    if ACTIVITY_COLUMN not in dataframe.columns:
        return []
    return sorted(dataframe[ACTIVITY_COLUMN].dropna().astype(str).unique().tolist())


def detect_target_activity(dataframe, target=DEFAULT_TARGET_ACTIVITY):
    """
    Cari nama aktivitas pada log yang cocok dengan target tanpa membedakan
    huruf besar/kecil dan spasi berlebih. Mengembalikan ejaan asli di log,
    atau None bila tidak ada.
    """
    wanted = _normalize(target)
    for name in list_activities(dataframe):
        if _normalize(name) == wanted:
            return name
    return None


def is_complete(lifecycle_series):
    """Mask boolean: True jika lifecycle:transition bernilai complete."""
    return (
        lifecycle_series.astype("string").str.strip().str.lower().eq(COMPLETE_VALUE)
        .fillna(False)
        .astype(bool)
    )


def is_identified_resource(resource_series):
    """Mask boolean: True jika resource terisi dan bukan nilai default UNKNOWN."""
    text = resource_series.astype("string").str.strip()
    unidentified = text.isna() | text.str.upper().isin(UNIDENTIFIED_RESOURCES)
    return ~unidentified.fillna(True).astype(bool)


def _ordered(dataframe):
    """Urutkan per case menurut timestamp secara stabil (NaT di akhir)."""
    return dataframe.sort_values(
        [CASE_COLUMN, TIMESTAMP_COLUMN], kind="stable", na_position="last"
    )


def _trace_positions(dataframe, case_ids):
    """
    Posisi (1-based) setiap event di dalam trace lengkapnya, hanya untuk
    case_ids terpilih. Mengembalikan Series ber-index sama dengan dataframe.
    """
    if not case_ids:
        return pd.Series(dtype="int64")
    subset = dataframe[dataframe[CASE_COLUMN].isin(set(case_ids))]
    ordered = subset.sort_values(TIMESTAMP_COLUMN, kind="stable", na_position="last")
    return ordered.groupby(CASE_COLUMN, sort=False).cumcount() + 1


def _validate(dataframe):
    required = {CASE_COLUMN, ACTIVITY_COLUMN, TIMESTAMP_COLUMN}
    missing = required.difference(dataframe.columns)
    if missing:
        raise ValueError("Kolom wajib tidak ditemukan: " + ", ".join(sorted(missing)))
    if dataframe.empty:
        raise ValueError("Event log tidak memiliki event.")
    if LIFECYCLE_COLUMN not in dataframe.columns:
        raise ValueError(
            "Atribut lifecycle:transition tidak tersedia, sehingga complete "
            "occurrence tidak dapat diidentifikasi."
        )


def _evidence_frame(rows, positions, counted_mask):
    if rows.empty:
        return pd.DataFrame(columns=EVIDENCE_COLUMNS)
    evidence = pd.DataFrame({
        CASE_COLUMN: rows[CASE_COLUMN],
        "trace_position": positions.reindex(rows.index).astype("Int64"),
        TIMESTAMP_COLUMN: rows[TIMESTAMP_COLUMN],
        ACTIVITY_COLUMN: rows[ACTIVITY_COLUMN],
        LIFECYCLE_COLUMN: rows[LIFECYCLE_COLUMN],
        RESOURCE_COLUMN: rows[RESOURCE_COLUMN] if RESOURCE_COLUMN in rows else pd.NA,
        "counted": counted_mask.reindex(rows.index).astype(bool),
    })
    return evidence.reset_index(drop=True)


# ----------------------------------------------------------------------
# Analisis utama
# ----------------------------------------------------------------------
def analyze_1115_1118(dataframe, activity=None, min_occurrences=MIN_OCCURRENCES):
    """
    Menghitung Exercise 11.15 dan 11.18 dari DataFrame log aktif.

    Parameter
    ---------
    dataframe : DataFrame hasil modules.importer.import_xes.
    activity  : nama aktivitas target persis seperti di log. Jika None,
                dideteksi otomatis dari DEFAULT_TARGET_ACTIVITY.
    min_occurrences : minimal jumlah complete (default 2 sesuai soal).

    Keluaran (dict)
    ---------------
    activity, total_cases_log, target_events, resource_available,
    ex_1115: rule, case_ids, total_cases, per_case, evidence
    ex_1118: rule, case_ids, total_cases, per_case, evidence,
             unidentified_resource_events
    comparison: tabel pembanding per lifecycle (BUKAN jawaban soal).

    Raises ValueError bila kolom wajib/lifecycle hilang, log kosong, atau
    aktivitas target tidak ditemukan.
    """
    _validate(dataframe)

    if activity is None:
        activity = detect_target_activity(dataframe)
        if activity is None:
            raise ValueError(
                f"Aktivitas '{DEFAULT_TARGET_ACTIVITY}' tidak ditemukan pada log "
                "(pencocokan tanpa membedakan huruf besar/kecil)."
            )
    elif activity not in set(list_activities(dataframe)):
        raise ValueError(f"Aktivitas '{activity}' tidak ditemukan pada log aktif.")

    resource_available = RESOURCE_COLUMN in dataframe.columns
    total_cases_log = int(dataframe[CASE_COLUMN].nunique())

    # Semua event aktivitas target (semua lifecycle), urut per case.
    target = _ordered(dataframe[dataframe[ACTIVITY_COLUMN].astype(str) == activity])
    complete_mask = is_complete(target[LIFECYCLE_COLUMN])
    complete = target[complete_mask]

    # ---------------- 11.15 ----------------
    complete_counts = complete.groupby(CASE_COLUMN, sort=False).size()
    ids_1115 = complete_counts[complete_counts >= min_occurrences].index.tolist()

    lifecycle_text = target[LIFECYCLE_COLUMN].astype("string").str.strip().str.lower()
    per_case_1115 = pd.DataFrame({
        CASE_COLUMN: ids_1115,
        "complete_count": [int(complete_counts[c]) for c in ids_1115],
        "target_events_all_lifecycle": [
            int((target[CASE_COLUMN] == c).sum()) for c in ids_1115
        ],
    })
    if not per_case_1115.empty:
        per_case_1115["lifecycle_detail"] = [
            ", ".join(
                f"{name}={count}"
                for name, count in lifecycle_text[target[CASE_COLUMN] == c]
                .value_counts().sort_index().items()
            )
            for c in ids_1115
        ]
    else:
        per_case_1115["lifecycle_detail"] = pd.Series(dtype="string")

    positions = _trace_positions(dataframe, ids_1115)
    evidence_rows_1115 = target[target[CASE_COLUMN].isin(set(ids_1115))]
    evidence_1115 = _evidence_frame(evidence_rows_1115, positions, complete_mask)

    # ---------------- 11.18 ----------------
    unidentified_events = 0
    per_case_1118 = pd.DataFrame(columns=[CASE_COLUMN, RESOURCE_COLUMN, "complete_count"])
    ids_1118 = []
    evidence_1118 = pd.DataFrame(columns=EVIDENCE_COLUMNS)

    if resource_available:
        in_1115 = complete[complete[CASE_COLUMN].isin(set(ids_1115))]
        identified = is_identified_resource(in_1115[RESOURCE_COLUMN])
        unidentified_events = int((~identified).sum())

        named = in_1115[identified].copy()
        named["_resource"] = named[RESOURCE_COLUMN].astype("string").str.strip()
        by_resource = (
            named.groupby([CASE_COLUMN, "_resource"], sort=False)
            .size()
            .reset_index(name="complete_count")
        )
        same = by_resource[by_resource["complete_count"] >= min_occurrences]
        per_case_1118 = same.rename(columns={"_resource": RESOURCE_COLUMN}).reset_index(drop=True)
        per_case_1118["complete_count"] = per_case_1118["complete_count"].astype(int)
        ids_1118 = list(dict.fromkeys(per_case_1118[CASE_COLUMN].tolist()))

        pairs = set(zip(per_case_1118[CASE_COLUMN], per_case_1118[RESOURCE_COLUMN]))
        keep = pd.Series(
            [
                (case_id, resource) in pairs
                for case_id, resource in zip(named[CASE_COLUMN], named["_resource"])
            ],
            index=named.index,
            dtype=bool,
        )
        evidence_rows_1118 = named.loc[keep].drop(columns="_resource")
        evidence_1118 = _evidence_frame(
            evidence_rows_1118, positions, pd.Series(True, index=evidence_rows_1118.index)
        )

    rule_1115 = (
        f"Case dipilih jika aktivitas '{activity}' dengan lifecycle:transition = "
        f"complete muncul minimal {min_occurrences}x dalam satu case. "
        "Lifecycle lain (schedule/start/suspend/resume/ate_abort/withdraw) tidak dihitung."
    )
    rule_1118 = (
        f"Dari case 11.15, case dipilih jika minimal {min_occurrences} complete "
        f"occurrence '{activity}' dilakukan oleh org:resource yang sama dan "
        "teridentifikasi. Resource kosong/UNKNOWN tidak dianggap sama."
    )

    return {
        "activity": activity,
        "total_cases_log": total_cases_log,
        "target_events": int(len(target)),
        "resource_available": resource_available,
        "ex_1115": {
            "rule": rule_1115,
            "case_ids": ids_1115,
            "total_cases": len(ids_1115),
            "per_case": per_case_1115,
            "evidence": evidence_1115,
        },
        "ex_1118": {
            "rule": rule_1118 if resource_available else
                    "Atribut org:resource tidak tersedia; 11.18 tidak dapat dihitung.",
            "case_ids": ids_1118,
            "total_cases": len(ids_1118),
            "per_case": per_case_1118,
            "evidence": evidence_1118,
            "unidentified_resource_events": unidentified_events,
        },
        "comparison": lifecycle_comparison(target, resource_available, min_occurrences),
    }


def lifecycle_comparison(target_events, resource_available=True, min_occurrences=MIN_OCCURRENCES):
    """
    Tabel pembanding (analisis tambahan, BUKAN jawaban soal): untuk setiap
    lifecycle aktivitas target, berapa event, berapa case yang memuatnya, berapa
    case dengan >= min_occurrences, dan berapa case dengan >= min_occurrences
    oleh resource yang sama. Baris terakhir mengabaikan lifecycle sama sekali,
    mendekati cara tool yang tidak memfilter lifecycle (mis. Disco pada buku).
    """
    columns = [
        "lifecycle", "event_count", "cases_with_event",
        "cases_min_occurrences", "cases_min_same_resource",
    ]
    if target_events.empty:
        return pd.DataFrame(columns=columns)

    lifecycle = target_events[LIFECYCLE_COLUMN].astype("string").str.strip().str.lower()
    frame = pd.DataFrame({
        CASE_COLUMN: target_events[CASE_COLUMN].values,
        "lifecycle": lifecycle.fillna("(kosong)").values,
    })
    if resource_available:
        identified = is_identified_resource(target_events[RESOURCE_COLUMN]).values
        frame["_resource"] = target_events[RESOURCE_COLUMN].astype("string").str.strip().values
        frame["_identified"] = identified

    def summarize(label, part):
        per_case = part.groupby(CASE_COLUMN, sort=False).size()
        same_resource = 0
        if resource_available:
            named = part[part["_identified"]]
            counts = named.groupby([CASE_COLUMN, "_resource"], sort=False).size()
            same_resource = int(
                counts[counts >= min_occurrences].index.get_level_values(0).nunique()
            )
        return {
            "lifecycle": label,
            "event_count": int(len(part)),
            "cases_with_event": int(per_case.size),
            "cases_min_occurrences": int((per_case >= min_occurrences).sum()),
            "cases_min_same_resource": same_resource,
        }

    rows = [summarize(name, frame[frame["lifecycle"] == name])
            for name in sorted(frame["lifecycle"].unique())]
    rows.append(summarize(ALL_LIFECYCLES_LABEL, frame))
    return pd.DataFrame(rows, columns=columns)
