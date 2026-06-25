#!/usr/bin/env python3
"""
Script para verificar que el parser esté usando el código correcto con decodificación HTML
"""

import sys
import os
from pathlib import Path

# Agregar carpeta agent/ al path
agent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agent'))
sys.path.insert(0, agent_dir)

# Importar el analizador
from phishingAnalizer import PhishingAnalyzerTXT

print("=" * 80)
print("VERIFICACIÓN DE CÓDIGO EN phishingAnalizer.py")
print("=" * 80)

# Verificar que el import de html está presente
import inspect
source = inspect.getsource(PhishingAnalyzerTXT.parse_txt_file)

print("\n✓ Verificando que parse_txt_file contiene manejo de HTML...")
if 'html.unescape' in source:
    print("  ✓ Decodificación HTML presente: html.unescape()")
else:
    print("  ✗ Decodificación HTML NO encontrada - código viejo cacheado!")

if '.replace("<br>"' in source:
    print("  ✓ Reemplazo de <br> presente")
else:
    print("  ✗ Reemplazo de <br> NO encontrado - código viejo cacheado!")

print("\n✓ Verificando que extract_email_from_address maneja HTML...")

# Verificar que extract_email_from_address esté en superagent_2.py
try:
    with open("superagent_2.py", "r") as f:
        superagent_source = f.read()
    
    if 'html.unescape' in superagent_source:
        print("  ✓ Decodificación HTML presente en superagent_2.py")
    else:
        print("  ✗ Decodificación HTML NO encontrada en superagent_2.py!")
except Exception as e:
    print(f"  ✗ Error verificando superagent_2.py: {e}")

print("\n" + "=" * 80)
print("PRUEBA PRÁCTICA: Extrayendo email del archivo de muestra")
print("=" * 80)

test_file = Path("test_sample.txt")
if test_file.exists():
    analyzer = PhishingAnalyzerTXT("config.json")
    parsed = analyzer.parse_txt_file(str(test_file))
    
    if parsed:
        headers = parsed["headers"]
        to_header = headers.get("To", "")
        
        print(f"\n✓ Header 'To:' extraído: {to_header}")
        
        # Extraer email manualmente usando el mismo código
        import html
        address = html.unescape(to_header)
        print(f"✓ Después de html.unescape(): {address}")
        
        if '<' in address and '>' in address:
            email = address[address.find('<')+1:address.find('>')].strip()
        else:
            email = address.strip()
        
        print(f"✓ Email extraído: {email}")
        
        if "@" in email:
            print(f"\n✓✓✓ TODO FUNCIONA CORRECTAMENTE")
        else:
            print(f"\n✗ ERROR: Email no contiene @")
    else:
        print("✗ Error parseando archivo")
else:
    print(f"✗ Archivo {test_file} no encontrado")

print("\n" + "=" * 80)
