
from pathlib import Path

from modules.importer import import_xes
from modules.overview import generate_overview


def main():
    xes_files = list(Path("data").glob("*.xes"))

    if len(xes_files) != 1:
        print("Pastikan hanya ada satu file .xes di folder data.")
        return

    try:
        # F01: Import dataset
        result = import_xes(xes_files[0])

        print("\n=== F01: IMPORT BERHASIL ===")
        print("File:", result["file_name"])
        print("Total case:", result["total_cases"])
        print("Total event:", result["total_events"])

        print("\nAtribut tersedia:")
        for column in result["available_columns"]:
            print("-", column)

        print("\nAtribut opsional:")
        print(result["available_optional"])

        print(
            "\nTimestamp tidak valid:",
            result["invalid_timestamp_events"],
        )

        # F02: Overview
        overview = generate_overview(result["dataframe"])

        print("\n=== F02: OVERVIEW ===")
        print("Total case:", overview["total_cases"])
        print("Total event:", overview["total_events"])
        print("Mulai:", overview["start_date"])
        print("Selesai:", overview["end_date"])
        print(
            "Rata-rata cycle time:",
            overview["average_cycle_time_days"],
            "hari",
        )

        print("\nFrekuensi aktivitas:")
        print(
            overview["activity_frequency"]
            .head(10)
            .to_string(index=False)
        )

        print("\nDurasi case:")
        print(
            overview["case_durations"]
            .head(10)
            .to_string(index=False)
        )

        print("\nF01 dan F02 berhasil diuji.")

    except Exception as error:
        print("\nTerjadi kesalahan:")
        print(type(error).__name__, error)


if __name__ == "__main__":
    main()
