#!/usr/bin/env python3
"""
Script de prueba para SuperAgent_2
Crea archivos de ejemplo en ingress/ para probar el flujo completo
"""

import os
from pathlib import Path

# Crear directorio ingress si no existe
ingress_dir = Path(__file__).parent.parent / "ingress"
ingress_dir.mkdir(parents=True, exist_ok=True)

# Ejemplos de emails TXT

EXAMPLE_PHISHING = """Received: from attacker-mail.com (23.251.247.211) by protection.outlook.com (10.167.241.200) with Microsoft SMTP Server
Content-Type: text/html; charset="utf-8"
From: "Banco Seguro" <noreply@banco-seguro-verificacion.com>
To: "Usuario Reporta" <reporter@company.com>
Subject: [URGENTE] Verifica tu cuenta ahora - Acción requerida
Thread-Topic: Verificación de cuenta
Date: Mon, 28 May 2026 10:30:00 +0000
Message-ID: <phishing_example_001@attacker-mail.com>
X-Originating-IP: [192.168.100.50]
X-MS-Has-Attach: 
Authentication-Results: spf=fail; dkim=fail; dmarc=fail
received-spf: Fail (protection.outlook.com: domain of attacker-mail.com does not designate 23.251.247.211 as permitted sender)
x-forefront-antispam-report: CIP:23.251.247.211;LANG:es;SCL:7;SRV:;IPV:NLI;SFV:NSPM

Tu cuenta ha sido bloqueada. Haz clic aquí INMEDIATAMENTE para verificar tu identidad y evitar que se cierre permanentemente:

http://banco-seguro-verificaci0n.com/account/login?session=12345

NO compartas esta información con nadie.

Equipo de Seguridad Banco
"""

EXAMPLE_SPAM = """Received: from marketing-smtp.example.com (192.0.2.100) by protection.outlook.com
Content-Type: text/html; charset="utf-8"
From: "Ofertas Especiales" <promotions@offers-unlimited.net>
To: "Usuario Reporta" <reporter@company.com>
Subject: ¡MEGA DESCUENTO 90% EN TODO! Hoy solamente
Date: Mon, 28 May 2026 12:00:00 +0000
Message-ID: <spam_example_001@offers-unlimited.net>
X-MS-Has-Attach: true
Authentication-Results: spf=neutral; dkim=none; dmarc=none

¡HOLA!

Solo hoy: 90% de descuento en TODOS nuestros productos premium.

>>> CLICK AQUI PARA COMPRAR <<<
www.offers-unlimited.net/mega-sale?ref=campaign_001

No dejes pasar esta oportunidad. Stock limitado.

---
Marketing Team
Desuscribirse: www.offers-unlimited.net/unsub
"""

EXAMPLE_LEGITIMATE = """Received: from github.com (140.82.113.3) by protection.outlook.com with TLS
Content-Type: text/plain; charset="utf-8"
From: GitHub <noreply@github.com>
To: "Developer Company" <developer@company.com>
Subject: Security Alert: Potential secret detected in repository
Thread-Topic: GitHub Security Alert
Date: Mon, 28 May 2026 14:15:00 +0000
Message-ID: <github-security-123456@github.com>
Authentication-Results: spf=pass; dkim=pass; dmarc=pass
received-spf: Pass (protection.outlook.com: domain of github.com designates 140.82.113.3 as permitted sender)

Hello,

We detected a potential secret in your repository push. This is a proactive security measure.

Repository: your-org/your-repo
Commit: abc123def456

View and dismiss alert:
https://github.com/your-org/your-repo/security/secret-scanning

Best regards,
GitHub Security Team
"""

# Crear archivos de ejemplo
examples = [
    ("phishing_example_001.txt", EXAMPLE_PHISHING),
    ("spam_example_001.txt", EXAMPLE_SPAM),
    ("legitimate_example_001.txt", EXAMPLE_LEGITIMATE),
]

for filename, content in examples:
    filepath = ingress_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✓ Creado: {filepath}")

print(f"\n✓ Archivos de prueba creados en: {ingress_dir}")
print("Inicia SuperAgent_2 para procesar estos archivos")
