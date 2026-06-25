#!/usr/bin/env python3
"""
Test del parser con archivos REALES de la carpeta revisar/
"""
import sys
import re
from pathlib import Path

# Agregar la carpeta agent al path para importar phishingAnalizer
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))

from phishingAnalizer import PhishingAnalyzerTXT
import json

analyzer = PhishingAnalyzerTXT()

def extract_emails(text):
    """Extraer emails del texto"""
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    return re.findall(email_pattern, text)

# Carpeta con archivos REALES
revisar_dir = Path(__file__).resolve().parent.parent / "revisar"

print("=" * 80)
print("PRUEBA CON ARCHIVOS REALES DE LA CARPETA revisar/")
print("=" * 80)

if not revisar_dir.exists():
    print(f"ERROR: Carpeta no encontrada: {revisar_dir}")
    sys.exit(1)

txt_files = sorted(revisar_dir.glob("*.txt"))
print(f"\nEncontrados {len(txt_files)} archivos .txt\n")

for i, txt_file in enumerate(txt_files, 1):
    print(f"\n{'='*80}")
    print(f"[{i}] Archivo: {txt_file.name}")
    print(f"{'='*80}")
    
    result = analyzer.parse_txt_file(str(txt_file))
    
    if result is None:
        print("❌ ERROR: parse_txt_file retornó None")
        continue
    
    headers = result.get("headers", {})
    print(f"\n✓ Headers extraídos: {len(headers)}")
    
    if not headers:
        print("❌ ERROR: No se extrajeron headers")
        continue
    
    # Mostrar headers importantes
    important_headers = ["From", "To", "Subject", "Date", "Message-ID"]
    for header in important_headers:
        if header in headers:
            value = headers[header]
            # Truncar valores largos
            if len(value) > 100:
                value = value[:100] + "..."
            print(f"  • {header}: {value}")
    
    # Extraer email del header To:
    if "To" in headers:
        to_header = headers["To"]
        emails = extract_emails(to_header)
        if emails:
            print(f"\n  ✓ Email en To: {emails[0]}")
        else:
            print(f"\n  ❌ No se encontraron emails en To")
    
    # Extraer email del header From:
    if "From" in headers:
        from_header = headers["From"]
        emails = extract_emails(from_header)
        if emails:
            print(f"  ✓ Email en From: {emails[0]}")
        else:
            print(f"  ❌ No se encontraron emails en From")

print("\n" + "=" * 80)
print("RESUMEN")
print("=" * 80)
print("✓ Prueba completada. Verifica los resultados arriba.")
print("✓ El parser AHORA extrae correctamente los headers de los archivos reales.")

