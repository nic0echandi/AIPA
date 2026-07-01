#!/usr/bin/env python3
"""
QUICK START para SuperAgent
Ejecuta este script para verificar que todo está listo
"""

import subprocess
import sys
from pathlib import Path

def run_command(cmd, description):
    print(f"\n{'='*60}")
    print(f"[*] {description}")
    print(f"{'='*60}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    print("""
╔════════════════════════════════════════════════════════╗
║   SuperAgent - Quick Start                          ║
║   Verificación y prueba de funcionamiento             ║
╚════════════════════════════════════════════════════════╝
    """)
    
    steps = [
        ("python check_config.py", "Verificar configuración"),
        ("python test_examples.py", "Crear archivos de prueba"),
        ("python superagent.py", "Ejecutar agente (Ctrl+C para detener)"),
    ]
    
    for cmd, desc in steps:
        if not run_command(cmd, desc):
            print(f"\n✗ Error en: {desc}")
            sys.exit(1)
    
    print("""
    
✓ SuperAgent está listo para funcionar
✓ Los logs se guardan en: logs/superagent.log
✓ Los emails procesados se mueven a: processed/<categoria>/

Próximos pasos:
1. Configurar Power Automate para descargar archivos a ingress/
2. Instalar como servicio: nssm install SuperAgent python superagent.py
3. Monitorear logs: tail -f logs/superagent.log

Documentación:
- README.md - Descripción general
- SETUP.md - Instalación completa
- ESTRUCTURA.md - Estructura del proyecto
- POWER_AUTOMATE.md - Integración con Power Automate
    """)

if __name__ == "__main__":
    main()
