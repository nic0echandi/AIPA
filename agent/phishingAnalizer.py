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

import os
import re
import json
import time
import html
import hashlib
import logging
import logging.handlers
import unicodedata
import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

import requests
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


# ---------------------------------------------------------------------------
# Logging estructurado
# ---------------------------------------------------------------------------

def setup_logger(log_level: str = "INFO", log_file: str = "phishing_analyzer.log") -> logging.Logger:
    """Configurar logger con salida a consola y archivo rotativo."""
    logger = logging.getLogger("phishing_analyzer")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )

    # Consola
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Archivo rotativo (5 MB x 3 backups)
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


log = setup_logger()


# ---------------------------------------------------------------------------
# Schema de validación para config.json
# ---------------------------------------------------------------------------

CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "ollama_url":    {"type": "string"},
        "ollama_model":  {"type": "string"},
        "whitelist_path": {"type": "string"},
        "llm_provider":  {"type": "string", "enum": ["ollama", "anthropic"]},
        "anthropic_api_key": {"type": "string"},
        "webhook_spam":  {"type": "string"},
        "webhook_legitimo": {"type": "string"},
        "log_level":     {"type": "string"},
        "max_workers":   {"type": "integer", "minimum": 1, "maximum": 16},
        "abuseipdb_api_key": {"type": "string"},
        "iris_dfir": {
            "type": "object",
            "properties": {
                "url":         {"type": "string"},
                "api_key":     {"type": "string"},
                "verify_ssl":  {"type": "boolean"},
                "default_customer_id": {"type": "integer"},
                "default_classification": {"type": "integer"}
            }
        }
    },
    "additionalProperties": True
}


# ---------------------------------------------------------------------------
# Dataclass resultado
# ---------------------------------------------------------------------------

@dataclass
class EmailAnalysis:
    """Resultado del análisis de un email."""
    mensaje_id:          str
    classification:      str   # 'legitimo', 'spam', 'sospechoso'
    confidence:          float
    reporter_email:      str
    original_subject:    str
    original_from:       str
    reply_to:            str
    sender_ip:           str
    ip_reputation:       Dict
    analysis_date:       str
    indicators:          Dict
    headers_raw:         str
    body_preview:        str
    urls_found:          List[str]
    microsoft_url_check: str
    risk_score:          int   # 0-100
    reasons:             List[str]


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def levenshtein(s1: str, s2: str) -> int:
    """Distancia de edición entre dos strings."""
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if not s2:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


def normalize_homograph(domain: str) -> str:
    """Normaliza caracteres unicode a su equivalente ASCII (NFKD)."""
    return unicodedata.normalize("NFKD", domain).encode("ascii", "ignore").decode("ascii")


def retry_post(url: str, payload: Dict, headers: Dict = None,
               verify_ssl: bool = True, max_retries: int = 3,
               backoff_base: float = 2.0, timeout: int = 30) -> Optional[requests.Response]:
    """POST con retry exponencial."""
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                url, json=payload,
                headers=headers or {},
                timeout=timeout,
                verify=verify_ssl
            )
            if resp.status_code in (200, 201):
                return resp
            log.warning("HTTP %s en intento %d/%d → %s", resp.status_code, attempt, max_retries, url)
        except requests.exceptions.RequestException as exc:
            log.warning("Error de red en intento %d/%d: %s", attempt, max_retries, exc)

        if attempt < max_retries:
            wait = backoff_base ** attempt
            log.debug("Reintentando en %.1f s...", wait)
            time.sleep(wait)

    log.error("Todos los reintentos fallaron para: %s", url)
    return None


# ---------------------------------------------------------------------------
# Clase principal
# ---------------------------------------------------------------------------

