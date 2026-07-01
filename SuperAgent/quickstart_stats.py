#!/usr/bin/env python3
"""
quickstart_stats.py — Guía rápida para comenzar con estadísticas

Ejecuta esto después de instalar SuperAgent para verificar que todo funciona.
"""

import sys
from pathlib import Path

# Agregar SuperAgent al path
sys.path.insert(0, str(Path(__file__).parent))

from usage_stats import UsageStats
from datetime import datetime


def print_section(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}\n")


def main():
    print_section("QUICKSTART: Sistema de Estadísticas")
    
    # 1. Verificar que funciona
    print("✓ Iniciando UsageStats...")
    stats = UsageStats()
    print("✓ OK - stats.json cargado\n")
    
    # 2. Mostrar estado actual
    current_month = datetime.now()
    print(f"Mes actual: {current_month.strftime('%B %Y')}\n")
    
    summary = stats.get_month_summary()
    print(f"Emails procesados este mes: {summary['total']}")
    
    if summary['total'] > 0:
        print(f"  • Legítimos: {summary['by_classification'].get('legitimo', 0)}")
        print(f"  • Spam: {summary['by_classification'].get('spam', 0)}")
        print(f"  • Sospechosos: {summary['by_classification'].get('sospechoso', 0)}")
        print(f"\nDecisiones por:")
        print(f"  • Whitelist: {summary['by_source'].get('whitelist', 0)}")
        print(f"  • KNN: {summary['by_source'].get('knn', 0)}")
        print(f"  • LLM: {summary['by_source'].get('llm', 0)}")
        print(f"\nPrecisión del KNN: {summary['knn_accuracy_pct']:.1f}%")
    else:
        print("  (Sin datos aún - comienza a procesar emails con superagent.py)")
    
    # 3. Instrucciones
    print_section("Próximos pasos")
    
    print("1️⃣  Ejecutar SuperAgent en background:")
    print("   cd SuperAgent")
    print("   nohup python superagent.py > logs/agent.log 2>&1 &")
    
    print("\n2️⃣  Ver estadísticas en tiempo real:")
    print("   python view_stats.py              # Mes actual")
    print("   python view_stats.py --report     # Reporte formateado")
    
    print("\n3️⃣  Monitorear precisión del KNN:")
    print("   watch -n 300 'python view_stats.py'  # Actualiza cada 5 min")
    
    print("\n4️⃣  Interpretar resultados:")
    print("   • KNN accuracy > 90% = modelo maduro ✓")
    print("   • KNN usage > 50% = poco uso de LLM ✓")
    print("   • LLM usage < 30% = eficiente ✓")
    
    # 4. Documentación
    print_section("Documentación")
    
    print("📖 Archivos importantes:")
    print("   • README.md          - Descripción general")
    print("   • STATS.md           - Documentación técnica")
    print("   • view_stats.py      - Herramienta CLI")
    print("   • ejemplo_stats.py   - Script de demostración")
    print("   • stats.json         - Datos (se crea automáticamente)")
    
    # 5. Problemas comunes
    print_section("Troubleshooting")
    
    print("❓ ¿No veo datos?")
    print("   → Asegúrate de que SuperAgent está ejecutándose")
    print("   → Coloca archivos .txt en ingress/")
    print("   → Verifica logs/superagent.log")
    
    print("\n❓ ¿KNN accuracy muy baja?")
    print("   → Normal en primeras 50 ejemplos")
    print("   → Aumenta a medida que procesa más emails")
    print("   → Verifica que features de headers sean claros (SPF, DKIM, etc.)")
    
    print("\n❓ ¿LLM usage muy alto?")
    print("   → Normal si pocos ejemplos")
    print("   → Espera a 200+ ejemplos para ver mejora")
    print("   → Revisa knn_stats.json para ver umbral dinámico")
    
    print_section("¡Listo!")
    
    print("Sistema de estadísticas funcionando correctamente.\n")
    print("Para más información:")
    print("  • Lee STATS.md para entender los datos")
    print("  • Ejecuta view_stats.py regularmente")
    print("  • Reporta problemas con detalles de logs/\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nVerifica que estés en el directorio SuperAgent/")
        sys.exit(1)
