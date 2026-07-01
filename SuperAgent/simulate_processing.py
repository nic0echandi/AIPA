#!/usr/bin/env python3
"""
Simular el procesamiento que hace SuperAgent
"""

import sys
import os
from pathlib import Path

from phishingAnalizer import PhishingAnalyzerTXT

def extract_email_from_address(address: str) -> str:
    """Función de SuperAgent2"""
    import html
    if not address:
        return ""
    
    # Decodificar entidades HTML
    address = html.unescape(address)
    
    # Caso 1: Formato "Name <email@example.com>"
    if '<' in address and '>' in address:
        return address[address.find('<')+1:address.find('>')].strip()
    
    # Caso 2: Dirección simple
    parts = address.split()
    if parts:
        for part in reversed(parts):
            if '@' in part:
                return part.strip()
    
    return address.strip()

print("=" * 80)
print("SIMULANDO PROCESAMIENTO DE SuperAgent")
print("=" * 80)

test_file = Path("ingress/test_debug_20260625.txt")

if not test_file.exists():
    print(f"✗ Archivo no encontrado: {test_file}")
    sys.exit(1)

print(f"\n📄 Procesando: {test_file.name}")

analyzer = PhishingAnalyzerTXT("config.json")
parsed = analyzer.parse_txt_file(str(test_file))

if not parsed:
    print("✗ No se pudo parsear")
    sys.exit(1)

headers = parsed["headers"]

print(f"\n✓ Headers extraídos: {len(headers)} cabeceras")
print("\nCabeceras principales:")
for key in ['From', 'To', 'Subject', 'Message-ID']:
    value = headers.get(key, "(no encontrado)")
    print(f"  {key}: {value[:80] if len(value) > 80 else value}")

print("\n▶ Procesamiento de email:")
to_raw = headers.get("To", "")
print(f"  to_raw = headers.get('To', '')")
print(f"  → '{to_raw}'")

to_email = extract_email_from_address(to_raw)
print(f"\n  to_email = extract_email_from_address(to_raw)")
print(f"  → '{to_email}'")

if not to_email:
    print("\n✗ Email del reporter VACÍO - esto es lo que vemos en los logs")
else:
    print(f"\n✓ Email extraído correctamente: {to_email}")

print("\n" + "=" * 80)