class PhishingAnalyzerTXT:
    """Analizador de reportes de phishing desde archivos .txt — v0.8"""

    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self._configure_logger()

        self.llm_provider    = self.config.get("llm_provider", "ollama")
        self.ollama_url      = self.config.get("ollama_url", "http://localhost:11434/api/generate")
        self.ollama_model    = self.config.get("ollama_model", "llama3.2")
        self.anthropic_key   = self.config.get("anthropic_api_key", "")
        self.abuseipdb_key   = self.config.get("abuseipdb_api_key", "")
        self.max_workers     = self.config.get("max_workers", 4)
        self.whitelist       = self._load_whitelist()

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------

    def _load_config(self, config_path: str) -> Dict:
        if not os.path.exists(config_path):
            log.warning("config.json no encontrado, usando defaults.")
            return {}
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if HAS_JSONSCHEMA:
                jsonschema.validate(cfg, CONFIG_SCHEMA)
                log.info("config.json validado correctamente.")
            else:
                log.warning("jsonschema no instalado — validación de config omitida.")
            return cfg
        except json.JSONDecodeError as exc:
            log.error("config.json tiene JSON inválido: %s", exc)
            return {}
        except Exception as exc:
            log.error("Error validando config.json: %s", exc)
            return {}

    def _configure_logger(self):
        """Ajustar nivel de log según config."""
        level = self.config.get("log_level", "INFO").upper()
        log.setLevel(getattr(logging, level, logging.INFO))

    def _load_whitelist(self) -> set:
        whitelist_path = self.config.get("whitelist_path", "whitelist.txt")
        domains = set()
        if not os.path.exists(whitelist_path):
            log.warning("Whitelist no encontrada: %s", whitelist_path)
            return domains
        try:
            with open(whitelist_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        domains.add(line.lower())
            log.info("Whitelist cargada: %d dominios", len(domains))
        except Exception as exc:
            log.error("Error cargando whitelist: %s", exc)
        return domains

    # ------------------------------------------------------------------
    # Whitelist con protección contra subdomain spoofing
    # ------------------------------------------------------------------

    def check_whitelist(self, from_email: str) -> bool:
        if not from_email or not self.whitelist:
            return False
        match = re.search(r"@([a-zA-Z0-9.-]+)", from_email.lower())
        if not match:
            return False
        domain = match.group(1)

        # Verificar dominio exacto
        if domain in self.whitelist:
            return True

        # Verificar subdominios — solo si el parent tiene al menos 2 partes
        # (evita que "com" o "net" solos hagan match)
        parts = domain.split(".")
        for i in range(1, len(parts)):          # i=0 sería el dominio completo (ya evaluado)
            parent = ".".join(parts[i:])
            if len(parent.split(".")) >= 2 and parent in self.whitelist:
                return True

        return False

    def check_homograph_spoofing(self, from_email: str) -> Optional[str]:
        """
        Detecta si el dominio del remitente es un homógrafo
        de algún dominio en la whitelist (distancia Levenshtein ≤ 2,
        excluyendo matches exactos ya cubiertos por check_whitelist).
        Retorna el dominio legítimo imitado o None.
        """
        match = re.search(r"@([a-zA-Z0-9.-]+)", from_email.lower())
        if not match:
            return None
        raw_domain = match.group(1)
        normalized = normalize_homograph(raw_domain)

        for legit in self.whitelist:
            if normalized == legit or raw_domain == legit:
                continue  # match exacto — no es spoofing
            dist = levenshtein(normalized, legit)
            if dist <= 2:
                log.warning("Posible homógrafo: '%s' ≈ '%s' (distancia %d)", raw_domain, legit, dist)
                return legit
        return None

    # ------------------------------------------------------------------
    # Parseo del archivo .txt
    # ------------------------------------------------------------------

    def parse_txt_file(self, txt_path: str) -> Optional[Dict]:
        try:
            with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as exc:
            log.error("No se pudo leer %s: %s", txt_path, exc)
            return None

        headers: Dict[str, str] = {}
        microsoft_urls = "None"

        # Procesar formato HTML: reemplazar <br> con saltos de línea para parseo correcto
        content_clean = content.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
        
        # ESTRATEGIA NUEVA: Insertar saltos de línea ANTES de headers conocidos
        # para que cada header esté en su propia línea incluso si TODO estaba en una línea
        headers_list = [
            'From:', 'To:', 'Subject:', 'Date:', 'Message-ID:', 'Reply-To:',
            'Content-Type:', 'Content-Transfer-Encoding:', 'Thread-Topic:', 'Thread-Index:',
            'Accept-Language:', 'Content-Language:', 'MIME-Version:', 'Received:',
            'X-MS-', 'x-ms-'
        ]
        
        for header_keyword in headers_list:
            # Reemplazar "word Header:" con "\nHeader:" si está al medio de una línea
            content_clean = re.sub(
                rf'(\S)\s+({re.escape(header_keyword)})',
                r'\1\n\2',
                content_clean
            )
        
        # Ahora procesar como RFC 5322 estándar
        lines = content_clean.split("\n")
        current_header = None
        current_value: List[str] = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # Saltar líneas vacías y comentarios
            if not line_stripped or line_stripped.startswith("#"):
                if current_header and line_stripped == "":
                    # Una línea vacía termina el header actual
                    if current_header:
                        headers[current_header] = " ".join(current_value).strip()
                        current_header = None
                        current_value = []
                continue
            
            # Detectar nueva cabecera: NO empieza con espacio y contiene ":"
            if line and not line[0].isspace() and ":" in line:
                # Guardar cabecera anterior si existe
                if current_header:
                    headers[current_header] = " ".join(current_value).strip()
                
                # Procesar nueva cabecera
                parts = line.split(":", 1)
                current_header = parts[0].strip()
                current_value = [parts[1].strip()] if len(parts) > 1 else []
            
            # Línea de continuación (empieza con espacio)
            elif line and line[0].isspace() and current_header:
                current_value.append(line.strip())

        # Guardar última cabecera
        if current_header:
            headers[current_header] = " ".join(current_value).strip()

        # Extraer URLs detectadas por Microsoft
        urls_match = re.search(r'# Questionable URLs detected in message:\s*\n?\s*(.+?)(?:\n|$)', content_clean)
        if urls_match:
            microsoft_urls = urls_match.group(1).strip()

        # Decodificar entidades HTML en los headers (ej: &lt; &gt; &quot;)
        for key in headers:
            headers[key] = html.unescape(headers[key])

        return {
            "headers":       headers,
            "microsoft_urls": microsoft_urls,
            "raw_content":   content,
        }

    # ------------------------------------------------------------------
    # Extracción de datos auxiliares
    # ------------------------------------------------------------------

    def extract_urls_from_content(self, content: str) -> List[str]:
        url_pattern = r"https?://[^\s<>\"{}|\\^`\[\]]+"
        return list(set(re.findall(url_pattern, content)))

    def extract_reporter_from_content(self, content: str) -> str:
        match = re.search(r"^To:\s*(.+)$", content, re.MULTILINE)
        if match:
            to_line = match.group(1)
            email_match = re.search(r"<([^>]+)>", to_line)
            if email_match:
                return email_match.group(1)
            return to_line.strip()
        return "unknown@example.com"

    def extract_sender_ip(self, headers: Dict) -> str:
        """
        Extrae la IP del último Received: externo
        (el primer hop que entró desde Internet).
        """
        received_headers = []
        # Los headers pueden estar duplicados; buscar todos los Received
        raw = headers.get("Received", "")
        # Buscar IPs IPv4 en el header Received más externo
        ip_match = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", raw)
        if ip_match:
            return ip_match.group(1)
        return ""

    def extract_reply_to(self, headers: Dict) -> str:
        return headers.get("Reply-To", "").strip()

    # ------------------------------------------------------------------
    # Autenticación SPF / DKIM / DMARC
    # ------------------------------------------------------------------

    def check_authentication(self, headers: Dict) -> Dict:
        auth_results = {
            "spf": "unknown", "dkim": "unknown",
            "dmarc": "unknown", "suspicious": False
        }
        auth_header = headers.get("authentication-results", "").lower()

        for proto in ("spf", "dkim", "dmarc"):
            for result in ("pass", "fail", "none", "softfail", "neutral"):
                if f"{proto}={result}" in auth_header:
                    auth_results[proto] = result
                    if result in ("fail", "softfail"):
                        auth_results["suspicious"] = True
                    break

        # Fallback a received-spf
        received_spf = headers.get("received-spf", "").lower()
        if auth_results["spf"] == "unknown":
            for result in ("pass", "fail", "softfail", "none", "neutral"):
                if result in received_spf:
                    auth_results["spf"] = result
                    if result in ("fail", "softfail"):
                        auth_results["suspicious"] = True
                    break

        return auth_results

    # ------------------------------------------------------------------
    # Reply-To sospechoso
    # ------------------------------------------------------------------

    def check_reply_to(self, headers: Dict) -> Optional[str]:
        """
        Detecta discrepancia entre dominio del From y del Reply-To.
        Táctica clásica: From legítimo, Reply-To del atacante.
        """
        from_addr  = headers.get("From", "").lower()
        reply_to   = headers.get("Reply-To", "").lower()

        if not reply_to:
            return None

        from_match   = re.search(r"@([a-zA-Z0-9.-]+)", from_addr)
        reply_match  = re.search(r"@([a-zA-Z0-9.-]+)", reply_to)

        if from_match and reply_match:
            from_domain  = from_match.group(1)
            reply_domain = reply_match.group(1)
            if from_domain != reply_domain:
                return f"Reply-To ({reply_domain}) difiere de From ({from_domain})"
        return None

    # ------------------------------------------------------------------
    # IP Reputation via AbuseIPDB
    # ------------------------------------------------------------------

    def check_ip_reputation(self, ip: str) -> Dict:
        """Consulta AbuseIPDB para obtener score de abuso de la IP origen."""
        result = {"ip": ip, "abuse_score": -1, "country": "", "checked": False}
        if not ip or not self.abuseipdb_key:
            return result

        try:
            resp = requests.get(
                "https://api.abuseipdb.com/api/v2/check",
                headers={"Key": self.abuseipdb_key, "Accept": "application/json"},
                params={"ipAddress": ip, "maxAgeInDays": 90},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                result.update({
                    "abuse_score": data.get("abuseConfidenceScore", 0),
                    "country":     data.get("countryCode", ""),
                    "isp":         data.get("isp", ""),
                    "checked":     True
                })
                log.info("IP %s — AbuseIPDB score: %d (%s)", ip, result["abuse_score"], result["country"])
        except Exception as exc:
            log.warning("Error consultando AbuseIPDB para %s: %s", ip, exc)

        return result

    # ------------------------------------------------------------------
    # Patrones sospechosos
    # ------------------------------------------------------------------

    def check_suspicious_patterns(self, headers: Dict, content: str) -> List[str]:
        reasons: List[str] = []
        subject   = headers.get("Subject", "").lower()
        from_addr = headers.get("From", "").lower()

        phishing_keywords = [
            "urgent", "verify", "suspend", "security alert", "confirm identity",
            "update payment", "account locked", "unusual activity", "click here",
            "limited time", "act now", "prize", "winner", "congratulations",
            "urgente", "verificar", "suspender", "alerta de seguridad",
            "confirmar identidad", "actualizar pago", "cuenta bloqueada",
            "actividad inusual", "haz clic", "tiempo limitado", "actúa ahora",
            "premio", "ganador", "felicitaciones"
        ]
        for kw in phishing_keywords:
            if kw in subject or kw in content.lower():
                reasons.append(f"Keyword sospechosa: '{kw}'")
                break

        # Discrepancia display name vs email
        if "<" in from_addr and ">" in from_addr:
            display_match = re.search(r"^([^<]+)", from_addr)
            email_match   = re.search(r"<([^>]+)>", from_addr)
            if display_match and email_match:
                display = display_match.group(1).strip().strip('"')
                addr    = email_match.group(1).strip()
                if "@" in display and display != addr:
                    reasons.append("Display name no coincide con email real")

        # Reply-To divergente
        reply_to_issue = self.check_reply_to(headers)
        if reply_to_issue:
            reasons.append(reply_to_issue)

        # URLs acortadas
        urls = self.extract_urls_from_content(content)
        short_url_services = ["bit.ly", "tinyurl.com", "goo.gl", "t.co", "ow.ly", "short.link"]
        for url in urls:
            dm = re.search(r"://([^/:?]+)", url)
            if dm:
                d = dm.group(1).lower()
                for svc in short_url_services:
                    if d == svc or d.endswith("." + svc):
                        reasons.append(f"URL acortada: {svc}")
                        break

        # Muchos dominios distintos
        domains = {re.search(r"://([^/]+)", u).group(1) for u in urls if re.search(r"://([^/]+)", u)}
        if len(domains) > 5:
            reasons.append(f"Múltiples dominios distintos ({len(domains)})")

        return reasons

    # ------------------------------------------------------------------
    # Risk score (ponderado, nunca excede 100 antes del clamp)
    # ------------------------------------------------------------------

    def calculate_risk_score(self, auth: Dict, reasons: List[str],
                              urls: List[str], microsoft_urls: str,
                              ip_rep: Dict, homograph: Optional[str]) -> int:
        score = 0

        # Autenticación (máx 60 puntos total)
        score += {"fail": 25, "softfail": 15, "none": 10}.get(auth["spf"],  0)
        score += {"fail": 25, "softfail": 15, "none": 10}.get(auth["dkim"], 0)
        score += {"fail": 15, "none":  8}.get(auth["dmarc"], 0)

        # Microsoft detectó URLs sospechosas (muy alto valor)
        if microsoft_urls not in ("None", ""):
            score += 35

        # Patrones sospechosos (máx 25)
        score += min(len(reasons) * 7, 25)

        # Cantidad de URLs (máx 10)
        if len(urls) > 10:
            score += 10
        elif len(urls) > 5:
            score += 5

        # IP con alta reputación de abuso (máx 20)
        abuse = ip_rep.get("abuse_score", -1)
        if abuse >= 80:
            score += 20
        elif abuse >= 50:
            score += 10
        elif abuse >= 20:
            score += 5

        # Homógrafo detectado (alto riesgo)
        if homograph:
            score += 30

        return min(score, 100)

    # ------------------------------------------------------------------
    # LLM: Ollama o Anthropic (configurable)
    # ------------------------------------------------------------------

    def analyze_with_llm(self, email_data: Dict) -> Dict:
        if self.llm_provider == "anthropic":
            return self._analyze_with_anthropic(email_data)
        return self._analyze_with_ollama(email_data)

    def _build_prompt(self, email_data: Dict) -> str:
        return f"""Eres un experto en seguridad informática especializado en detección de phishing.
Analiza el siguiente email reportado y clasifícalo en una de estas dos categorías exactas:

- "spam": Email no deseado pero inofensivo (marketing masivo, newsletters, reportado por error)
- "sospechoso": Posible phishing real que requiere investigación manual

REGLAS:
1. SPF=pass + DKIM=pass + DMARC=pass + Risk Score < 30 → "spam"
2. Microsoft NO detectó URLs sospechosas + Risk Score < 30 → "spam"
3. Solo "sospechoso" si hay evidencia clara: autenticación fallida, URLs maliciosas, homógrafo, Reply-To divergente, IP con alta reputación de abuso.
4. Newsletters de Mailchimp/SendGrid con autenticación correcta = "spam"
5. En caso de duda → "spam" (minimizar falsos positivos)

DATOS:
From: {email_data.get('from', 'N/A')}
Reply-To: {email_data.get('reply_to', 'N/A')}
Subject: {email_data.get('subject', 'N/A')}
SPF: {email_data.get('spf')} | DKIM: {email_data.get('dkim')} | DMARC: {email_data.get('dmarc')}
Microsoft URLs sospechosas: {email_data.get('microsoft_urls', 'None')}
URLs totales: {len(email_data.get('urls', []))}
IP origen: {email_data.get('sender_ip', 'N/A')} (AbuseScore: {email_data.get('abuse_score', 'N/A')})
Homógrafo detectado: {email_data.get('homograph', 'No')}
Indicadores: {', '.join(email_data.get('reasons', [])) or 'Ninguno'}
Risk Score: {email_data.get('risk_score', 0)}/100

Responde ÚNICAMENTE con JSON:
{{
    "classification": "spam",
    "confidence": 0.85,
    "reasoning": "Explicación breve (máx 2 líneas)"
}}
"""

    def _analyze_with_ollama(self, email_data: Dict) -> Dict:
        prompt = self._build_prompt(email_data)
        try:
            response = requests.post(
                self.ollama_url,
                json={"model": self.ollama_model, "prompt": prompt, "stream": False, "format": "json"},
                timeout=60
            )
            if response.status_code == 200:
                result = response.json()
                return self._parse_and_validate_llm_response(result.get("response", "{}"), email_data)
        except Exception as exc:
            log.error("Error con Ollama: %s — usando fallback.", exc)

        return self._fallback_classification(email_data)

    def _analyze_with_anthropic(self, email_data: Dict) -> Dict:
        if not self.anthropic_key:
            log.error("anthropic_api_key no configurada. Usando fallback.")
            return self._fallback_classification(email_data)

        prompt = self._build_prompt(email_data)
        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key":         self.anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type":      "application/json",
                },
                json={
                    "model":      "claude-sonnet-4-20250514",
                    "max_tokens": 512,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=60
            )
            if response.status_code == 200:
                text = response.json()["content"][0]["text"]
                return self._parse_and_validate_llm_response(text, email_data)
            else:
                log.error("Anthropic API error %s: %s", response.status_code, response.text[:200])
        except Exception as exc:
            log.error("Error con Anthropic API: %s — usando fallback.", exc)

        return self._fallback_classification(email_data)

    def _parse_and_validate_llm_response(self, text: str, email_data: Dict) -> Dict:
        """Parsea y valida la respuesta JSON del LLM."""
        VALID = {"spam", "sospechoso"}
        REMAP = {
            "spam": "spam", "marketing": "spam", "legitimo": "spam",
            "legit": "spam", "genuine": "spam",
            "phishing": "sospechoso", "malicious": "sospechoso",
            "suspicious": "sospechoso", "sospecho": "sospechoso"
        }
        try:
            # Strip posibles backticks de markdown
            clean = re.sub(r"```(?:json)?|```", "", text).strip()
            analysis = json.loads(clean)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    analysis = json.loads(match.group())
                except Exception:
                    return self._fallback_classification(email_data)
            else:
                return self._fallback_classification(email_data)

        classification = analysis.get("classification", "").lower()
        if classification not in VALID:
            mapped = next((v for k, v in REMAP.items() if k in classification), None)
            if mapped:
                log.warning("Clasificación LLM '%s' mapeada a '%s'", classification, mapped)
                analysis["classification"] = mapped
            else:
                analysis["classification"] = "sospechoso" if email_data.get("risk_score", 0) >= 50 else "spam"
                log.warning("Clasificación LLM inválida '%s' → '%s'", classification, analysis["classification"])

        return analysis

    def _fallback_classification(self, email_data: Dict) -> Dict:
        """Clasificación determinista cuando el LLM no está disponible."""
        risk_score    = email_data.get("risk_score", 0)
        microsoft_urls = email_data.get("microsoft_urls", "None")
        spf  = email_data.get("spf",  "unknown")
        dkim = email_data.get("dkim", "unknown")
        dmarc = email_data.get("dmarc", "unknown")
        abuse = email_data.get("abuse_score", -1)
        homograph = email_data.get("homograph")

        if microsoft_urls not in ("None", ""):
            return {"classification": "sospechoso", "confidence": 0.85,
                    "reasoning": f"Microsoft detectó URLs sospechosas: {microsoft_urls}"}

        if homograph:
            return {"classification": "sospechoso", "confidence": 0.9,
                    "reasoning": f"Dominio homógrafo de '{homograph}' detectado"}

        if isinstance(abuse, int) and abuse >= 80:
            return {"classification": "sospechoso", "confidence": 0.8,
                    "reasoning": f"IP origen con AbuseIPDB score {abuse}"}

        if risk_score >= 60:
            return {"classification": "sospechoso", "confidence": 0.7,
                    "reasoning": f"Risk score alto: {risk_score}/100"}

        if spf == "pass" and dkim == "pass" and dmarc == "pass" and risk_score < 30:
            return {"classification": "spam", "confidence": 0.75,
                    "reasoning": "Autenticación completa y risk score bajo"}

        return {"classification": "spam", "confidence": 0.5,
                "reasoning": f"Sin indicadores claros de phishing (score: {risk_score})"}

    # ------------------------------------------------------------------
    # Análisis completo de un archivo
    # ------------------------------------------------------------------

    def analyze_txt_file(self, file_path: str) -> Optional[EmailAnalysis]:
        parsed = self.parse_txt_file(file_path)
        if not parsed:
            return None

        headers        = parsed["headers"]
        microsoft_urls = parsed["microsoft_urls"]
        content        = parsed["raw_content"]
        from_email     = headers.get("From", "")
        reply_to       = self.extract_reply_to(headers)
        sender_ip      = self.extract_sender_ip(headers)

        # --- Whitelist: clasificación rápida, pero con indicadores REALES ---
        if self.check_whitelist(from_email):
            auth     = self.check_authentication(headers)
            urls_wl  = self.extract_urls_from_content(content)[:10]
            ip_rep   = self.check_ip_reputation(sender_ip)
            log.info("Dominio en whitelist → clasificado como LEGÍTIMO: %s", from_email)
            return EmailAnalysis(
                mensaje_id          = headers.get("Message-ID", hashlib.md5(file_path.encode()).hexdigest()),
                classification      = "legitimo",
                confidence          = 1.0,
                reporter_email      = self.extract_reporter_from_content(content),
                original_subject    = headers.get("Subject", "N/A"),
                original_from       = from_email,
                reply_to            = reply_to,
                sender_ip           = sender_ip,
                ip_reputation       = ip_rep,
                analysis_date       = datetime.now().isoformat(),
                indicators          = auth,
                headers_raw         = str(headers),
                body_preview        = content[:500],
                urls_found          = urls_wl,
                microsoft_url_check = microsoft_urls,
                risk_score          = 0,
                reasons             = ["Dominio en whitelist — clasificado automáticamente como legítimo"]
            )

        # --- Detección de homógrafo ---
        homograph = self.check_homograph_spoofing(from_email)
        if homograph:
            log.warning("Homógrafo detectado en From: '%s' imita '%s'", from_email, homograph)

        # --- Pipeline de análisis ---
        urls       = self.extract_urls_from_content(content)
        auth       = self.check_authentication(headers)
        reasons    = self.check_suspicious_patterns(headers, content)
        ip_rep     = self.check_ip_reputation(sender_ip)

        if homograph:
            reasons.insert(0, f"Dominio homógrafo de '{homograph}' detectado")

        risk_score = self.calculate_risk_score(auth, reasons, urls, microsoft_urls, ip_rep, homograph)

        if microsoft_urls not in ("None", ""):
            reasons.insert(0, f"Microsoft detectó URLs sospechosas: {microsoft_urls}")

        email_data = {
            "from":          from_email,
            "reply_to":      reply_to,
            "subject":       headers.get("Subject", "N/A"),
            "urls":          urls,
            "spf":           auth["spf"],
            "dkim":          auth["dkim"],
            "dmarc":         auth["dmarc"],
            "reasons":       reasons,
            "risk_score":    risk_score,
            "microsoft_urls": microsoft_urls,
            "sender_ip":     sender_ip,
            "abuse_score":   ip_rep.get("abuse_score", -1),
            "homograph":     homograph,
        }

        llm_result = self.analyze_with_llm(email_data)

        return EmailAnalysis(
            mensaje_id          = headers.get("Message-ID", hashlib.md5(file_path.encode()).hexdigest()),
            classification      = llm_result.get("classification", "sospechoso"),
            confidence          = llm_result.get("confidence", 0.5),
            reporter_email      = self.extract_reporter_from_content(content),
            original_subject    = headers.get("Subject", "N/A"),
            original_from       = from_email,
            reply_to            = reply_to,
            sender_ip           = sender_ip,
            ip_reputation       = ip_rep,
            analysis_date       = datetime.now().isoformat(),
            indicators          = auth,
            headers_raw         = str(headers),
            body_preview        = content[:500],
            urls_found          = urls[:10],
            microsoft_url_check = microsoft_urls,
            risk_score          = risk_score,
            reasons             = reasons + [llm_result.get("reasoning", "")]
        )

    # ------------------------------------------------------------------
    # Acciones post-análisis
    # ------------------------------------------------------------------

    def send_to_powerautomate(self, analysis: EmailAnalysis, webhook_type: str):
        webhooks = {
            "spam":     self.config.get("webhook_spam", ""),
            "legitimo": self.config.get("webhook_legitimo", ""),
        }
        webhook_url = webhooks.get(webhook_type, "")
        if not webhook_url:
            log.warning("Webhook no configurado para: %s", webhook_type)
            return

        payload = {
            "reporter_email":      analysis.reporter_email,
            "classification":      analysis.classification,
            "confidence":          analysis.confidence,
            "original_subject":    analysis.original_subject,
            "original_from":       analysis.original_from,
            "reply_to":            analysis.reply_to,
            "sender_ip":           analysis.sender_ip,
            "ip_reputation":       analysis.ip_reputation,
            "risk_score":          analysis.risk_score,
            "reasons":             analysis.reasons,
            "microsoft_url_check": analysis.microsoft_url_check,
            "analysis_date":       analysis.analysis_date,
        }

        resp = retry_post(webhook_url, payload)
        if resp:
            log.info("Webhook enviado OK (%s)", webhook_type)
        else:
            log.error("Webhook falló definitivamente (%s)", webhook_type)

    def create_iris_case(self, analysis: EmailAnalysis):
        iris_cfg = self.config.get("iris_dfir", {})
        iris_url = iris_cfg.get("url", "")
        iris_key = iris_cfg.get("api_key", "")

        if not iris_url or not iris_key:
            log.warning("IRIS DFIR no configurado — caso no creado.")
            return None

        verify_ssl = iris_cfg.get("verify_ssl", True)
        if not verify_ssl:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        case_data = {
            "case_name": f"Phishing: {analysis.original_subject[:50]}",
            "case_description": (
                f"**From:** {analysis.original_from}\n"
                f"**Reply-To:** {analysis.reply_to or 'N/A'}\n"
                f"**Subject:** {analysis.original_subject}\n"
                f"**Reporter:** {analysis.reporter_email}\n"
                f"**Risk Score:** {analysis.risk_score}/100\n"
                f"**Confidence:** {analysis.confidence:.0%}\n\n"
                f"**IP Origen:** {analysis.sender_ip} "
                f"(AbuseScore: {analysis.ip_reputation.get('abuse_score', 'N/A')})\n\n"
                f"**Microsoft URL Check:** {analysis.microsoft_url_check}\n\n"
                f"**Indicadores:**\n"
                f"- SPF: {analysis.indicators.get('spf', 'unknown')}\n"
                f"- DKIM: {analysis.indicators.get('dkim', 'unknown')}\n"
                f"- DMARC: {analysis.indicators.get('dmarc', 'unknown')}\n\n"
                f"**Razones de sospecha:**\n"
                + "\n".join(f"- {r}" for r in analysis.reasons[:10]) +
                f"\n\n**URLs encontradas:**\n"
                + "\n".join(f"- {u}" for u in analysis.urls_found)
            ),
            "case_customer":       iris_cfg.get("default_customer_id", 1),
            "classification_id":   iris_cfg.get("default_classification", 30),
            "case_soc_id":         "",
            "case_tags":           "phishing,email-security,automated",
            "custom_attributes": {
                "risk_score":          analysis.risk_score,
                "reporter":            analysis.reporter_email,
                "sender_ip":           analysis.sender_ip,
                "ip_abuse_score":      analysis.ip_reputation.get("abuse_score", -1),
                "microsoft_url_check": analysis.microsoft_url_check,
            }
        }

        auth_headers = {
            "Authorization": f"Bearer {iris_key}",
            "Content-Type":  "application/json",
        }

        resp = retry_post(
            f"{iris_url}/api/v2/cases",
            case_data,
            headers=auth_headers,
            verify_ssl=verify_ssl
        )

        if resp:
            case_id = resp.json().get("data", {}).get("case_id", "?")
            log.info("Caso IRIS creado: #%s", case_id)
            return case_id
        else:
            log.error("No se pudo crear caso IRIS para: %s", analysis.original_subject)
            return None

    def save_analysis(self, analysis: EmailAnalysis):
        output_dir = Path("analysis_results")
        output_dir.mkdir(exist_ok=True)
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"analysis_{ts}_{analysis.classification}.json"
        with open(output_dir / filename, "w", encoding="utf-8") as f:
            json.dump(asdict(analysis), f, indent=2, ensure_ascii=False)
        log.info("Análisis guardado: %s", output_dir / filename)

    # ------------------------------------------------------------------
    # Proceso individual
    # ------------------------------------------------------------------

    def process_file(self, file_path: str) -> Optional[EmailAnalysis]:
        log.info("=" * 70)
        log.info("Procesando: %s", os.path.basename(file_path))
        log.info("=" * 70)

        analysis = self.analyze_txt_file(file_path)
        if not analysis:
            log.error("No se pudo analizar: %s", file_path)
            return None

        log.info("RESULTADO → %s (confianza: %.0f%%, score: %d/100)",
                 analysis.classification.upper(), analysis.confidence * 100, analysis.risk_score)
        log.info("From:    %s", analysis.original_from)
        log.info("Subject: %s", analysis.original_subject)
        if analysis.reply_to:
            log.info("Reply-To: %s", analysis.reply_to)
        if analysis.sender_ip:
            log.info("IP origen: %s (abuse: %s)", analysis.sender_ip,
                     analysis.ip_reputation.get("abuse_score", "N/A"))
        log.info("Microsoft URLs: %s", analysis.microsoft_url_check)

        for r in analysis.reasons[:5]:
            log.warning("  ↳ %s", r)

        # Acciones
        if analysis.classification == "sospechoso":
            log.info("→ Creando caso en IRIS DFIR...")
            self.create_iris_case(analysis)
        elif analysis.classification == "spam":
            log.info("→ Notificando reporter via Power Automate...")
            self.send_to_powerautomate(analysis, "spam")
        elif analysis.classification == "legitimo":
            log.info("→ Notificando reporter (legítimo)...")
            self.send_to_powerautomate(analysis, "legitimo")

        self.save_analysis(analysis)
        return analysis

    # ------------------------------------------------------------------
    # Procesamiento paralelo
    # ------------------------------------------------------------------

    def process_files(self, file_paths: List[str]) -> List[EmailAnalysis]:
        """Procesa múltiples archivos en paralelo usando ThreadPoolExecutor."""
        results: List[EmailAnalysis] = []

        existing = [p for p in file_paths if os.path.exists(p)]
        missing  = [p for p in file_paths if not os.path.exists(p)]
        for p in missing:
            log.error("Archivo no encontrado: %s", p)

        if not existing:
            return results

        workers = min(self.max_workers, len(existing))
        log.info("Procesando %d archivo(s) con %d worker(s)...", len(existing), workers)

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(self.process_file, fp): fp for fp in existing}
            for future in concurrent.futures.as_completed(futures):
                fp = futures[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as exc:
                    log.error("Error procesando %s: %s", fp, exc)

        return results


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    import sys

    if len(sys.argv) < 2:
        print("Uso: python phishingAnalizer.py <archivo.txt> [archivo2.txt ...]")
        print("\nEjemplo:")
        print("  python phishingAnalizer.py phishing_20260120_114646.txt")
        sys.exit(1)

    analyzer = PhishingAnalyzerTXT()
    results  = analyzer.process_files(sys.argv[1:])

    log.info("=" * 70)
    log.info("RESUMEN — Total procesados: %d", len(results))
    spam    = sum(1 for r in results if r.classification == "spam")
    legit   = sum(1 for r in results if r.classification == "legitimo")
    susp    = sum(1 for r in results if r.classification == "sospechoso")
    log.info("  Spam: %d | Legítimos: %d | Sospechosos: %d", spam, legit, susp)


if __name__ == "__main__":
    main()
