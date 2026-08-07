#!/usr/bin/env python3
"""
SuperAgent — Agente de análisis de phishing sin SharePoint
Monitorea archivos .txt en ingress/ (depositados automáticamente)
Realiza análisis completo con KNN + Ollama/LLM
Registra alertas en IRIS 2.5.0 y notifica al reporter por SMTP

Flujo:
  1. FileSystemWatcher detecta nuevos .txt en ingress/
  2. KNN clasifica rápidamente con features del header
  3. Si confianza < umbral → Ollama para análisis profundo
  4. Según clasificación:
     - legitimo    → mueve a processed/legitimo/, notifica reporter
     - spam        → mueve a processed/spam/, notifica reporter
     - sospechoso  → registra alerta en IRIS, mueve a processed/sospechoso/, notifica reporter
  5. Logging estructurado de todas las acciones
"""

import os
import sys
import time
import json
import shutil
import signal
import logging
import logging.handlers
import threading
import queue
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from smtplib import SMTP, SMTP_SSL
from email.message import EmailMessage

# Importar módulos locales
from phishingAnalizer import PhishingAnalyzerTXT, EmailAnalysis
from knn_classifier import KNNClassifier, extract_features, features_to_vector, FEATURE_NAMES
from llm_validation import LLMValidator
from data_quality import DataQualityController
from usage_stats import UsageStats


# ============================================================================
# Filtro de encoding para logs
# ============================================================================

class CP1252SafeFilter(logging.Filter):
    """Filtra y sanitiza mensajes de log para que sean cp1252-compatibles."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Sanitiza el mensaje del log para remover caracteres no-cp1252."""
        try:
            # Obtener el mensaje completo con argumentos interpolados
            msg = record.getMessage()
            
            # Remover emojis y caracteres Unicode problemáticos AGRESIVAMENTE
            sanitized = self._sanitize_message(msg)
            
            # Reemplazar el mensaje sanitizado
            record.msg = sanitized
            record.args = ()  # Limpiamos args para evitar interpolación doble
            
            # EXTRA: Codificar el mensaje final para asegurar cp1252 compatibility
            try:
                sanitized.encode('cp1252')
            except UnicodeEncodeError:
                # Si aún hay problemas, hacer una limpieza final
                record.msg = sanitized.encode('cp1252', errors='replace').decode('cp1252')
            
            return True
        except Exception as e:
            # Si algo falla, registrar el error de forma segura
            record.msg = f"[ENCODING ERROR] {str(type(e).__name__)}: {str(e)[:100]}"
            record.args = ()
            return True
    
    @staticmethod
    def _sanitize_message(msg: str) -> str:
        """Remueve agresivamente emojis y caracteres no-cp1252."""
        if not msg:
            return msg
        
        # PASO 1: Remover TODOS los emojis (rangos Unicode altos)
        # Todos los emojis estándar
        msg = re.sub(r'[\U0001F000-\U0001F9FF]', '', msg)  # Rango principal de emojis
        msg = re.sub(r'[\U0001F600-\U0001F64F]', '', msg)  # Emoticones
        msg = re.sub(r'[\U0001F900-\U0001F9FF]', '', msg)  # Emojis suplementarios
        msg = re.sub(r'[\U0001F300-\U0001F5FF]', '', msg)  # Símbolos y pictogramas
        msg = re.sub(r'[\U0001F680-\U0001F6FF]', '', msg)  # Transporte
        msg = re.sub(r'[\U0001F700-\U0001F77F]', '', msg)  # Alquimia
        msg = re.sub(r'[\U0001F780-\U0001F7FF]', '', msg)  # Caracteres geométricos
        
        # PASO 2: Remover símbolos Unicode problemáticos
        msg = re.sub(r'[\u2600-\u27BF]', '', msg)  # Símbolos varios (incluye flechas)
        msg = re.sub(r'[\u2300-\u243F]', '', msg)  # Caracteres misceláneos
        msg = re.sub(r'[\u2190-\u21FF]', '', msg)  # Flechas (incluye →)
        msg = re.sub(r'[\u2700-\u27BF]', '', msg)  # Dingbats
        msg = re.sub(r'[\u2000-\u206F]', '', msg)  # Espacio general de puntuación
        
        # PASO 3: Remover caracteres de controles Unicode
        msg = re.sub(r'[\u0080-\u009F]', '', msg)  # Control characters
        
        # PASO 4: Reemplazar caracteres especiales problemáticos
        msg = msg.replace('→', '->').replace('←', '<-')
        msg = msg.replace('✓', '[OK]').replace('✗', '[FAIL]')
        msg = msg.replace('─', '-').replace('━', '=').replace('═', '=')
        
        # PASO 5: Codificar a cp1252 y redecodificar para remover caracteres incompatibles
        try:
            # Esto removerá/reemplazará cualquier carácter que no sea cp1252-encodable
            msg = msg.encode('cp1252', errors='replace').decode('cp1252')
        except:
            # Si todo falla, al menos intentar ISO-8859-1
            try:
                msg = msg.encode('iso-8859-1', errors='replace').decode('iso-8859-1')
            except:
                pass
        
        return msg


# ============================================================================
# Logger global
# ============================================================================

def setup_logger(log_level: str = "INFO", log_dir: str = "logs") -> logging.Logger:
    """Configura logger con salida a consola y archivo rotativo."""
    logger = logging.getLogger("superagent")
    
    # Evitar agregar handlers múltiples
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )
    
    # Crear el filtro CP1252-safe (aplicable a todos los handlers)
    safe_filter = CP1252SafeFilter()
    
    # Consola
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    ch.addFilter(safe_filter)
    logger.addHandler(ch)
    
    # Archivo rotativo
    try:
        Path(log_dir).mkdir(exist_ok=True, parents=True)
        fh = logging.handlers.RotatingFileHandler(
            Path(log_dir) / "superagent.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="cp1252",
            errors="replace"
        )
        fh.setFormatter(fmt)
        fh.addFilter(safe_filter)
        logger.addHandler(fh)
    except PermissionError as e:
        print(f"[WARNING] No se puede escribir a {log_dir}/superagent.log: {e}")
        print(f"[WARNING] Usando solo logging a consola")
    except Exception as e:
        print(f"[WARNING] Error configurando archivo de log: {e}")
        print(f"[WARNING] Usando solo logging a consola")
    
    return logger


