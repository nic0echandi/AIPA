#!/usr/bin/env python3
"""
view_stats.py — Herramienta para ver estadísticas de uso desde línea de comandos

Uso:
    python view_stats.py                    # Resumen del mes actual
    python view_stats.py --month 2025-01   # Resumen de mes específico
    python view_stats.py --year 2025        # Resumen anual
    python view_stats.py --report           # Reporte completo
"""

import sys
import argparse
from pathlib import Path

# Debug: escribir en archivo desde el inicio
debug_file = Path(__file__).resolve().parent / "debug_view_stats.log"
with open(debug_file, "w") as df:
    df.write(f"[INIT] view_stats.py iniciado\n")
    df.write(f"[INIT] __file__ = {__file__}\n")
    df.write(f"[INIT] Path(__file__).parent = {Path(__file__).parent}\n")
    df.flush()

# Agregar SuperAgent_2 al path
sys.path.insert(0, str(Path(__file__).parent))

with open(debug_file, "a") as df:
    df.write(f"[INIT] sys.path actualizado\n")
    df.flush()

try:
    from usage_stats import UsageStats
    with open(debug_file, "a") as df:
        df.write(f"[INIT] UsageStats importado correctamente\n")
        df.flush()
except ImportError as e:
    with open(debug_file, "a") as df:
        df.write(f"[ERROR] No se pudo importar UsageStats: {e}\n")
        df.flush()
    sys.exit(1)

from datetime import datetime


def print_month_summary(stats_obj, year, month):
    """Imprime resumen de mes específico."""
    summary = stats_obj.get_month_summary(year, month)
    
    print(f"📅 Estadísticas del {summary['month']:02d}/{summary['year']}")
    print("=" * 60)
    print()
    
    print(f"Total de casos procesados: {summary['total']}")
    print()
    
    if summary['total'] == 0:
        print("   (Sin datos para este mes)")
        return
    
    print("Clasificación de emails:")
    for cls in ["legitimo", "spam", "sospechoso"]:
        count = summary['by_classification'].get(cls, 0)
        pct = summary['by_classification_pct'].get(cls, 0)
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"  {cls:12} {count:4} ({pct:5.1f}%) {bar}")
    
    print()
    print("Decisiones por:")
    for src in ["whitelist", "knn", "llm"]:
        count = summary['by_source'].get(src, 0)
        pct = summary['by_source_pct'].get(src, 0)
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"  {src:12} {count:4} ({pct:5.1f}%) {bar}")
    
    print()
    print("Rendimiento del KNN:")
    knn_data = summary['knn_accuracy']
    correct = knn_data['correct']
    incorrect = knn_data['incorrect']
    total_knn = correct + incorrect
    
    if total_knn > 0:
        accuracy = correct / total_knn * 100
        print(f"  Aciertos: {correct} / {total_knn} ({accuracy:.1f}%)")
        print(f"  Errores:  {incorrect} / {total_knn} ({100-accuracy:.1f}%)")
    else:
        print("  (Sin casos de KNN)")
    
    print()


def print_year_summary(stats_obj, year):
    """Imprime resumen anual."""
    summary = stats_obj.get_year_summary(year)
    
    print(f"📊 Estadísticas del año {year}")
    print("=" * 60)
    print()
    
    print(f"Total de casos procesados: {summary['total']}")
    print()
    
    if summary['total'] == 0:
        print("   (Sin datos para este año)")
        return
    
    print("Resumen por clasificación:")
    for cls in ["legitimo", "spam", "sospechoso"]:
        count = summary['by_classification'].get(cls, 0)
        pct = summary['by_classification_pct'].get(cls, 0)
        print(f"  {cls:12} {count:6} ({pct:5.1f}%)")
    
    print()
    print("Resumen por decisión:")
    for src in ["whitelist", "knn", "llm"]:
        count = summary['by_source'].get(src, 0)
        pct = summary['by_source_pct'].get(src, 0)
        print(f"  {src:12} {count:6} ({pct:5.1f}%)")
    
    print()
    print("Histórico mensual:")
    for month in range(1, 13):
        if month in summary.get('by_month', {}):
            count = summary['by_month'][month]
            print(f"  Mes {month:02d}: {count:4} casos")
    
    print()


def main():
    debug_file = Path(__file__).resolve().parent / "debug_view_stats.log"
    
    with open(debug_file, "a") as df:
        df.write(f"[MAIN] main() iniciado\n")
        df.flush()
    
    parser = argparse.ArgumentParser(
        description="Visualizador de estadísticas de SuperAgent_2"
    )
    parser.add_argument(
        "--month",
        help="Mes específico (formato: YYYY-MM, ej: 2025-01)",
        default=None
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Año completo",
        default=None
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generar reporte completo"
    )
    
    args = parser.parse_args()
    
    with open(debug_file, "a") as df:
        df.write(f"[MAIN] Creando objeto UsageStats...\n")
        df.flush()
    
    try:
        stats = UsageStats()
        with open(debug_file, "a") as df:
            df.write(f"[MAIN] UsageStats creado exitosamente\n")
            df.write(f"[MAIN] stats.stats contiene: {stats.stats}\n")
            df.flush()
    except Exception as e:
        with open(debug_file, "a") as df:
            df.write(f"[MAIN] ERROR: No se pudo crear UsageStats: {e}\n")
            import traceback
            df.write(traceback.format_exc())
            df.flush()
        sys.exit(1)
    
    now = datetime.now()
    
    if args.report:
        # Generar y mostrar reporte completo
        report = stats.generate_report()
        print(report)
    elif args.month:
        # Mes específico
        try:
            year, month = map(int, args.month.split("-"))
            print_month_summary(stats, year, month)
        except (ValueError, IndexError):
            print(f"❌ Formato de mes inválido: {args.month}")
            print("   Use: YYYY-MM (ej: 2025-01)")
            sys.exit(1)
    elif args.year:
        # Año completo
        print_year_summary(stats, args.year)
    else:
        # Mes actual por defecto
        with open(debug_file, "a") as df:
            df.write(f"[MAIN] Mostrando mes actual: {now.year}/{now.month}\n")
            df.flush()
        print_month_summary(stats, now.year, now.month)


if __name__ == "__main__":
    debug_file = Path(__file__).resolve().parent / "debug_view_stats.log"
    try:
        with open(debug_file, "a") as df:
            df.write(f"[ENTRY] Punto de entrada main\n")
            df.flush()
        main()
        with open(debug_file, "a") as df:
            df.write(f"[ENTRY] main() completó exitosamente\n")
            df.flush()
    except Exception as e:
        with open(debug_file, "a") as df:
            df.write(f"[ENTRY] ERROR FATAL: {e}\n")
            import traceback
            df.write(traceback.format_exc())
            df.flush()
        print(f"ERROR: {e}")
        sys.exit(1)
