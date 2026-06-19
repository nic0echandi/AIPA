#!/usr/bin/env python3
"""
ejemplo_stats.py — Ejemplo de cómo usar el sistema de estadísticas de SuperAgent_2

Demuestra:
- Cómo se registran casos
- Cómo se generan reportes
- Estructura de datos
"""

import sys
import os
from pathlib import Path

# Agregar SuperAgent_2 al path
sys.path.insert(0, str(Path(__file__).parent))

from usage_stats import UsageStats


def main():
    print("=" * 70)
    print("DEMO: Sistema de Estadísticas de SuperAgent_2")
    print("=" * 70)
    print()
    
    # Crear instancia
    stats = UsageStats()
    
    print("📊 Registrando casos de ejemplo...")
    print()
    
    # Simular algunos casos
    casos = [
        ("legitimo", "whitelist"),
        ("legitimo", "whitelist"),
        ("legitimo", "whitelist"),
        ("spam", "knn", True),
        ("spam", "knn", True),
        ("spam", "knn", False),  # KNN se equivocó
        ("spam", "llm"),
        ("sospechoso", "knn", True),
        ("sospechoso", "knn", False),  # KNN se equivocó
        ("sospechoso", "llm"),
        ("sospechoso", "llm"),
    ]
    
    for i, caso in enumerate(casos, 1):
        if len(caso) == 2:
            classification, source = caso
            stats.record_case(classification, source)
            print(f"  {i:2}. {classification:12} → {source}")
        else:
            classification, source, knn_correct = caso
            stats.record_case(classification, source, knn_correct)
            result = "✓" if knn_correct else "✗"
            print(f"  {i:2}. {classification:12} → {source} [{result}]")
    
    print()
    print("=" * 70)
    print("RESUMEN DE ESTADÍSTICAS")
    print("=" * 70)
    print()
    
    # Mostrar resumen mensual
    month_summary = stats.get_month_summary()
    print(f"📅 Mes: {month_summary['month']}/{month_summary['year']}")
    print(f"   Total casos: {month_summary['total']}")
    print()
    print("   Clasificación:")
    for cls, count in month_summary["by_classification"].items():
        pct = month_summary["by_classification_pct"][cls]
        print(f"     • {cls:12} {count:3} ({pct:5.1f}%)")
    print()
    print("   Decisiones por:")
    for src, count in month_summary["by_source"].items():
        pct = month_summary["by_source_pct"][src]
        print(f"     • {src:12} {count:3} ({pct:5.1f}%)")
    print()
    
    # Precisión del KNN
    knn_data = month_summary["knn_accuracy"]
    print("   🎯 Precisión del KNN:")
    print(f"     • Correctas: {knn_data['correct']}")
    print(f"     • Incorrectas: {knn_data['incorrect']}")
    print(f"     • Tasa de acierto: {month_summary['knn_accuracy_pct']:.1f}%")
    print()
    
    # Generar reporte textual
    print("=" * 70)
    print("REPORTE COMPLETO")
    print("=" * 70)
    print()
    
    report = stats.generate_report("ejemplo_stats_report.txt")
    print(report)
    
    print()
    print("✅ Reporte guardado en: ejemplo_stats_report.txt")
    print()
    print("📁 Archivo de datos JSON: stats.json")
    print("   (contiene el histórico completo de estadísticas)")
    

if __name__ == "__main__":
    main()
