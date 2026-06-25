#!/usr/bin/env python3
"""
Script de prueba para verificar extracción correcta de emails del header "To:"
"""

import html
import sys
import os
from pathlib import Path

# Agregar carpeta agent/ al path
agent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agent'))
sys.path.insert(0, agent_dir)

from phishingAnalizer import PhishingAnalyzerTXT

def test_email_extraction():
    """Prueba la extracción de emails con diferentes formatos."""
    
    # Crear instancia del analizador
    analyzer = PhishingAnalyzerTXT("config.json")
    
    print("=" * 80)
    print("PRUEBAS DE EXTRACCIÓN DE EMAIL DEL HEADER 'To:'")
    print("=" * 80)
    
    # Casos de prueba
    test_cases = [
        # (entrada, descripción, email_esperado)
        ("Campuzano Eliana &lt;eliana.campuzano@tmoviles.com.ar&gt;", 
         "HTML entities (real case)", 
         "eliana.campuzano@tmoviles.com.ar"),
        
        ("Campuzano Eliana <eliana.campuzano@tmoviles.com.ar>", 
         "Formato estándar con < >", 
         "eliana.campuzano@tmoviles.com.ar"),
        
        ("user@example.com", 
         "Solo email", 
         "user@example.com"),
        
        ("John Doe &lt;john.doe@company.com&gt;", 
         "Otro HTML entities", 
         "john.doe@company.com"),
         
        ("&quot;Usuario Test&quot; &lt;test@domain.com&gt;", 
         "Nombre con quotes HTML + email", 
         "test@domain.com"),
    ]
    
    # Función helper para extraer email (simula lo que hace superagent)
    def extract_email_from_address(address: str) -> str:
        """Extrae email con manejo de entidades HTML."""
        if not address:
            return ""
        
        # Decodificar entidades HTML
        address = html.unescape(address)
        
        # Caso 1: Formato "Name <email@example.com>"
        if '<' in address and '>' in address:
            return address[address.find('<')+1:address.find('>')].strip()
        
        # Caso 2: Dirección simple o solo nombre + email separados
        parts = address.split()
        if parts:
            for part in reversed(parts):
                if '@' in part:
                    return part.strip()
        
        # Caso 3: No es un email válido
        return address.strip()
    
    print("\n📧 Probando extracción de emails:\n")
    
    all_passed = True
    for entrada, descripcion, esperado in test_cases:
        resultado = extract_email_from_address(entrada)
        passed = resultado == esperado
        all_passed = all_passed and passed
        
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status} | {descripcion}")
        print(f"      Entrada:   {entrada}")
        print(f"      Esperado:  {esperado}")
        print(f"      Resultado: {resultado}")
        print()
    
    print("=" * 80)
    if all_passed:
        print("✓ TODAS LAS PRUEBAS PASARON")
    else:
        print("✗ ALGUNAS PRUEBAS FALLARON")
    print("=" * 80)
    
    return all_passed

def test_with_actual_file():
    """Prueba con el archivo real adjunto."""
    print("\n" + "=" * 80)
    print("PRUEBA CON ARCHIVO REAL")
    print("=" * 80)
    
    test_file = Path("..") / "revisar" / "20260625_122219_Phishing_000000002D6A6BF8F58B924FA9CB0BDD9CBC5FC0070000BA94D7C4C0B1459B5F6EF4A7DE2474000002825C8A000000BA94D7C4C0B1459B5F6EF4A7DE24740000DF373E870000.txt"
    
    if not test_file.exists():
        print(f"⚠ Archivo no encontrado: {test_file}")
        return False
    
    try:
        analyzer = PhishingAnalyzerTXT("config.json")
        parsed = analyzer.parse_txt_file(str(test_file))
        
        if not parsed:
            print("✗ No se pudo parsear el archivo")
            return False
        
        headers = parsed["headers"]
        to_header = headers.get("To", "")
        
        print(f"\n📧 Header 'To:' encontrado:")
        print(f"   {to_header}\n")
        
        # Extraer email
        import html as html_module
        to_decoded = html_module.unescape(to_header)
        print(f"📧 Después de decodificar HTML:")
        print(f"   {to_decoded}\n")
        
        # Función de extracción
        def extract_email_from_address(address: str) -> str:
            if not address:
                return ""
            address = html_module.unescape(address)
            if '<' in address and '>' in address:
                return address[address.find('<')+1:address.find('>')].strip()
            parts = address.split()
            if parts:
                for part in reversed(parts):
                    if '@' in part:
                        return part.strip()
            return address.strip()
        
        email_extraido = extract_email_from_address(to_header)
        print(f"✓ Email extraído: {email_extraido}")
        
        # Verificar que sea válido
        if "@" in email_extraido and "." in email_extraido:
            print(f"✓ Email válido identificado")
            return True
        else:
            print(f"✗ Email no parece válido")
            return False
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Ejecutar pruebas
    resultado1 = test_email_extraction()
    resultado2 = test_with_actual_file()
    
    sys.exit(0 if (resultado1 and resultado2) else 1)
