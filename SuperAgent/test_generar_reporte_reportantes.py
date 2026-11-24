import argparse
import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from generar_reporte_reportantes import (
    collect_reporters,
    find_log_files,
    parse_date,
    write_report,
)


class ReportantesReportTests(unittest.TestCase):
    def test_collect_reporters_filters_domain_and_inclusive_dates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "superagent.log"
            log_file.write_text(
                "\n".join(
                    [
                        "2026-10-22T23:59:59 | INFO | app | Procesando: before.txt",
                        "2026-10-22T23:59:59 | INFO | app | [EXTRACT From] 'user@update-credentials.com'",
                        "2026-10-22T23:59:59 | INFO | app | Para (reporter): before@example.com",
                        "2026-10-23T00:00:00 | INFO | app | Procesando: first.txt",
                        "2026-10-23T00:00:00 | INFO | app | [EXTRACT From] 'sender@UPDATE-CREDENTIALS.COM'",
                        "2026-10-23T00:00:00 | INFO | app | Para (reporter): PERSON@example.com",
                        "2026-10-30T23:59:59 | INFO | app | Procesando: last.txt",
                        "2026-10-30T23:59:59 | INFO | app | [EXTRACT From] 'sender@update-credentials.com'",
                        "2026-10-30T23:59:59 | INFO | app | Para (reporter): person@example.com",
                        "2026-10-31T00:00:00 | INFO | app | Procesando: after.txt",
                        "2026-10-31T00:00:00 | INFO | app | [EXTRACT From] 'user@update-credentials.com'",
                        "2026-10-31T00:00:00 | INFO | app | Para (reporter): after@example.com",
                    ]
                ),
                encoding="cp1252",
            )

            reporters = collect_reporters(
                [log_file],
                date(2026, 10, 23),
                date(2026, 10, 30),
                domain="update-credentials.com",
            )

        self.assertEqual(
            reporters,
            {
                ("person@example.com", date(2026, 10, 23)): 1,
                ("person@example.com", date(2026, 10, 30)): 1,
            },
        )

    def test_collect_reporters_ignores_records_without_reporter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "superagent.log"
            log_file.write_text(
                "2026-10-27T12:00:00 | INFO | app | Procesando: missing.txt\n"
                "2026-10-27T12:00:00 | INFO | app | [EXTRACT From] 'sender@update-credentials.com'\n",
                encoding="cp1252",
            )

            reporters = collect_reporters(
                [log_file],
                date(2026, 10, 27),
                date(2026, 10, 27),
                domain="update-credentials.com",
            )

        self.assertFalse(reporters)

    def test_write_report_uses_existing_csv_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "nested" / "report.csv"
            write_report(
                {
                    ("z@example.com", date(2026, 10, 24)): 1,
                    ("a@example.com", date(2026, 10, 25)): 1,
                    ("a@example.com", date(2026, 10, 23)): 2,
                },
                output_path,
            )

            with output_path.open(encoding="utf-8-sig", newline="") as report:
                rows = list(csv.reader(report))

        self.assertEqual(
            rows,
            [
                ["email", "reportes", "fecha_reporte"],
                ["a@example.com", "2", "2026-10-23"],
                ["a@example.com", "1", "2026-10-25"],
                ["z@example.com", "1", "2026-10-24"],
            ],
        )

    def test_find_log_files_includes_rotated_logs_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            for name in ("superagent.log", "superagent.log.1", "superagent.log.3", "other.log"):
                (log_dir / name).touch()

            log_files = find_log_files(log_dir)

        self.assertEqual(
            [path.name for path in log_files],
            ["superagent.log", "superagent.log.1", "superagent.log.3"],
        )

    def test_parse_date_rejects_non_iso_format(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_date("23/10/2026")


if __name__ == "__main__":
    unittest.main()
