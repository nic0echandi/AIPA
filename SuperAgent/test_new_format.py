#!/usr/bin/env python3
"""
Script de prueba para validar el parser del nuevo formato de archivos.
"""

import sys
import os
from pathlib import Path

# Agregar carpeta agent/ al path si existe
agent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agent'))
if os.path.exists(agent_dir):
    sys.path.insert(0, agent_dir)

from phishingAnalizer import PhishingAnalyzerTXT

def test_new_format():
    """Prueba el parser con el nuevo formato."""
    print("\n" + "=" * 80)
    print("PRUEBA: Nuevo Formato de Archivos (key-value)")
    print("=" * 80)
    
    analyzer = PhishingAnalyzerTXT("config.json")
    
    # Archivos de prueba en manual_review
    manual_review_dir = Path("manual_review")
    if not manual_review_dir.exists():
        print("✗ No se encontró carpeta manual_review")
        return False
    
    test_files = list(manual_review_dir.glob("*.txt"))[:2]  # Tomar 2 ejemplos
    
    if not test_files:
        print("✗ No hay archivos .txt en manual_review")
        return False
    
    all_ok = True
    
    for file_path in test_files:
        print(f"\n📄 Archivo: {file_path.name}")
        print("─" * 80)
        
        # Parsear archivo
        parsed = analyzer.parse_txt_file(str(file_path))
        
        if not parsed:
            print("✗ Error: No se pudo parsear")
            all_ok = False
            continue
        
        headers = parsed.get("headers", {})
        is_phishing = parsed.get("is_confirmed_phishing", False)
        
        print(f"  Confirmado phishing: {is_phishing}")
        print(f"  Formato detectado: {'new_format' if 'SenderEmailAddress' in str(headers) or 'SenderName' in str(headers) else 'rfc5322'}")
        print(f"  Headers extraidos: {len(headers)}")
        
        # Headers críticos
        print(f"\n  📧 HEADERS CRÍTICOS:")
        print(f"     From (SenderEmailAddress): {headers.get('From', '(no encontrado)')}")
        print(f"     To: {headers.get('To', '(no encontrado)')}")
        print(f"     Subject: {headers.get('Subject', '(no encontrado)')[:60]}")
        print(f"     Message-ID: {headers.get('Message-ID', '(no encontrado)')[:40]}")
        
        # Reporter
        reporter = analyzer.extract_reporter_from_content(parsed.get("raw_content", ""), headers)
        print(f"\n  👤 Reportero detectado: {reporter}")
        
        # Contenido del email
        content_preview = parsed.get("raw_content", "")[:150]
        print(f"\n  📝 Contenido (primeros 150 chars):")
        print(f"     {content_preview}...")
        
        # Validación
        if not headers.get("From") or not headers.get("To") or not headers.get("Subject"):
            print("\n  ⚠️ Advertencia: Headers críticos faltantes")
            all_ok = False
        else:
            print("\n  ✓ Headers críticos presentes")
    
    print("\n" + "=" * 80)
    return all_ok

if __name__ == "__main__":
    success = test_new_format()
    sys.exit(0 if success else 1)
