#!/usr/bin/env python3
"""Genera un CSV de reportantes para un dominio y un rango de fechas."""

import argparse
import csv
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Counter as CounterType, Iterable, List, Optional, Tuple


DEFAULT_DOMAIN = "movistarbeneficios.support-email.info"
TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T")
EMAIL_RE = re.compile(r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+", re.IGNORECASE)


def parse_date(value: str) -> date:
    """Parsea fechas en formato ISO YYYY-MM-DD."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise argparse.ArgumentTypeError(
            f"Fecha inválida: {value!r}. Usa el formato YYYY-MM-DD."
        )
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Fecha inválida: {value!r}. Usa el formato YYYY-MM-DD."
        ) from exc


def normalize_domain(value: str) -> str:
    domain = value.strip().lower().rstrip(".")
    if not domain or "@" in domain or any(char.isspace() for char in domain):
        raise ValueError(f"Dominio inválido: {value!r}")
    return domain


def find_log_files(log_dir: Path) -> List[Path]:
    """Devuelve el log actual y sus respaldos numéricos de rotación."""
    current_log = log_dir / "superagent.log"
    rotated_logs = sorted(
        (path for path in log_dir.glob("superagent.log.*") if path.suffix[1:].isdigit()),
        key=lambda path: int(path.suffix[1:]),
    )
    log_files = [path for path in [current_log, *rotated_logs] if path.is_file()]
    if not log_files:
        raise FileNotFoundError(f"No se encontraron logs de SuperAgent en {log_dir}")
    return log_files


def collect_reporters(
    log_files: Iterable[Path],
    start_date: date,
    end_date: date,
    domain: str = DEFAULT_DOMAIN,
) -> CounterType[Tuple[str, date]]:
    """Cuenta reportes cuyo remitente pertenece al dominio indicado."""
    if start_date > end_date:
        raise ValueError("La fecha de inicio no puede ser posterior a la fecha de fin.")

    target_domain = normalize_domain(domain)
    reporters: CounterType[Tuple[str, date]] = Counter()

    for log_file in log_files:
        current_date: Optional[date] = None
        sender_domain: Optional[str] = None
        reporter_email: Optional[str] = None

        def record_current_email() -> None:
            if (
                current_date is not None
                and start_date <= current_date <= end_date
                and sender_domain == target_domain
                and reporter_email is not None
            ):
                reporters[(reporter_email, current_date)] += 1

        with log_file.open(encoding="cp1252") as log:
            for line in log:
                timestamp_match = TIMESTAMP_RE.match(line)
                if "Procesando:" in line and timestamp_match:
                    record_current_email()
                    current_date = date.fromisoformat(timestamp_match.group(1))
                    sender_domain = None
                    reporter_email = None
                elif current_date is not None and "[EXTRACT From]" in line:
                    email_match = EMAIL_RE.search(line.split("[EXTRACT From]", 1)[1])
                    sender_domain = (
                        email_match.group(0).rsplit("@", 1)[1].lower().rstrip(".")
                        if email_match
                        else None
                    )
                elif current_date is not None and "Para (reporter):" in line:
                    email_match = EMAIL_RE.search(line.split("Para (reporter):", 1)[1])
                    reporter_email = email_match.group(0).lower() if email_match else None

        record_current_email()

    return reporters


def write_report(
    reporters: CounterType[Tuple[str, date]], output_path: Path
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(["email", "reportes", "fecha_reporte"])
        writer.writerows(
            (email, reporters[(email, report_date)], report_date.isoformat())
            for email, report_date in sorted(reporters)
        )


def prompt_date(label: str) -> date:
    while True:
        try:
            return parse_date(input(f"Fecha {label} (YYYY-MM-DD): ").strip())
        except argparse.ArgumentTypeError as exc:
            print(exc)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera un CSV con reportantes de una campaña en un rango de fechas."
    )
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="Dominio remitente de la campaña.")
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "logs",
        help="Directorio de logs (default: SuperAgent/logs).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directorio donde guardar el CSV (default: SuperAgent).",
    )
    args = parser.parse_args()

    start_date = prompt_date("de inicio")
    end_date = prompt_date("de fin")
    if start_date > end_date:
        parser.error("La fecha de inicio no puede ser posterior a la fecha de fin.")

    try:
        domain = normalize_domain(args.domain)
        log_files = find_log_files(args.log_dir)
        reporters = collect_reporters(log_files, start_date, end_date, domain)
        output_path = args.output_dir / (
            f"reportantes_{domain}_{start_date.isoformat()}_{end_date.isoformat()}.csv"
        )
        write_report(reporters, output_path)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    print(f"CSV generado: {output_path}")
    print(f"Reportantes únicos: {len({email for email, _ in reporters})}")
    print(f"Reportes encontrados: {sum(reporters.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
