#!/usr/bin/env python3
"""
Script para anonimizar config.json antes de compartirlo o hacer commits.
Oculta credenciales, URLs, direcciones de correo y otros datos sensibles.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any


def anonymize_email(email: str) -> str:
    """Anonimiza direcciones de correo."""
    if not email or '@' not in email:
        return email
    
    user, domain = email.split('@', 1)
    return f"[REDACTED_USER]@[REDACTED_DOMAIN]"


def anonymize_url(url: str) -> str:
    """Anonimiza URLs."""
    if not url:
        return url
    
    # Extraer solo protocolo
    if '://' in url:
        protocol = url.split('://')[0]
        return f"{protocol}://[REDACTED_HOST]/[REDACTED_PATH]"
    
    return "[REDACTED_URL]"


def anonymize_ip(ip: str) -> str:
    """Anonimiza direcciones IP."""
    if not ip:
        return ip
    
    # Patrón IPv4
    if re.match(r'^\d+\.\d+\.\d+\.\d+', ip):
        return "[REDACTED_IP]"
    
    # Patrón IPv6
    if ':' in ip and re.match(r'^[0-9a-f:]+', ip, re.I):
        return "[REDACTED_IPV6]"
    
    return ip


def anonymize_domain(domain: str) -> str:
    """Anonimiza nombres de dominio."""
    if not domain:
        return domain
    
    if re.match(r'^[a-z0-9.-]+\.[a-z]{2,}$', domain, re.I):
        return "[REDACTED_DOMAIN]"
    
    return domain


def anonymize_value(key: str, value: Any) -> Any:
    """Anonimiza un valor según su clave."""
    if not isinstance(value, str):
        return value
    
    value = value.strip()
    if not value:
        return value
    
    # Claves que contienen credenciales o datos sensibles
    sensitive_keys = [
        "api_key", "apikey", "api_secret", "secret", "password", "passwd",
        "token", "auth", "credential", "key", "access_token", "bearer"
    ]
    
    # Claves que contienen datos de contacto
    email_keys = ["email", "mail", "reporter", "address", "from", "to"]
    
    # Claves que contienen URLs/hosts
    url_keys = ["url", "host", "server", "endpoint", "address", "connection"]
    
    # Claves que contienen IP
    ip_keys = ["ip", "address", "host", "server"]
    
    # Claves que contienen dominios
    domain_keys = ["domain", "hostname", "host"]
    
    key_lower = key.lower()
    
    # Aplicar anonimización según la clave
    if any(sk in key_lower for sk in sensitive_keys):
        return "[REDACTED_CREDENTIAL]"
    
    if any(ek in key_lower for ek in email_keys) and '@' in value:
        return anonymize_email(value)
    
    if any(uk in key_lower for uk in url_keys) and ('://' in value or '.' in value):
        if '://' in value:
            return anonymize_url(value)
        elif re.match(r'^\d+\.\d+\.\d+\.\d+', value):
            return anonymize_ip(value)
        elif re.match(r'^[a-z0-9.-]+\.[a-z]{2,}', value, re.I):
            return anonymize_domain(value)
    
    if any(ik in key_lower for ik in ip_keys) and re.match(r'^\d+\.\d+', value):
        return anonymize_ip(value)
    
    if any(dk in key_lower for dk in domain_keys) and re.match(r'^[a-z0-9.-]+\.[a-z]{2,}', value, re.I):
        return anonymize_domain(value)
    
    # Buscar patrones comunes
    if re.match(r'^\d+\.\d+\.\d+\.\d+', value):  # IP
        return anonymize_ip(value)
    
    if '@' in value:  # Email
        return anonymize_email(value)
    
    if re.match(r'^https?://', value):  # URL
        return anonymize_url(value)
    
    if re.match(r'^[a-z0-9.-]+\.[a-z]{2,}$', value, re.I):  # Domain
        return anonymize_domain(value)
    
    return value


def anonymize_dict(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Anonimiza recursivamente un diccionario."""
    result = {}
    
    for key, value in obj.items():
        if isinstance(value, dict):
            result[key] = anonymize_dict(value)
        elif isinstance(value, list):
            result[key] = [
                anonymize_dict(item) if isinstance(item, dict) else anonymize_value(key, item)
                for item in value
            ]
        else:
            result[key] = anonymize_value(key, value)
    
    return result


def anonymize_config(input_file: str, output_file: str):
    """Lee config.json, anonimiza y guarda."""
    input_path = Path(input_file)
    
    if not input_path.exists():
        print(f"❌ Error: {input_file} no existe")
        return False
    
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        print(f"📖 Leyendo: {input_file}")
        
        # Anonimizar
        anon_config = anonymize_dict(config)
        
        # Guardar
        output_path = Path(output_file)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(anon_config, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Anonimizado guardado en: {output_file}")
        
        # Mostrar resumen
        print("\n📋 Resumen de anonimización:")
        print("   • Credenciales (API keys, passwords) → [REDACTED_CREDENTIAL]")
        print("   • Direcciones de email → [REDACTED_USER]@[REDACTED_DOMAIN]")
        print("   • URLs/Hosts → [REDACTED_HOST]/[REDACTED_PATH]")
        print("   • Direcciones IP → [REDACTED_IP]")
        print("   • Dominios → [REDACTED_DOMAIN]")
        
        return True
    
    except json.JSONDecodeError as e:
        print(f"❌ Error: JSON inválido en {input_file}: {e}")
        return False
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        # Usar valores por defecto
        input_file = "config.json"
        output_file = "config_anonymized.json"
    elif len(sys.argv) == 2:
        input_file = sys.argv[1]
        output_file = "config_anonymized.json"
    else:
        input_file = sys.argv[1]
        output_file = sys.argv[2]
    
    print("=" * 60)
    print("ANONIMIZADOR DE CONFIG.JSON")
    print("=" * 60)
    print()
    
    success = anonymize_config(input_file, output_file)
    
    if success:
        print("\n✅ Proceso completado exitosamente")
        sys.exit(0)
    else:
        print("\n❌ Proceso fallido")
        sys.exit(1)
gi