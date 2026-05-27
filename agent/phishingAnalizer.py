#!/usr/bin/env python3
"""
Analizador de Reportes de Phishing - Versión 0.8
Lee archivos .txt con headers de emails reportados

Mejoras v0.8:
	- Logging estructurado con niveles (reemplaza print())
	- Retry con backoff exponencial en webhooks
	- Detección de Reply-To sospechoso
	- Verificación de IP reputation (AbuseIPDB)
	- Detección de homógrafos via Levenshtein
	- Validación de config.json con jsonschema
	- Procesamiento paralelo con ThreadPoolExecutor
	- Indicadores reales en clasificación whitelist
	- Subdomain spoofing mitigation en check_whitelist
	- Proveedor de LLM configurable (Ollama o Anthropic)
"""