log = logging.getLogger("superagent.main")


# ============================================================================
# Funciones auxiliares de sanitización
# ============================================================================

def sanitize_for_cp1252(text: str) -> str:
    """Sanitiza un string para que sea encodable a cp1252 (Windows production)."""
    if not text:
        return text
    
    # Remover emojis y caracteres Unicode problemáticos
    text = re.sub(r'[\U0001F000-\U0001F9FF]', '', text)  # Emojis principales
    text = re.sub(r'[\u2600-\u27BF]', '', text)  # Símbolos varios
    text = re.sub(r'[\u2300-\u243F]', '', text)  # Caracteres misceláneos
    text = re.sub(r'[\u2190-\u21FF]', '', text)  # Flechas
    
    # Codificar a cp1252 removiendo caracteres no-compatibles
    text = text.encode('cp1252', errors='replace').decode('cp1252')
    
    return text


# ============================================================================
# Configuración
# ============================================================================

def load_config(config_path: str = "config.json") -> Dict:
    """Carga configuración desde JSON y valida campos requeridos."""
    if not os.path.exists(config_path):
        log.error(f"config.json no encontrado en {config_path}")
        raise FileNotFoundError(f"Configuración no encontrada: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    # Validar campos requeridos
    required_fields = ["ingress_dir", "processed_dir", "analysis_dir"]
    for field in required_fields:
        if field not in config or not config[field]:
            raise KeyError(f"Campo requerido faltante en config.json: {field}")
    
    log.info(f"Configuración cargada desde {config_path}")
    return config


# ============================================================================
# SuperAgent
# ============================================================================

class SuperAgent2:
    """
    Agente de análisis de phishing sin dependencia de SharePoint.
    Monitorea carpeta ingress/ para archivos .txt depositados automáticamente.
    Realiza análisis completo y toma acciones post-análisis.
    """
    
    @staticmethod
    def extract_email_from_address(address: str) -> str:
        """Extrae email de una dirección que puede tener múltiples formatos:
        - 'Name <email@example.com>' (RFC 5322)
        - 'SMTP:email@example.com' (X.500 Exchange)
        - '/O=ORG/OU=UNIT/.../SMTP:email@example.com' (LDAP DN)
        - 'email@example.com' (simple)
        - 'Name email@example.com' (separados)
        """
        import html
        import re
        
        if not address or not isinstance(address, str):
            return "unknown@exchange.local"
        
        address = address.strip()
        
        # Decodificar entidades HTML (&lt; &gt; etc.)
        address = html.unescape(address)
        
        # Caso 1: Formato X.500 con SMTP - buscar SMTP: o smtp:
        # Patrón: "... SMTP:email@example.com" o "SMTP:email@example.com"
        smtp_match = re.search(r'[Ss][Mm][Tt][Pp]:([^/\s,;]+@[^/\s,;]+)', address)
        if smtp_match:
            email = smtp_match.group(1).strip()
            if email and '@' in email:
                return email
        
        # Caso 2: Formato "Name <email@example.com>"
        if '<' in address and '>' in address:
            email = address[address.find('<')+1:address.find('>')].strip()
            if email and '@' in email:
                return email
        
        # Caso 3: Búsqueda simple de email (contiene @)
        # Extraer parte con @ y evitar caracteres inválidos
        email_match = re.search(r'([a-zA-Z0-9._%-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', address)
        if email_match:
            return email_match.group(1).strip()
        
        # Caso 4: No se encontró email válido
        # Devolver "unknown" + dominio si está disponible o fallback genérico
        if address and not address.startswith('/O='):
            # Si no es LDAP DN, devolver lo que sea (podría ser un nombre)
            return "unknown@exchange.local"
        
        return "unknown@exchange.local"
    
    def _print_monthly_stats(self):
        """Imprime estadísticas mensuales en los logs."""
        summary = self.stats.stats_summary()
        month_data = summary["mes_actual"]
        
        if month_data["total"] > 0:
            log.info("[STATS] Estadísticas del mes actual:")
            log.info(f"  Total procesados: {month_data['total']}")
            log.info(f"  - Legítimos: {month_data['by_classification'].get('legitimo', 0)}")
            log.info(f"  - Spam: {month_data['by_classification'].get('spam', 0)}")
            log.info(f"  - Sospechosos: {month_data['by_classification'].get('sospechoso', 0)}")
            log.info(f"  Decisiones por: WL:{month_data['by_source'].get('whitelist', 0)} KNN:{month_data['by_source'].get('knn', 0)} LLM:{month_data['by_source'].get('llm', 0)}")

    
    def __init__(self, config_path: str = "config.json"):
        self.config = load_config(config_path)
        setup_logger(
            self.config.get("log_level", "INFO"),
            self.config.get("log_dir", "logs")
        )
        
        # Rutas (requeridas en config.json)
        self.ingress_dir = Path(self.config["ingress_dir"]).resolve()
        self.processed_dir = Path(self.config["processed_dir"]).resolve()
        self.analysis_dir = Path(self.config["analysis_dir"]).resolve()
        
        # Crear estructura
        for sub in ("legitimo", "spam", "sospechoso", "campana"):
            (self.processed_dir / sub).mkdir(parents=True, exist_ok=True)
        self.ingress_dir.mkdir(parents=True, exist_ok=True)
        self.analysis_dir.mkdir(parents=True, exist_ok=True)
        
        # Componentes
        self.knn = KNNClassifier(
            k=5,
            confidence_threshold=float(self.config.get("knn_confidence_threshold", 0.85))
        )
        self.analyzer = PhishingAnalyzerTXT(config_path)
        self.stats = UsageStats()  # Estadísticas de uso
        
        # Cola thread-safe
        self.file_queue: queue.Queue = queue.Queue()
        
        # Control
        self._running = False
        self._stop_evt = threading.Event()
        
        log.info("=" * 70)
        log.info("SuperAgent inicializado")
        log.info(f"  Ingress:       {self.ingress_dir}")
        log.info(f"  Processed:     {self.processed_dir}")
        log.info(f"  Analysis:      {self.analysis_dir}")
        log.info(f"  KNN threshold: {self.config.get('knn_confidence_threshold', 0.85) * 100:.0f}%")
        log.info(f"  LLM provider:  {self.config.get('llm_provider', 'ollama')}")
        log.info(f"  Log level:     {self.config.get('log_level', 'INFO')}")
        log.info("=" * 70)
        
        # Mejoras etapa 1: Validadores
        self.llm_validator = LLMValidator(self.config)
        self.quality_controller = DataQualityController(self.config)
        log.info("[OK] Validadores cargados: LLM + Data Quality")
        
        # Recarga automática de whitelist
        whitelist_path = self.config.get("whitelist_path", "whitelist.txt")
        self.whitelist_path = Path(whitelist_path)
        self.whitelist_mtime = 0
        if self.whitelist_path.exists():
            self.whitelist_mtime = self.whitelist_path.stat().st_mtime
            log.info(f"[OK] Monitoreo de whitelist activado: {self.whitelist_path}")
        
        # Recarga automática de spam_domains
        spam_domains_path = self.config.get("spam_domains_path", "spam_domains.txt")
        self.spam_domains_path = Path(spam_domains_path)
        self.spam_domains_mtime = 0
        if self.spam_domains_path.exists():
            self.spam_domains_mtime = self.spam_domains_path.stat().st_mtime
            log.info(f"[OK] Monitoreo de spam_domains activado: {self.spam_domains_path}")
        
        # Recarga automática de campaign_senders (simulacros de Phishing)
        campaign_senders_path = self.config.get("campaign_senders_path", "campaign_senders.txt")
        self.campaign_senders_path = Path(campaign_senders_path)
        self.campaign_senders_mtime = 0
        if self.campaign_senders_path.exists():
            self.campaign_senders_mtime = self.campaign_senders_path.stat().st_mtime
            log.info(f"[OK] Monitoreo de campaign_senders activado: {self.campaign_senders_path}")
        
        # Estado del reporte mensual (evita reenvíos duplicados el mismo día)
        self.monthly_report_state_path = Path(__file__).resolve().parent / "monthly_report_state.json"
        self._monthly_report_last_sent = self._load_monthly_report_state()
        
        # Mostrar estadísticas mensuales iniciales
        self._print_monthly_stats()
    
    # ========================================================================
    # Ciclo principal
    # ========================================================================
    
    def start(self):
        """Inicia el agente."""
        self._running = True
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        # Hilo de FileWatcher
        watcher_thread = threading.Thread(
            target=self._file_watcher_loop,
            daemon=True,
            name="file-watcher"
        )
        watcher_thread.start()
        
        # Hilo de Worker
        worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="analysis-worker"
        )
        worker_thread.start()
        
        log.info("SuperAgent iniciado. Observando ingress/...")
        
        # Loop principal
        while self._running:
            try:
                self._stop_evt.wait(timeout=1)
            except Exception as exc:
                # Sanitizar la excepción ANTES de loguearla
                exc_str = str(exc).encode('cp1252', errors='replace').decode('cp1252')
                log.error(f"Error en loop principal: {exc_str}")
        
        log.info("SuperAgent detenido.")
    
    def _handle_shutdown(self, signum, frame):
        """Maneja señal de shutdown."""
        log.info(f"Señal de shutdown recibida ({signum}). Deteniendo...")
        self._running = False
        self._stop_evt.set()
    
    # ========================================================================
    # FileWatcher
    # ========================================================================
    
    def _check_and_reload_whitelist(self):
        """Verifica si whitelist.txt cambió y lo recarga si es necesario."""
        if not self.whitelist_path.exists():
            return
        
        try:
            current_mtime = self.whitelist_path.stat().st_mtime
            
            # Si el archivo fue modificado
            if current_mtime > self.whitelist_mtime:
                log.info(f"[WATCH] Whitelist actualizado detectado. Recargando...")
                
                # Recargar whitelist en el analyzer
                self.analyzer.whitelist = self.analyzer._load_whitelist()
                
                self.whitelist_mtime = current_mtime
                log.info(f"[OK] Whitelist recargado exitosamente ({len(self.analyzer.whitelist)} dominios)")
        
        except Exception as exc:
            exc_str = str(exc).encode('cp1252', errors='replace').decode('cp1252')
            log.error(f"Error recargando whitelist: {exc_str}")

    def _check_and_reload_spam_domains(self):
        """Verifica si spam_domains.txt cambió y lo recarga si es necesario."""
        if not self.spam_domains_path.exists():
            return
        
        try:
            current_mtime = self.spam_domains_path.stat().st_mtime
            
            # Si el archivo fue modificado
            if current_mtime > self.spam_domains_mtime:
                log.info(f"[WATCH] Spam domains actualizado detectado. Recargando...")
                
                # Recargar spam_domains en el analyzer
                self.analyzer.spam_domains = self.analyzer._load_spam_domains()
                
                self.spam_domains_mtime = current_mtime
                log.info(f"[OK] Spam domains recargado exitosamente ({len(self.analyzer.spam_domains)} dominios)")
        
        except Exception as exc:
            exc_str = str(exc).encode('cp1252', errors='replace').decode('cp1252')
            log.error(f"Error recargando spam_domains: {exc_str}")
    
    def _check_and_reload_campaign_senders(self):
        """Verifica si campaign_senders.txt cambió y lo recarga si es necesario."""
        if not self.campaign_senders_path.exists():
            return
        
        try:
            current_mtime = self.campaign_senders_path.stat().st_mtime
            
            # Si el archivo fue modificado
            if current_mtime > self.campaign_senders_mtime:
                log.info(f"[WATCH] Campaign senders actualizado detectado. Recargando...")
                
                # Recargar campaign_senders en el analyzer
                self.analyzer.campaign_senders = self.analyzer._load_campaign_senders()
                
                self.campaign_senders_mtime = current_mtime
                log.info(f"[OK] Campaign senders recargado exitosamente ({len(self.analyzer.campaign_senders)} entradas)")
        
        except Exception as exc:
            exc_str = str(exc).encode('cp1252', errors='replace').decode('cp1252')
            log.error(f"Error recargando campaign_senders: {exc_str}")
    
    def _file_watcher_loop(self):
        """Monitorea ingress/ buscando nuevos .txt."""
        seen = set()
        log.info(f"FileWatcher iniciado en: {self.ingress_dir}")
        
        while self._running:
            try:
                # Verificar y recargar whitelist si cambió
                self._check_and_reload_whitelist()
                
                # Verificar y recargar spam_domains si cambió
                self._check_and_reload_spam_domains()
                
                # Verificar y recargar campaign_senders si cambió
                self._check_and_reload_campaign_senders()
                
                # Verificar si corresponde enviar el reporte mensual (día 1 de cada mes)
                self._check_and_send_monthly_report()
                
                current = {p for p in self.ingress_dir.glob("*.txt") if p.is_file()}
                new_files = current - seen
                
                for path in sorted(new_files):
                    log.info(f"FileWatcher: nuevo archivo detectado: {path.name}")
                    self.file_queue.put(path)
                    seen.add(path)
                
                seen = seen & current
                
            except Exception as exc:
                exc_str = str(exc).encode('cp1252', errors='replace').decode('cp1252')
                log.error(f"Error en FileWatcher: {exc_str}")
            
            time.sleep(5)
    
    # ========================================================================
    # Worker
    # ========================================================================
    
    def _worker_loop(self):
        """Procesa archivos de la cola."""
        log.info("Worker de análisis iniciado.")
        
        while self._running:
            try:
                path = self.file_queue.get(timeout=2)
                if path is None:
                    break
                self._process_file(path)
                self.file_queue.task_done()
            except queue.Empty:
                continue
            except Exception as exc:
                # Sanitizar la excepción ANTES de loguearla
                exc_str = str(exc).encode('cp1252', errors='replace').decode('cp1252')
                log.error(f"Error en worker: {exc_str}")
    
    # ========================================================================
    # Procesamiento de archivo
    # ========================================================================
    
    def _process_file(self, file_path: Path):
        """Procesa un archivo: parseo, clasificación, acciones."""
        log.info("=" * 70)
        log.info(f"Procesando: {file_path.name}")
        
        if not file_path.exists():
            log.warning(f"Archivo no encontrado: {file_path}")
            return
        
        # 1. Parsear
        parsed = self.analyzer.parse_txt_file(str(file_path))
        if not parsed:
            log.error(f"No se pudo parsear: {file_path.name}")
            self._move_to_processed(file_path, "spam")
            return
        
        # DEBUG: Verificar headers extraídos
        headers = parsed["headers"]
        log.info(f"  [HEADERS] Extraídos: {len(headers)} cabeceras")
        to_raw = headers.get("To", "")
        from_raw = headers.get("From", "")
        log.info(f"  [RAW To] '{to_raw}'")
        log.info(f"  [RAW From] '{from_raw}'")
        
        # Extraer emails limpiando formatos X.500, HTML entities, etc.
        from_email = self.extract_email_from_address(headers.get("From", ""))
        to_email = self.extract_email_from_address(headers.get("To", ""))
        
        log.info(f"  [EXTRACT To] '{to_email}'")
        log.info(f"  [EXTRACT From] '{from_email}'")
        log.info(f"  De: {from_email}")
        log.info(f"  Para (reporter): {to_email}")
        
        microsoft_urls = parsed["microsoft_urls"]
        content = parsed["raw_content"]
        
        # ✨ MEJORA ETAPA 1: Guardar datos para validación (sanitizados)
        self.last_email_headers = {k: sanitize_for_cp1252(str(v)) for k, v in headers.items()}
        self.last_email_content = sanitize_for_cp1252(content)
        self.current_file_path = file_path
        
        if not to_email:
            log.warning(f"No se encontró email del reporter en header 'To:' de {file_path.name}")
            self._move_to_processed(file_path, "spam")
            return
        
        # 2. Campaign check — simulacro de Phishing, máxima prioridad (no genera alertas en IRIS)
        if self.analyzer.check_campaign_sender(from_email):
            log.info(f"Campaign match: {from_email} [SIMULACRO DE PHISHING]")
            analysis = self._build_campaign_analysis(file_path, parsed, from_email, to_email)
            self._handle_result(file_path, analysis, classification_source="campaign")
            return
        
        # 3. Whitelist check
        if self.analyzer.check_whitelist(from_email):
            log.info(f"Whitelist match: {from_email} [LEGIT]")
            analysis = self.analyzer.analyze_txt_file(str(file_path))
            # Registrar estadística: whitelist
            self.stats.record_case("legitimo", "whitelist")
            self._handle_result(file_path, analysis)
            return
        
        # 4. KNN rápido
        knn_result = self.knn.classify_email(headers, content, microsoft_urls)
        
        if knn_result["is_confident"]:
            log.info(
                f"KNN directo ({knn_result['confidence'] * 100:.0f}% confianza) - "
                f"{knn_result['classification'].upper()}"
            )
            analysis = self._build_analysis_from_knn(file_path, parsed, knn_result)
            classification_source = "knn"
        else:
            log.info(
                f"KNN inseguro ({knn_result['confidence'] * 100:.0f}%) - "
                f"escalando a análisis profundo..."
            )
            analysis = self.analyzer.analyze_txt_file(str(file_path))
            if analysis:
                # Sobrescribir reporter_email con el del header "To:" para consistencia
                analysis.reporter_email = to_email
                analysis.reasons = [
                    f"KNN: {knn_result['classification']} ({knn_result['confidence']:.0%}) "
                    f"-> LLM refinement"
                ] + analysis.reasons
            classification_source = "llm"
        
        self._handle_result(file_path, analysis, knn_result, classification_source)
    
    def _build_analysis_from_knn(
        self, file_path: Path, parsed: Dict, knn_result: Dict
    ) -> EmailAnalysis:
        """Construye EmailAnalysis desde KNN sin Ollama."""
        headers = parsed["headers"]
        content = parsed["raw_content"]
        microsoft_urls = parsed["microsoft_urls"]
        
        auth = self.analyzer.check_authentication(headers)
        urls = self.analyzer.extract_urls_from_content(content)
        sender_ip = self.analyzer.extract_sender_ip(headers)
        ip_rep = self.analyzer.check_ip_reputation(sender_ip)
        homograph = self.analyzer.check_homograph_spoofing(headers.get("From", ""))
        reasons = self.analyzer.check_suspicious_patterns(headers, content)
        risk_score = self.analyzer.calculate_risk_score(
            auth, reasons, urls, microsoft_urls, ip_rep, homograph
        )
        
        active_features = [
            FEATURE_NAMES[i] for i, v in enumerate(knn_result["vector"]) if v > 0
        ]
        
        return EmailAnalysis(
            mensaje_id=sanitize_for_cp1252(headers.get("Message-ID", file_path.stem)),
            classification=knn_result["classification"],
            confidence=knn_result["confidence"],
            reporter_email=self.extract_email_from_address(headers.get("To", "")),
            original_subject=sanitize_for_cp1252(headers.get("Subject", "N/A")),
            original_from=sanitize_for_cp1252(self.extract_email_from_address(headers.get("From", ""))),
            reply_to=sanitize_for_cp1252(self.analyzer.extract_reply_to(headers) or ""),
            sender_ip=sender_ip,
            ip_reputation=ip_rep,
            analysis_date=datetime.now().isoformat(),
            indicators=auth,
            headers_raw=sanitize_for_cp1252(str(headers)),
            body_preview=sanitize_for_cp1252(content[:500]),
            urls_found=urls[:10],
            microsoft_url_check=microsoft_urls,
            risk_score=risk_score,
            reasons=reasons + [
                f"KNN features activas: {', '.join(active_features[:8])}"
            ]
        )
    
    def _build_campaign_analysis(
        self, file_path: Path, parsed: Dict, from_email: str, to_email: str
    ) -> EmailAnalysis:
        """Construye EmailAnalysis para un remitente identificado como campaña de simulacro de Phishing."""
        headers = parsed["headers"]
        content = parsed["raw_content"]
        microsoft_urls = parsed["microsoft_urls"]
        
        return EmailAnalysis(
            mensaje_id=sanitize_for_cp1252(headers.get("Message-ID", file_path.stem)),
            classification="campana",
            confidence=1.0,
            reporter_email=to_email,
            original_subject=sanitize_for_cp1252(headers.get("Subject", "N/A")),
            original_from=sanitize_for_cp1252(from_email),
            reply_to=sanitize_for_cp1252(self.analyzer.extract_reply_to(headers) or ""),
            sender_ip=self.analyzer.extract_sender_ip(headers),
            ip_reputation={},
            analysis_date=datetime.now().isoformat(),
            indicators=self.analyzer.check_authentication(headers),
            headers_raw=sanitize_for_cp1252(str(headers)),
            body_preview=sanitize_for_cp1252(content[:500]),
            urls_found=[],
            microsoft_url_check=microsoft_urls,
            risk_score=0,
            reasons=["Remitente identificado en campaign_senders.txt — simulacro de Phishing"]
        )
    
    # ========================================================================
    # Acciones post-análisis
    # ========================================================================
    
    def _handle_result(self, file_path: Path, analysis: Optional[EmailAnalysis], knn_result: Optional[Dict] = None, classification_source: str = "llm"):
        """Ejecuta acciones según clasificación y actualiza aprendizaje del modelo."""
        if not analysis:
            log.error(f"Análisis nulo para: {file_path.name}")
            self._move_to_processed(file_path, "spam")
            # Registrar como error (asumimos spam)
            self.stats.record_case("spam", classification_source)
            return
        
        classification = analysis.classification
        log.info(
            f"RESULTADO: {classification.upper()} | Score: {analysis.risk_score}/100 | "
            f"Confianza: {analysis.confidence * 100:.0f}%"
        )
        
        # Guardar JSON del análisis
        self.analyzer.save_analysis(analysis)
        
        # Determinar si KNN acertó (para tracking de precisión)
        knn_was_correct = None
        if knn_result:
            knn_predicted = knn_result["classification"]
            knn_was_correct = (knn_predicted == classification)
            
            if not knn_was_correct:
                log.warning(
                    f"KNN feedback: predijo '{knn_predicted}' pero análisis final es '{classification}'"
                )
                self.knn.record_feedback(knn_predicted, classification)
        
        # Registrar estadística (incluir feedback si fue KNN)
        self.stats.record_case(classification, classification_source, knn_was_correct if classification_source == "knn" else None)
        
        # ✨ MEJORA ETAPA 1: Validación LLM antes de actuar
        if classification_source == "llm":
            llm_result = {
                "classification": classification,
                "confidence": analysis.confidence,
                "risk_score": analysis.risk_score,
                "reasons": analysis.reasons
            }
            validation = self.llm_validator.validate(
                self.last_email_headers,
                self.last_email_content,
                llm_result,
                knn_result,
                analysis.risk_score
            )
            
            log.info(f"Validación LLM: {validation['recommendation']} (confianza: {validation['confidence']:.0%})")
            
            if validation["recommendation"] == "REVIEW":
                log.warning(f"[REVIEW] Email para revisión manual: {', '.join(validation['flags'])}")
                self.llm_validator.save_for_review(
                    file_path, validation, 
                    {"headers": self.last_email_headers},
                    llm_result
                )
                # Marcar en análisis
                analysis.validation_flags = validation["flags"]
        
        if classification == "sospechoso":
            log.info("[IRIS] Registrando alerta en IRIS...")
            self._register_alert_in_iris(analysis)
            self._notify_reporter(analysis, "sospechoso")
            self._update_knn(analysis, knn_result)
        
        elif classification == "spam":
            log.info("[SPAM] Email clasificado como SPAM")
            self._notify_reporter(analysis, "spam")
            self._update_knn(analysis, knn_result)
        
        elif classification == "campana":
            log.info("[CAMPAÑA] Email identificado como simulacro de Phishing — sin alerta en IRIS")
            self._notify_reporter(analysis, "campana")
        
        elif classification == "legitimo":
            log.info("[LEGIT] Email clasificado como LEGÍTIMO")
            self._notify_reporter(analysis, "legitimo")
        
        self._move_to_processed(file_path, classification)
    
    def _register_alert_in_iris(self, analysis: EmailAnalysis):
        """Registra alerta en IRIS usando endpoint /alerts/add (en thread separado)."""
        iris_cfg = self.config.get("iris_dfir", {})
        url = iris_cfg.get("url", "")
        api_key = iris_cfg.get("api_key", "")
        customer_id = iris_cfg.get("default_customer_id", 1)
        
        if not url or not api_key:
            log.warning("IRIS DFIR no configurado correctamente - alerta NO registrada")
            return
        
        # Ejecutar en thread separado para no bloquear
        thread = threading.Thread(
            target=self._iris_post_worker,
            args=(url, api_key, customer_id, analysis),
            daemon=True,
            name=f"iris-{analysis.mensaje_id[:8]}"
        )
        thread.start()
    
    def _iris_post_worker(self, url: str, api_key: str, customer_id: int, analysis: EmailAnalysis):
        """Worker thread que envía alertas a IRIS con reintentos."""
        import requests
        from datetime import datetime
        import json
        
        iris_cfg = self.config.get("iris_dfir", {})
        max_retries = 3
        retry_delay = 2  # segundos
        
        # FUNCIÓN: Sanitizar strings para IRIS (remover caracteres especiales)
        def sanitize_for_iris(text: str) -> str:
            """Limpia texto para IRIS: ASCII-only, sin caracteres especiales problemáticos."""
            if not isinstance(text, str):
                text = str(text)
            
            # Convertir a ASCII, removiendo acentos y caracteres especiales
            text = unicodedata.normalize('NFKD', text)
            text = text.encode('ascii', 'ignore').decode('ascii')
            
            # Remover comillas problemáticas y saltos de línea
            text = text.replace('"', "'").replace('\n', ' ').replace('\r', ' ')
            
            return text.strip()
        
        # Estructura de alertas compatible con IRIS 2.5.0
        # alert_source_content es un OBJETO JSON, no un string
        data = {
            "alert_title": sanitize_for_iris("AIPA - Posible Phishing"),
            "alert_severity_id": 1,
            "alert_status_id": 3,
            "alert_customer_id": customer_id,  # ← REQUERIDO: customer_id=1 (CSIRT - SOC)
            "alert_source_event_time": sanitize_for_iris(analysis.analysis_date or datetime.utcnow().isoformat() + "Z"),
            "alert_source_link": sanitize_for_iris(iris_cfg.get("source_link_template", "").format(msg_id=analysis.mensaje_id)),
            # alert_source_content es un OBJETO JSON anidado (no string)
            "alert_source_content": {
                "id": sanitize_for_iris(analysis.mensaje_id),
                "remitente": sanitize_for_iris(analysis.original_from),
                "asunto": sanitize_for_iris(analysis.original_subject),
                "reportero": sanitize_for_iris(analysis.reporter_email),
                "clasificacion": sanitize_for_iris(analysis.classification),
                "risk_score": analysis.risk_score,
                "confianza": f"{analysis.confidence:.0%}",
                "ip_origen": sanitize_for_iris(analysis.sender_ip or "N/A"),
                "spf": sanitize_for_iris(analysis.indicators.get("spf", "unknown")),
                "dkim": sanitize_for_iris(analysis.indicators.get("dkim", "unknown")),
                "dmarc": sanitize_for_iris(analysis.indicators.get("dmarc", "unknown")),
            }
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        log.info(f"[IRIS-QUEUE] Alerta encolada para IRIS: {analysis.mensaje_id}")
        
        for attempt in range(1, max_retries + 1):
            try:
                log.debug(f"[IRIS] Intento {attempt}/{max_retries} para {analysis.mensaje_id}")
                
                # TIMEOUT AUMENTADO A 30 SEGUNDOS (IRIS puede ser lento)
                response = requests.post(
                    url, 
                    json=data, 
                    headers=headers, 
                    timeout=30,  # ← 30 SEGUNDOS
                    verify=False  # SSL auto-firmado
                )
                
                if response.status_code in (200, 201):
                    try:
                        response_json = response.json()
                        alert_id = response_json.get("data", {}).get("alert_id") or response_json.get("alert_id")
                        if alert_id:
                            log.info(f"[OK] IRIS: Alert ID {alert_id} | Msg: {analysis.mensaje_id}")
                        else:
                            log.info(f"[OK] IRIS: HTTP {response.status_code} | Msg: {analysis.mensaje_id}")
                    except (ValueError, KeyError):
                        log.info(f"[OK] IRIS: HTTP {response.status_code} | Msg: {analysis.mensaje_id}")
                    return  # Éxito - salir
                
                else:
                    error_detail = response.text[:200] if response.text else "Sin detalles"
                    log.warning(f"[IRIS] HTTP {response.status_code}: {error_detail} (intento {attempt}/{max_retries})")
                    
                    if attempt < max_retries:
                        time.sleep(retry_delay)
                    else:
                        log.error(f"[ERROR] IRIS: HTTP {response.status_code} después de {max_retries} intentos | Msg: {analysis.mensaje_id}")
            
            except requests.exceptions.Timeout:
                log.warning(f"[IRIS] TIMEOUT en intento {attempt}/{max_retries}")
                if attempt < max_retries:
                    time.sleep(retry_delay)
                else:
                    log.error(f"[ERROR] IRIS: TIMEOUT después de {max_retries} intentos | Msg: {analysis.mensaje_id}")
            
            except requests.exceptions.ConnectionError as exc:
                exc_str = str(exc).encode('cp1252', errors='replace').decode('cp1252')
                log.warning(f"[IRIS] CONEXIÓN ERROR en intento {attempt}/{max_retries}: {exc_str[:100]}")
                if attempt < max_retries:
                    time.sleep(retry_delay)
                else:
                    log.error(f"[ERROR] IRIS: No se puede conectar después de {max_retries} intentos | {url}")
            
            except Exception as exc:
                exc_str = str(exc).encode('cp1252', errors='replace').decode('cp1252')
                log.error(f"[ERROR] IRIS: {type(exc).__name__}: {exc_str} | Msg: {analysis.mensaje_id}")
    
    def _notify_reporter(self, analysis: EmailAnalysis, classification: str):
        """Envía notificación por email al reporter (persona que reportó el email)."""
        smtp_cfg = self.config.get("smtp", {})
        to_addr = analysis.reporter_email
        
        if not to_addr:
            log.warning("No se encontró email del reporter para notificar")
            return
        
        if not smtp_cfg.get("host"):
            log.warning("SMTP no configurado — notificación omitida")
            return
        
        log.info(f"Enviando notificación a reporter: {to_addr}")
        
        # Mensajes según clasificación
        messages = {
            "legitimo": (
                f"[LEGÍTIMO] El email que reportaste fue revisado y clasificado como LEGÍTIMO.\n"
                f"Remitente: {analysis.original_from}\n"
                f"Asunto: {analysis.original_subject}\n"
                f"No se requiere ninguna acción adicional."
            ),
            "spam": (
                f"[SPAM] El email fue clasificado como SPAM.\n"
                f"Remitente: {analysis.original_from}\n"
                f"Asunto: {analysis.original_subject}\n"
                f"Ha sido registrado para mejorar los filtros. No hay riesgo de seguridad."
            ),
            "sospechoso": (
                f"[ALERTA] El email fue identificado como SOSPECHOSO / PHISHING.\n"
                f"Remitente: {analysis.original_from}\n"
                f"Asunto: {analysis.original_subject}\n"
                f"Score de riesgo: {analysis.risk_score}/100\n"
                f"Nuestro equipo de seguridad ya fue notificado. "
                f"POR FAVOR NO hagas clic en enlaces ni descargues archivos de ese email."
            ),
            "campana": self.config.get(
                "campaign_reply_message",
                "El email que reportaste era un simulacro de Phishing. Gracias por reportarlo!!"
            ),
        }
        
        msg = EmailMessage()
        msg["Subject"] = f"[SuperAgent] Resultado de análisis: {classification.upper()}"
        msg["From"] = smtp_cfg.get("from", "noreply@example.com")
        msg["To"] = to_addr
        msg.set_content(messages.get(classification, "Tu reporte fue procesado."))
        
        try:
            if smtp_cfg.get("use_tls", False):
                # Usar TLS (starttls en puerto 587)
                with SMTP(smtp_cfg["host"], smtp_cfg["port"]) as smtp:
                    smtp.starttls()
                    smtp.send_message(msg)
            else:
                # SMTP simple sin encriptación (puerto 25)
                with SMTP(smtp_cfg["host"], smtp_cfg["port"]) as smtp:
                    smtp.send_message(msg)
            
            log.info(f"[OK] Notificación enviada a {to_addr} ({classification})")
        
        except Exception as exc:
            exc_str = str(exc).encode('cp1252', errors='replace').decode('cp1252')
            log.error(f"[ERROR] Error enviando email a {to_addr}: {exc_str}")
    
    def _move_to_processed(self, file_path: Path, classification: str):
        """Mueve archivo a processed/<clasificación>/."""
        dest_dir = self.processed_dir / classification
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_name = f"{ts}_{file_path.name}"
        dest_path = dest_dir / dest_name
        
        try:
            shutil.move(str(file_path), str(dest_path))
            log.info(f"Archivo movido: processed/{classification}/{dest_name}")
        except Exception as exc:
            exc_str = str(exc).encode('cp1252', errors='replace').decode('cp1252')
            log.error(f"No se pudo mover {file_path.name}: {exc_str}")
    
    # ========================================================================
    # Reporte mensual por email (día 1 de cada mes, estadísticas del mes anterior)
    # ========================================================================
    
    def _load_monthly_report_state(self) -> Optional[str]:
        """Carga la fecha (YYYY-MM-DD) del último envío del reporte mensual."""
        try:
            if self.monthly_report_state_path.exists():
                with open(self.monthly_report_state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("last_sent")
        except Exception as exc:
            log.error(f"Error cargando estado de reporte mensual: {exc}")
        return None
    
    def _save_monthly_report_state(self, date_str: str):
        """Persiste la fecha del último envío del reporte mensual."""
        try:
            with open(self.monthly_report_state_path, "w", encoding="utf-8") as f:
                json.dump({"last_sent": date_str}, f)
        except Exception as exc:
            log.error(f"Error guardando estado de reporte mensual: {exc}")
    
    def _check_and_send_monthly_report(self):
        """Si es día 1 del mes y no se envió hoy, envía por email el reporte del mes anterior."""
        now = datetime.now()
        if now.day != 1:
            return
        
        today_key = now.strftime("%Y-%m-%d")
        if self._monthly_report_last_sent == today_key:
            return
        
        report_cfg = self.config.get("monthly_report", {})
        if not report_cfg.get("enabled", True):
            return
        
        recipients = [r.strip() for r in report_cfg.get("recipients", "").split(",") if r.strip()]
        if not recipients:
            log.warning("Reporte mensual: no hay destinatarios configurados (monthly_report.recipients)")
            self._monthly_report_last_sent = today_key
            self._save_monthly_report_state(today_key)
            return
        
        # Mes anterior al actual
        last_month_date = now.replace(day=1) - timedelta(days=1)
        year = str(last_month_date.year)
        month = f"{last_month_date.month:02d}"
        
        self._send_monthly_report_email(year, month, recipients)
        
        self._monthly_report_last_sent = today_key
        self._save_monthly_report_state(today_key)
    
    def _send_monthly_report_email(self, year: str, month: str, recipients: List[str]):
        """Envía por email el resumen de estadísticas de un mes a la lista de destinatarios."""
        smtp_cfg = self.config.get("smtp", {})
        if not smtp_cfg.get("host"):
            log.warning("SMTP no configurado — reporte mensual omitido")
            return
        
        summary = self.stats.get_month_summary(year, month)
        month_name = datetime.strptime(month, "%m").strftime("%B")
        
        lines = [
            f"Reporte mensual de SuperAgent — {month_name} {year}",
            "=" * 50,
            f"Total de casos procesados: {summary['total']}",
            "",
            "Por clasificación:",
        ]
        for cls, count in summary["by_classification"].items():
            pct = summary["by_classification_pct"].get(cls, 0)
            lines.append(f"  - {cls}: {count} ({pct}%)")
        lines.append("")
        lines.append("Por fuente de decisión:")
        for src, count in summary["by_source"].items():
            pct = summary["by_source_pct"].get(src, 0)
            lines.append(f"  - {src}: {count} ({pct}%)")
        lines.append("")
        lines.append(f"Precisión KNN: {summary.get('knn_accuracy_pct', 0)}%")
        
        msg = EmailMessage()
        msg["Subject"] = f"[SuperAgent] Reporte mensual de estadísticas — {month_name} {year}"
        msg["From"] = smtp_cfg.get("from", "noreply@example.com")
        msg["To"] = ", ".join(recipients)
        msg.set_content("\n".join(lines))
        
        try:
            if smtp_cfg.get("use_tls", False):
                with SMTP(smtp_cfg["host"], smtp_cfg["port"]) as smtp:
                    smtp.starttls()
                    smtp.send_message(msg)
            else:
                with SMTP(smtp_cfg["host"], smtp_cfg["port"]) as smtp:
                    smtp.send_message(msg)
            
            log.info(f"[OK] Reporte mensual enviado a: {', '.join(recipients)}")
        
        except Exception as exc:
            exc_str = str(exc).encode('cp1252', errors='replace').decode('cp1252')
            log.error(f"[ERROR] Error enviando reporte mensual: {exc_str}")
    
    def _update_knn(self, analysis: EmailAnalysis, knn_result: Optional[Dict] = None):
        """
        Actualiza modelo KNN con nuevo ejemplo (aprendizaje activo).
        El modelo mejora con cada ejemplo y ajusta su umbral dinámicamente.
        """
        try:
            features = {
                "spf_fail": 1.0 if analysis.indicators.get("spf") in ("fail", "softfail") else 0.0,
                "dkim_none": 1.0 if analysis.indicators.get("dkim") in ("none", "fail") else 0.0,
                "dmarc_none": 1.0 if analysis.indicators.get("dmarc") in ("none", "fail") else 0.0,
                "auth_all_pass": 1.0 if (
                    analysis.indicators.get("spf") == "pass" and
                    analysis.indicators.get("dkim") == "pass" and
                    analysis.indicators.get("dmarc") == "pass"
                ) else 0.0,
                "ms_urls_detected": 1.0 if analysis.microsoft_url_check not in ("None", "") else 0.0,
                "has_attachment": 0.0,
                "url_count_norm": min(len(analysis.urls_found) / 10.0, 1.0),
            }
            vector = [features.get(n, 0.0) for n in FEATURE_NAMES]
            
            # Determinar si el feedback fue correcto
            # Si KNN tuvo confianza y acertó, es un buen ejemplo
            feedback_correct = True
            if knn_result:
                knn_predicted = knn_result["classification"]
                feedback_correct = (knn_predicted == analysis.classification)
            
            # ✨ MEJORA ETAPA 2: Validación data_quality antes de agregar
            quality_check = self.quality_controller.should_add_to_training(
                self.last_email_headers,
                analysis.classification,
                analysis.confidence,
                analysis.risk_score
            )
            
            if quality_check["action"] == "ADD":
                self.knn.add_training_example(vector, analysis.classification, feedback_correct)
                log.debug(f"[OK] Ejemplo agregado a entrenamiento KNN")
            elif quality_check["action"] == "QUARANTINE":
                log.warning(f"[QUARANTINE] Ejemplo en cuarentena: {', '.join(quality_check['issues'])}")
                self.quality_controller.quarantine_example(
                    str(self.current_file_path),
                    quality_check["issues"],
                    analysis.classification,
                    {"confidence": analysis.confidence, "risk_score": analysis.risk_score}
                )
            elif quality_check["action"] == "MANUAL_REVIEW":
                log.info(f"📋 Ejemplo para revisión: {', '.join(quality_check['issues'])}")
                self.knn.add_training_example(vector, analysis.classification, feedback_correct)
            
            # Log de estadísticas del modelo
            stats = self.knn.stats_summary()
            log.info(
                f"KNN actualizado | "
                f"Total: {stats['total_examples']} | "
                f"Threshold: {stats['current_threshold']:.2%} | "
                f"Clases: L:{stats['by_label'].get('legitimo', 0)} "
                f"S:{stats['by_label'].get('spam', 0)} "
                f"P:{stats['by_label'].get('sospechoso', 0)}"
            )
        except Exception as exc:
            log.debug(f"No se pudo actualizar KNN: {exc}")
    
    def generate_stats_report(self, output_file: Optional[str] = None) -> str:
        """
        Genera reporte de estadísticas mensuales.
        
        Args:
            output_file: si se especifica, guarda el reporte en archivo
            
        Returns:
            Reporte como string
        """
        if output_file is None:
            output_file = "stats_report.txt"
        
        report = self.stats.generate_report(output_file)
        log.info(f"Reporte de estadísticas generado: {output_file}")
        return report


# ============================================================================
# Entrypoint
# ============================================================================

def main():
    """Punto de entrada principal."""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    agent = SuperAgent2(config_path=config_path)
    agent.start()


if __name__ == "__main__":
    main()
