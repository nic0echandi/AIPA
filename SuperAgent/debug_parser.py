#!/usr/bin/env python3
"""
Script de debug para diagnosticar por qué los headers no se están extrayendo
"""

import sys
import os
from pathlib import Path

# Agregar carpeta agent/ al path
agent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agent'))
sys.path.insert(0, agent_dir)

from phishingAnalizer import PhishingAnalyzerTXT

def debug_parse_file(file_path):
    """Analiza un archivo y muestra toda la información extraída."""
    print("\n" + "=" * 80)
    print(f"ANALIZANDO: {file_path}")
    print("=" * 80)
    
    analyzer = PhishingAnalyzerTXT("config.json")
    parsed = analyzer.parse_txt_file(str(file_path))
    
    if not parsed:
        print("✗ Error: No se pudo parsear el archivo")
        return False
    
    headers = parsed.get("headers", {})
    content = parsed.get("raw_content", "")[:500]
    
    print(f"\n📊 HEADERS EXTRAIDOS ({len(headers)} headers):")
    print("─" * 80)
    
    if not headers:
        print("⚠ ¡NO SE ENCONTRARON HEADERS!")
    else:
        for key, value in headers.items():
            # Truncar valores muy largos
            display_value = value[:100] + "..." if len(value) > 100 else value
            print(f"  {key}: {display_value}")
    
    print(f"\n📧 HEADERS CRÍTICOS:")
    print("─" * 80)
    print(f"  From:     {headers.get('From', '(no encontrado)')}")
    print(f"  To:       {headers.get('To', '(no encontrado)')}")
    print(f"  Subject:  {headers.get('Subject', '(no encontrado)')}")
    print(f"  Message-ID: {headers.get('Message-ID', '(no encontrado)')}")
    
    print(f"\n📄 CONTENIDO (primeros 500 chars):")
    print("─" * 80)
    print(content[:500])
    
    # Buscar patrones de headers en el contenido crudo
    print(f"\n🔍 BÚSQUEDA DE PATRONES:")
    print("─" * 80)
    
    content_sample = parsed["raw_content"][:2000]
    
    # Buscar líneas con "Header:"
    import re
    header_pattern = re.findall(r'^[A-Za-z-]+:\s*.+$', content_sample, re.MULTILINE)
    print(f"  Líneas tipo 'Header:' encontradas: {len(header_pattern)}")
    if header_pattern:
        print("  Ejemplos:")
        for line in header_pattern[:5]:
            print(f"    - {line[:80]}")
    
    # Buscar etiquetas HTML
    if "<br>" in content_sample:
        print("  ✓ Encontradas etiquetas <br>")
    if "&lt;" in content_sample or "&gt;" in content_sample:
        print("  ✓ Encontradas entidades HTML (&lt; &gt;)")
    if "Received:" in content_sample:
        print("  ✓ Encontrado header 'Received:'")
    
    return bool(headers)

if __name__ == "__main__":
    # Probar con archivo de muestra
    test_file = Path("test_sample.txt")
    
    if not test_file.exists():
        print("✗ No se encontró test_sample.txt")
        sys.exit(1)
    
    print(f"\n📦 Analizando archivo de prueba...")
    
    result = debug_parse_file(test_file)
    all_ok = result
    
    print("\n" + "=" * 80)
    if all_ok:
        print("✓ Todos los archivos se parsearon correctamente")
    else:
        print("✗ Algunos archivos no pudieron parsearse correctamente")
    print("=" * 80)
