#!/usr/bin/env python3
"""
Prueba simple del parser sin dependencias de sklearn
"""
import os
import sys
from pathlib import Path
from datetime import datetime

# Agregar carpeta agent/ al path (igual que SuperAgent)
agent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agent'))
sys.path.insert(0, agent_dir)

from phishingAnalizer import PhishingAnalyzerTXT

# Configurar logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
log = logging.getLogger('test_simple')

# Rutas
revisar_dir = Path(__file__).resolve().parent.parent / "revisar"
config_path = Path(__file__).resolve().parent / "config.json"

print("=" * 80)
print("PRUEBA SIMPLE: Parser sin dependencias externas")
print("=" * 80)
print(f"Directorio revisar: {revisar_dir}\n")

# Instanciar analyzer
log.info("Inicializando PhishingAnalyzerTXT...")
try:
    analyzer = PhishingAnalyzerTXT(str(config_path))
    log.info("✓ Analyzer inicializado correctamente")
except Exception as e:
    log.error(f"Error inicializando analyzer: {e}")
    sys.exit(1)

# Procesar archivos
txt_files = sorted(revisar_dir.glob("*.txt"))
print(f"Encontrados {len(txt_files)} archivos\n")

total_with_headers = 0
total_without_headers = 0

for i, txt_file in enumerate(txt_files, 1):
    print(f"\n[{i}] {txt_file.name}")
    
    # Parsear archivo
    parsed = analyzer.parse_txt_file(str(txt_file))
    
    if parsed is None:
        log.error("  ❌ parse_txt_file retornó None")
        total_without_headers += 1
        continue
    
    headers = parsed.get("headers", {})
    
    if not headers:
        log.error(f"  ❌ NO se extrajeron headers")
        total_without_headers += 1
        continue
    
    total_with_headers += 1
    print(f"  ✓ Headers extraídos: {len(headers)}")
    
    # Mostrar headers importantes
    for header in ["From", "To", "Subject"]:
        if header in headers:
            value = headers[header]
            if len(value) > 70:
                value = value[:70] + "..."
            print(f"    • {header}: {value}")

print("\n" + "=" * 80)
print("RESUMEN")
print("=" * 80)
print(f"✓ Archivos con headers: {total_with_headers}/{len(txt_files)}")
print(f"✗ Archivos sin headers: {total_without_headers}/{len(txt_files)}")

if total_with_headers == len(txt_files):
    print("\n✓✓✓ ÉXITO: Todos los archivos fueron parseados correctamente")
    print("✓ El parser está funcionando correctamente en SuperAgent")
else:
    print(f"\n✗ ERROR: Solo {total_with_headers} de {len(txt_files)} archivos")
