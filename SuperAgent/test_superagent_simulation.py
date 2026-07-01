#!/usr/bin/env python3
"""
Simular el procesamiento de SuperAgent con los archivos reales
"""
import os
import sys
from pathlib import Path
from datetime import datetime

# Agregar carpeta agent/ al path (igual que SuperAgent)
agent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agent'))
sys.path.insert(0, agent_dir)

from knn_classifier import KNNClassifier, extract_features, features_to_vector, FEATURE_NAMES
from phishingAnalizer import PhishingAnalyzerTXT
from usage_stats import UsageStats

# Configurar logging igual que SuperAgent
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
log = logging.getLogger('test_superagent')

# Rutas
revisar_dir = Path(__file__).resolve().parent.parent / "revisar"
config_path = Path(__file__).resolve().parent / "config.json"

print("=" * 80)
print("SIMULACIÓN DE PROCESAMIENTO SUPERAGENT_2")
print("=" * 80)
print(f"Directorio revisar: {revisar_dir}")
print(f"Config: {config_path}\n")

# Instanciar analyzer (igual que SuperAgent)
log.info("Inicializando PhishingAnalyzerTXT...")
analyzer = PhishingAnalyzerTXT(str(config_path))

# Procesar archivos
txt_files = sorted(revisar_dir.glob("*.txt"))
print(f"Encontrados {len(txt_files)} archivos\n")

for i, txt_file in enumerate(txt_files, 1):
    print(f"\n{'='*80}")
    print(f"[{i}] {txt_file.name}")
    print(f"{'='*80}")
    
    # Paso 1: Parsear archivo (parse_txt_file)
    log.info(f"Parseando archivo: {txt_file.name}")
    parsed = analyzer.parse_txt_file(str(txt_file))
    
    if parsed is None:
        log.error("parse_txt_file retornó None")
        continue
    
    headers = parsed.get("headers", {})
    log.info(f"✓ Headers extraídos: {len(headers)}")
    
    if not headers:
        log.error("❌ NO se extrajeron headers")
        continue
    
    # Mostrar headers importantes
    print(f"  ✓ Headers extraídos: {len(headers)}")
    
    for header in ["From", "To", "Subject", "Date"]:
        if header in headers:
            value = headers[header]
            if len(value) > 80:
                value = value[:80] + "..."
            print(f"    • {header}: {value}")
    
    # Paso 2: Extraer email del header From:
    from_email = headers.get("From", "")
    log.info(f"From header: {from_email}")
    
    # Paso 3: Analizar archivo
    log.info(f"Analizando archivo con analyze_txt_file...")
    analysis = analyzer.analyze_txt_file(str(txt_file))
    
    if analysis:
        log.info(f"  Classification: {analysis.classification}")
        log.info(f"  Confidence: {analysis.confidence:.2%}")
        log.info(f"  URLs found: {len(analysis.urls)}")
    else:
        log.error("analyze_txt_file retornó None")

print("\n" + "=" * 80)
print("RESUMEN")
print("=" * 80)
print("✓ Simulación completada.")
print("✓ Si todos los archivos muestran headers, el parser está funcionando")
print("✓ SuperAgent debería procesar correctamente los archivos ahora.")
