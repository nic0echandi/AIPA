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

# Agregar SuperAgent al path
sys.path.insert(0, str(Path(__file__).parent))

from usage_stats import UsageStats
from datetime import datetime


def print_month_summary(stats_obj, year, month):
    """Imprime resumen de mes específico."""
    summary = stats_obj.get_month_summary(str(year), f"{month:02d}" if isinstance(month, int) else month)
    
    # Convertir year y month a int si son strings
    year_int = int(summary['year']) if isinstance(summary['year'], str) else summary['year']
    month_int = int(summary['month']) if isinstance(summary['month'], str) else summary['month']
    
    print(f"\n📅 Estadísticas del {month_int:02d}/{year_int}")
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
    summary = stats_obj.get_year_summary(str(year))
    
    print(f"\n📊 Estadísticas del año {summary['year']}")
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


def get_latest_month_with_data(stats_obj) -> tuple:
    """Encuentra el mes más reciente que tiene datos."""
    # Recorrer desde mes actual hacia atrás
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    
    # Buscar en los últimos 12 meses
    for months_back in range(0, 13):
        year = current_year
        month = current_month - months_back
        
        if month <= 0:
            year -= 1
            month += 12
        
        year_str = str(year)
        month_str = f"{month:02d}"
        
        if year_str in stats_obj.stats and month_str in stats_obj.stats[year_str]:
            if stats_obj.stats[year_str][month_str].get("total", 0) > 0:
                return (year, month)
    
    # Si no hay datos, retornar mes actual
    return (current_year, current_month)

def main():
    parser = argparse.ArgumentParser(
        description="Visualizador de estadísticas de SuperAgent"
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
    
    stats = UsageStats()
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
        # Mostrar mes actual si tiene datos, sino el mes más reciente
        summary = stats.get_month_summary(str(now.year), f"{now.month:02d}")
        
        if summary['total'] == 0:
            # No hay datos del mes actual, buscar mes más reciente
            latest_year, latest_month = get_latest_month_with_data(stats)
            if (latest_year, latest_month) != (now.year, now.month):
                print(f"ℹ️  No hay datos para {now.month:02d}/{now.year}. Mostrando mes más reciente con datos:\n")
            print_month_summary(stats, latest_year, latest_month)
        else:
            print_month_summary(stats, now.year, now.month)


if __name__ == "__main__":
    main()
