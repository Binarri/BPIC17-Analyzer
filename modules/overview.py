import pandas as pd

CASE_COLUMN = "case:concept:name"
ACTIVITY_COLUMN = "concept:name"
TIMESTAMP_COLUMN = "time:timestamp"


def generate_overview(dataframe):
    """Menghasilkan statistik dasar event log."""

    if dataframe.empty:
        raise ValueError("Event log tidak memiliki event.")

    # 1. Total event
    total_events = len(dataframe)

    # 2. Frekuensi aktivitas
    activity_frequency = (
        dataframe[ACTIVITY_COLUMN]
        .value_counts()
        .rename_axis("Activity")
        .reset_index(name="Frequency")
    )

    # 3. Rentang waktu event log
    timestamps = dataframe[TIMESTAMP_COLUMN]
    start_date = timestamps.min()
    end_date = timestamps.max()

    # 4. Durasi setiap case
    case_durations = (
        dataframe.groupby(CASE_COLUMN, sort=False)
        .agg(
            start_time=(TIMESTAMP_COLUMN, "min"),
            end_time=(TIMESTAMP_COLUMN, "max"),
            valid_timestamp_count=(TIMESTAMP_COLUMN, "count"),
            total_events=(TIMESTAMP_COLUMN, "size"),
        )
        .reset_index()
    )

    # 5. Validasi kelengkapan timestamp setiap case
    incomplete = (
        case_durations["valid_timestamp_count"]
        != case_durations["total_events"]
    )

    case_durations["duration"] = (
        case_durations["end_time"] - case_durations["start_time"]
    )

    case_durations.loc[incomplete, "duration"] = pd.NaT

    case_durations["duration_days"] = (
        case_durations["duration"].dt.total_seconds() / 86400
    )

    case_durations["status"] = (
        case_durations["duration_days"]
        .notna()
        .map({
            True: "Valid",
            False: "Timestamp tidak lengkap",
        })
    )

    # 6. Rata-rata cycle time
    valid_durations = case_durations["duration_days"].dropna()

    average_cycle_time = (
        float(valid_durations.mean())
        if not valid_durations.empty
        else None
    )

    # 7. Ringkasan hasil
    total_cases = len(case_durations)

    return {
        "total_cases": int(total_cases),
        "total_events": int(total_events),
        "activity_frequency": activity_frequency,
        "start_date": start_date,
        "end_date": end_date,
        "average_cycle_time_days": average_cycle_time,
        "case_durations": case_durations,
        "valid_duration_cases": int(valid_durations.count()),
        "invalid_duration_cases": int(
            case_durations["duration_days"].isna().sum()
        ),
    }
