#!/usr/bin/env python3
"""
SuperAgent_2 — Agente de análisis de phishing sin SharePoint
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
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from smtplib import SMTP, SMTP_SSL
from email.message import EmailMessage

# --- Agregar carpeta agent/ al path para importar módulos ---
agent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agent'))
sys.path.insert(0, agent_dir)

from knn_classifier import KNNClassifier, extract_features, features_to_vector, FEATURE_NAMES
from phishingAnalizer import PhishingAnalyzerTXT, EmailAnalysis
from usage_stats import UsageStats


# ============================================================================
# Logger global
# ============================================================================

def setup_logger(log_level: str = "INFO", log_dir: str = "logs") -> logging.Logger:
    """Configura logger con salida a consola y archivo rotativo."""
    Path(log_dir).mkdir(exist_ok=True, parents=True)
    logger = logging.getLogger("superagent_2")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )
    
    # Consola
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    
    # Archivo rotativo
    fh = logging.handlers.RotatingFileHandler(
        Path(log_dir) / "superagent_2.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    
    return logger


log = logging.getLogger("superagent_2.main")


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
        """Extrae email de una dirección que puede tener formato 'Name <email@example.com>'"""
        if not address:
            return ""
        # Si tiene formato "Name <email@example.com>", extrae el email
        if '<' in address and '>' in address:
            return address[address.find('<')+1:address.find('>')]
        # Si no, devuelve tal cual (asume que es un email)
        return address.strip()
    
    def _print_monthly_stats(self):
        """Imprime estadísticas mensuales en los logs."""
        summary = self.stats.stats_summary()
        month_data = summary["mes_actual"]
        
        if month_data["total"] > 0:
            log.info("📊 Estadísticas del mes actual:")
            log.info(f"  Total procesados: {month_data['total']}")
            log.info(f"  • Legítimos: {month_data['by_classification'].get('legitimo', 0)}")
            log.info(f"  • Spam: {month_data['by_classification'].get('spam', 0)}")
            log.info(f"  • Sospechosos: {month_data['by_classification'].get('sospechoso', 0)}")
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
        for sub in ("legitimo", "spam", "sospechoso"):
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
        log.info("SuperAgent_2 inicializado")
        log.info(f"  Ingress:       {self.ingress_dir}")
        log.info(f"  Processed:     {self.processed_dir}")
        log.info(f"  Analysis:      {self.analysis_dir}")
        log.info(f"  KNN threshold: {self.config.get('knn_confidence_threshold', 0.85) * 100:.0f}%")
        log.info(f"  LLM provider:  {self.config.get('llm_provider', 'ollama')}")
        log.info(f"  Log level:     {self.config.get('log_level', 'INFO')}")
        log.info("=" * 70)
        
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
        
        log.info("SuperAgent_2 iniciado. Observando ingress/...")
        
        # Loop principal
        while self._running:
            try:
                self._stop_evt.wait(timeout=1)
            except Exception as exc:
                log.error(f"Error en loop principal: {exc}")
        
        log.info("SuperAgent_2 detenido.")
    
    def _handle_shutdown(self, signum, frame):
        """Maneja señal de shutdown."""
        log.info(f"Señal de shutdown recibida ({signum}). Deteniendo...")
        self._running = False
        self._stop_evt.set()
    
    # ========================================================================
    # FileWatcher
    # ========================================================================
    
    def _file_watcher_loop(self):
        """Monitorea ingress/ buscando nuevos .txt."""
        seen = set()
        log.info(f"FileWatcher iniciado en: {self.ingress_dir}")
        
        while self._running:
            try:
                current = {p for p in self.ingress_dir.glob("*.txt") if p.is_file()}
                new_files = current - seen
                
                for path in sorted(new_files):
                    log.info(f"FileWatcher: nuevo archivo detectado: {path.name}")
                    self.file_queue.put(path)
                    seen.add(path)
                
                seen = seen & current
                
            except Exception as exc:
                log.error(f"Error en FileWatcher: {exc}")
            
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
                log.error(f"Error en worker: {exc}")
    
    # ========================================================================
    # Procesamiento de archivo
    # ========================================================================
    
    def _process_file(self, file_path: Path):
        """Procesa un archivo: parseo, clasificación, acciones."""
        log.info("─" * 70)
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
        
        headers = parsed["headers"]
        microsoft_urls = parsed["microsoft_urls"]
        content = parsed["raw_content"]
        from_email = headers.get("From", "")
        to_email = self.extract_email_from_address(headers.get("To", ""))
        
        log.info(f"  De: {from_email}")
        log.info(f"  Para (reporter): {to_email}")
        
        if not to_email:
            log.warning(f"No se encontró email del reporter en header 'To:' de {file_path.name}")
            self._move_to_processed(file_path, "spam")
            return
        
        # 2. Whitelist check
        if self.analyzer.check_whitelist(from_email):
            log.info(f"Whitelist match: {from_email} → legítimo")
            analysis = self.analyzer.analyze_txt_file(str(file_path))
            # Registrar estadística: whitelist
            self.stats.record_case("legitimo", "whitelist")
            self._handle_result(file_path, analysis)
            return
        
        # 3. KNN rápido
        knn_result = self.knn.classify_email(headers, content, microsoft_urls)
        
        if knn_result["is_confident"]:
            log.info(
                f"KNN directo ({knn_result['confidence'] * 100:.0f}% confianza) → "
                f"{knn_result['classification'].upper()}"
            )
            analysis = self._build_analysis_from_knn(file_path, parsed, knn_result)
            classification_source = "knn"
        else:
            log.info(
                f"KNN inseguro ({knn_result['confidence'] * 100:.0f}%) → "
                f"escalando a análisis profundo..."
            )
            analysis = self.analyzer.analyze_txt_file(str(file_path))
            if analysis:
                # Sobrescribir reporter_email con el del header "To:" para consistencia
                analysis.reporter_email = to_email
                analysis.reasons = [
                    f"KNN: {knn_result['classification']} ({knn_result['confidence']:.0%}) "
                    f"→ LLM refinement"
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
            mensaje_id=headers.get("Message-ID", file_path.stem),
            classification=knn_result["classification"],
            confidence=knn_result["confidence"],
            reporter_email=self.extract_email_from_address(headers.get("To", "")),
            original_subject=headers.get("Subject", "N/A"),
            original_from=headers.get("From", "N/A"),
            reply_to=self.analyzer.extract_reply_to(headers),
            sender_ip=sender_ip,
            ip_reputation=ip_rep,
            analysis_date=datetime.now().isoformat(),
            indicators=auth,
            headers_raw=str(headers),
            body_preview=content[:500],
            urls_found=urls[:10],
            microsoft_url_check=microsoft_urls,
            risk_score=risk_score,
            reasons=reasons + [
                f"KNN features activas: {', '.join(active_features[:8])}"
            ]
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
            f"RESULTADO → {classification.upper()} | Score: {analysis.risk_score}/100 | "
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
        
        if classification == "sospechoso":
            log.info("→ Registrando alerta en IRIS...")
            self._register_alert_in_iris(analysis)
            self._notify_reporter(analysis, "sospechoso")
            self._update_knn(analysis, knn_result)
        
        elif classification == "spam":
            log.info("→ Email clasificado como SPAM")
            self._notify_reporter(analysis, "spam")
            self._update_knn(analysis, knn_result)
        
        elif classification == "legitimo":
            log.info("→ Email clasificado como LEGÍTIMO")
            self._notify_reporter(analysis, "legitimo")
        
        self._move_to_processed(file_path, classification)
    
    def _register_alert_in_iris(self, analysis: EmailAnalysis):
        """Registra alerta en IRIS 2.5.0 usando endpoint de alertas."""
        iris_cfg = self.config.get("iris_dfir", {})
        url = iris_cfg.get("url", "")
        api_key = iris_cfg.get("api_key", "")
        customer_id = iris_cfg.get("default_customer_id", 1)
        iris_version = iris_cfg.get("iris_version", "2.5.0")
        
        if not url or not api_key:
            log.warning("IRIS DFIR no configurado correctamente - alerta NO registrada")
            return
        
        import requests
        
        # Estructura de alertas compatible con IRIS 2.5.0
        data = {
            "alert_title": f"[SuperAgent] {analysis.original_subject}",
            "alert_description": f"Phishing reportado por: {analysis.reporter_email}\n"
                                 f"Remitente: {analysis.original_from}\n"
                                 f"Asunto: {analysis.original_subject}\n"
                                 f"Score de riesgo: {analysis.risk_score}/100",
            "alert_source": "SuperAgent",
            "alert_severity": iris_cfg.get("default_severity", "high"),
            "alert_status": "new",
            "customer_id": customer_id,
            "alert_type": "phishing",
            "message_id": analysis.mensaje_id,
            "source_email": analysis.original_from,
            "recipient_email": analysis.reporter_email,
            "risk_score": analysis.risk_score,
            "classification": analysis.classification,
            "analysis_date": analysis.analysis_date
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        log.info(f"Intentando registrar alerta en IRIS {iris_version} (URL: {url})")
        
        try:
            response = requests.post(url, json=data, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Intentar extraer ID de alerta de la respuesta
            alert_id = None
            try:
                response_json = response.json()
                alert_id = response_json.get("alert_id") or response_json.get("id")
            except:
                alert_id = None
            
            if alert_id:
                log.info(f"✓ ÉXITO: Alerta creada en IRIS {iris_version} | "
                        f"Alert ID: {alert_id} | Mensaje ID: {analysis.mensaje_id} | "
                        f"Status: {response.status_code}")
            else:
                log.info(f"✓ ÉXITO: Alerta registrada en IRIS {iris_version} | "
                        f"Mensaje ID: {analysis.mensaje_id} | Status: {response.status_code}")
        
        except requests.exceptions.Timeout:
            log.error(f"✗ TIMEOUT: Conexión con IRIS {iris_version} expiró después de 10s | "
                     f"Mensaje ID: {analysis.mensaje_id}")
        
        except requests.exceptions.HTTPError as exc:
            error_msg = str(exc)
            try:
                error_detail = exc.response.text
            except:
                error_detail = "Sin detalles"
            log.error(f"✗ ERROR HTTP: No se pudo registrar alerta en IRIS {iris_version} | "
                     f"Status: {exc.response.status_code if exc.response else 'N/A'} | "
                     f"Detalle: {error_detail} | Mensaje ID: {analysis.mensaje_id}")
        
        except requests.exceptions.ConnectionError as exc:
            log.error(f"✗ ERROR CONEXIÓN: No se puede conectar a IRIS en {url} | "
                     f"Detalle: {exc} | Mensaje ID: {analysis.mensaje_id}")
        
        except Exception as exc:
            log.error(f"✗ ERROR: Fallo registrando alerta en IRIS {iris_version} | "
                     f"Excepción: {type(exc).__name__}: {exc} | Mensaje ID: {analysis.mensaje_id}")
    
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
                f"✅ El email que reportaste fue revisado y clasificado como LEGÍTIMO.\n"
                f"Remitente: {analysis.original_from}\n"
                f"Asunto: {analysis.original_subject}\n"
                f"No se requiere ninguna acción adicional."
            ),
            "spam": (
                f"📧 El email fue clasificado como SPAM.\n"
                f"Remitente: {analysis.original_from}\n"
                f"Asunto: {analysis.original_subject}\n"
                f"Ha sido registrado para mejorar los filtros. No hay riesgo de seguridad."
            ),
            "sospechoso": (
                f"⚠️ El email fue identificado como SOSPECHOSO / PHISHING.\n"
                f"Remitente: {analysis.original_from}\n"
                f"Asunto: {analysis.original_subject}\n"
                f"Score de riesgo: {analysis.risk_score}/100\n"
                f"Nuestro equipo de seguridad ya fue notificado. "
                f"POR FAVOR NO hagas clic en enlaces ni descargues archivos de ese email."
            ),
        }
        
        msg = EmailMessage()
        msg["Subject"] = f"[SuperAgent] Resultado de análisis: {classification.upper()}"
        msg["From"] = smtp_cfg.get("from", "noreply@example.com")
        msg["To"] = to_addr
        msg.set_content(messages.get(classification, "Tu reporte fue procesado."))
        
        try:
            if smtp_cfg.get("use_tls", False):
                with SMTP(smtp_cfg["host"], smtp_cfg["port"]) as smtp:
                    smtp.starttls()
                    #smtp.login(smtp_cfg["username"], smtp_cfg["password"])
                    smtp.send_message(msg)
            else:
                with SMTP_SSL(smtp_cfg["host"], smtp_cfg["port"]) as smtp:
                    #smtp.login(smtp_cfg["username"], smtp_cfg["password"])
                    smtp.send_message(msg)
            
            log.info(f"✓ Notificación enviada a {to_addr} ({classification})")
        
        except Exception as exc:
            log.error(f"✗ Error enviando email a {to_addr}: {exc}")
    
    def _move_to_processed(self, file_path: Path, classification: str):
        """Mueve archivo a processed/<clasificación>/."""
        dest_dir = self.processed_dir / classification
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_name = f"{ts}_{file_path.name}"
        dest_path = dest_dir / dest_name
        
        try:
            shutil.move(str(file_path), str(dest_path))
            log.info(f"Archivo movido → processed/{classification}/{dest_name}")
        except Exception as exc:
            log.error(f"No se pudo mover {file_path.name}: {exc}")
    
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
