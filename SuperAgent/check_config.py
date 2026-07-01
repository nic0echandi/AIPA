#!/usr/bin/env python3
"""
Script de validación para SuperAgent
Verifica que todas las dependencias y configuración están correctas
"""

import os
import sys
import json
from pathlib import Path

def check_config():
    """Verifica la configuración."""
    config_path = Path(__file__).parent / "config.json"
    
    print("\n[1] Verificando config.json...")
    
    if not config_path.exists():
        print(f"  ✗ config.json no encontrado en {config_path}")
        return False
    
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        print(f"  ✓ config.json cargado correctamente")
    except json.JSONDecodeError as e:
        print(f"  ✗ Error en JSON: {e}")
        return False
    
    # Verificar campos requeridos
    required = ["ingress_dir", "processed_dir", "analysis_dir"]
    for field in required:
        if field not in config or not config[field]:
            print(f"  ✗ Campo requerido faltante: {field}")
            return False
        print(f"  ✓ {field}: {config[field]}")
    
    # Verificar SMTP
    smtp = config.get("smtp", {})
    if not smtp.get("host"):
        print(f"  ✗ SMTP no configurado (smtp.host vacío)")
        return False
    
    if not smtp.get("username") or not smtp.get("password"):
        print(f"  ✗ Credenciales SMTP incompletas")
        return False
    
    print(f"  ✓ SMTP configurado: {smtp.get('host')}:{smtp.get('port')}")
    
    # Verificar IRIS
    iris = config.get("iris_dfir", {})
    if not iris.get("url") or not iris.get("api_key"):
        print(f"  ⚠ IRIS no configurado completamente (funcionará en modo degradado)")
    else:
        print(f"  ✓ IRIS configurado: {iris.get('url')}")
    
    return True


def check_directories():
    """Verifica las carpetas."""
    print("\n[2] Verificando directorios...")
    
    base = Path(__file__).parent.parent
    
    dirs = {
        "ingress": base / "ingress",
        "processed": base / "processed",
        "analysis_results": base / "analysis_results",
    }
    
    for name, path in dirs.items():
        if path.exists():
            print(f"  ✓ {name}: {path}")
        else:
            print(f"  ⚠ {name} no existe (se creará automáticamente): {path}")
    
    return True


def check_dependencies():
    """Verifica las dependencias de Python."""
    print("\n[3] Verificando dependencias...")
    
    required = ["requests"]
    missing = []
    
    for pkg in required:
        try:
            __import__(pkg)
            print(f"  ✓ {pkg}")
        except ImportError:
            print(f"  ✗ {pkg} no instalado")
            missing.append(pkg)
    
    if missing:
        print(f"\n  Para instalar dependencias faltantes:")
        print(f"  pip install {' '.join(missing)}")
        return False
    
    return True


def check_modules():
    """Verifica los módulos de agent/."""
    print("\n[4] Verificando módulos compartidos (agent/)...")
    
    agent_dir = Path(__file__).parent.parent / "agent"
    modules = {
        "phishingAnalizer.py": "PhishingAnalyzerTXT",
        "knn_classifier.py": "KNNClassifier",
    }
    
    for filename, classname in modules.items():
        filepath = agent_dir / filename
        if not filepath.exists():
            print(f"  ✗ {filename} no encontrado en {agent_dir}")
            return False
        print(f"  ✓ {filename} ({classname})")
    
    return True


def main():
    print("=" * 60)
    print("SuperAgent - Verificación de configuración")
    print("=" * 60)
    
    checks = [
        ("Configuración", check_config),
        ("Directorios", check_directories),
        ("Dependencias", check_dependencies),
        ("Módulos", check_modules),
    ]
    
    results = []
    
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"  ✗ Error: {e}")
            results.append((name, False))
    
    # Resumen
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    
    all_ok = True
    for name, result in results:
        status = "✓ OK" if result else "✗ ERROR"
        print(f"{status} - {name}")
        if not result:
            all_ok = False
    
    print("=" * 60)
    
    if all_ok:
        print("\n✓ Configuración correcta. Puedes ejecutar SuperAgent\n")
        print("  python superagent.py")
        return 0
    else:
        print("\n✗ Corrige los errores antes de ejecutar SuperAgent\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
