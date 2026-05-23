"""
agent.py — Orquestador principal del agente de análisis de phishing
Corre como Windows Service o proceso background permanente.

Flujo:
  1. Polling de SharePoint via Graph API → descarga .txt a ingress/
  2. FileSystemWatcher detecta nuevos archivos en ingress/
  3. KNN clasifica rápidamente con features del header
  4. Si confianza < umbral → Ollama para análisis profundo
  5. Según clasificación:
     - legitimo    → notifica via Power Automate, mueve a processed/legitimo/
     - spam        → notifica via Power Automate, mueve a processed/spam/
     - sospechoso  → crea caso en IRIS DFIR, mueve a processed/sospechoso/
  6. En todos los casos → notifica al destinatario del email reportado
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

# --- Dependencias locales ---
from sharepoint_client import SharePointClient
from knn_classifier     import KNNClassifier, extract_features, features_to_vector, FEATURE_NAMES
from phishing_analyzer_txt_08 import PhishingAnalyzerTXT, EmailAnalysis


# ---------------------------------------------------------------------------
# Logger global del agente
# ---------------------------------------------------------------------------

def setup_agent_logger(log_level: str = "INFO", log_dir: str = "logs") -> logging.Logger:
    Path(log_dir).mkdir(exist_ok=True)
    logger = logging.getLogger("phishing_analyzer")
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
        Path(log_dir) / "agent.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


log = logging.getLogger("phishing_analyzer.agent")


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "poll_interval_seconds": 60,
    "ingress_dir":  "ingress",
    "processed_dir": "processed",
    "analysis_dir":  "analysis_results",
    "log_level":     "INFO",
    "log_dir":       "logs",
    "knn_confidence_threshold": 0.85,
    "llm_provider":  "ollama",
    "ollama_url":    "http://localhost:11434/api/generate",
    "ollama_model":  "llama3.2",
    "anthropic_api_key": "",
    "abuseipdb_api_key": "",
    "max_workers":   2,
    "whitelist_path": "whitelist.txt",
    "azure": {
        "tenant_id":     "",
        "client_id":     "",
        "client_secret": ""
    },
    "sharepoint": {
        "site_id":     "",
        "drive_id":    "",
        "folder_path": "/phishing-reports"
    },
    "webhook_spam":    "",
    "webhook_legitimo": "",
    "webhook_notify_reporter": "",
    "iris_dfir": {
        "url":         "",
        "api_key":     "",
        "verify_ssl":  True,
        "default_customer_id":    1,
        "default_classification": 30
    }
}


def load_config(config_path: str = "config.json") -> Dict:
    config = DEFAULT_CONFIG.copy()
    if not os.path.exists(config_path):
        log.warning("config.json no encontrado — usando defaults. Crear el archivo para configurar.")
        # Escribir template
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        log.info("Template config.json creado en %s", config_path)
        return config

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        # Merge profundo para no perder claves anidadas
        _deep_merge(config, loaded)
        log.info("Configuración cargada desde %s", config_path)
    except Exception as exc:
        log.error("Error leyendo config.json: %s", exc)

    return config


def _deep_merge(base: Dict, override: Dict):
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


# ---------------------------------------------------------------------------
# Agente principal
# ---------------------------------------------------------------------------

class PhishingAgent:
    """
    Agente de análisis de phishing que corre como servicio permanente.
    Combina:
      - Polling de SharePoint (Graph API)
      - FileSystemWatcher sobre carpeta ingress/
      - Clasificación KNN + Ollama híbrida
      - Acciones post-análisis (IRIS, Power Automate, notificación al reporter)
    """

    def __init__(self, config_path: str = "config.json"):
        self.config   = load_config(config_path)
        setup_agent_logger(self.config.get("log_level", "INFO"), self.config.get("log_dir", "logs"))

        self.ingress_dir   = Path(self.config["ingress_dir"])
        self.processed_dir = Path(self.config["processed_dir"])
        self.poll_interval = int(self.config.get("poll_interval_seconds", 60))

        # Crear estructura de carpetas
        for sub in ("legitimo", "spam", "sospechoso"):
            (self.processed_dir / sub).mkdir(parents=True, exist_ok=True)
        self.ingress_dir.mkdir(parents=True, exist_ok=True)
        Path(self.config["analysis_dir"]).mkdir(parents=True, exist_ok=True)

        # Componentes
        self.sp_client = SharePointClient(self.config)
        self.knn       = KNNClassifier(
            k=5,
            confidence_threshold=float(self.config.get("knn_confidence_threshold", 0.85))
        )
        self.analyzer  = PhishingAnalyzerTXT(config_path)

        # Cola de archivos a procesar (thread-safe)
        self.file_queue: queue.Queue = queue.Queue()

        # Control del loop
        self._running  = False
        self._stop_evt = threading.Event()

        log.info("=" * 60)
        log.info("Agente de phishing inicializado")
        log.info("  Ingress:       %s", self.ingress_dir.resolve())
        log.info("  Processed:     %s", self.processed_dir.resolve())
        log.info("  Poll interval: %ds", self.poll_interval)
        log.info("  KNN threshold: %.0f%%", float(self.config.get("knn_confidence_threshold", 0.85)) * 100)
        log.info("  LLM provider:  %s", self.config.get("llm_provider", "ollama"))
        log.info("=" * 60)

    # ------------------------------------------------------------------
    # Ciclo principal
    # ------------------------------------------------------------------

    def start(self):
        """Inicia el agente. Bloqueante — usar en hilo o como proceso principal."""
        self._running = True
        signal.signal(signal.SIGINT,  self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        # Hilo de procesamiento de cola
        worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="analysis-worker"
        )
        worker_thread.start()

        # Hilo de FileWatcher sobre ingress/ (detecta archivos ya presentes o copiados manualmente)
        watcher_thread = threading.Thread(
            target=self._file_watcher_loop, daemon=True, name="file-watcher"
        )
        watcher_thread.start()

        log.info("Agente iniciado. Iniciando polling de SharePoint cada %ds...", self.poll_interval)

        # Loop principal: polling de SharePoint
        while self._running:
            try:
                self._poll_sharepoint()
            except Exception as exc:
                log.error("Error en ciclo de polling: %s", exc)

            self._stop_evt.wait(timeout=self.poll_interval)

        log.info("Agente detenido.")

    def _handle_shutdown(self, signum, frame):
        log.info("Señal de shutdown recibida (%s). Deteniendo...", signum)
        self._running = False
        self._stop_evt.set()

    # ------------------------------------------------------------------
    # Polling SharePoint
    # ------------------------------------------------------------------

    def _poll_sharepoint(self):
        """Un ciclo de polling: descarga archivos nuevos de SharePoint a ingress/."""
        try:
            downloaded = self.sp_client.poll_and_download()
            for path in downloaded:
                self.file_queue.put(path)
                log.info("Archivo encolado desde SharePoint: %s", path.name)
        except Exception as exc:
            log.error("Error en poll SharePoint: %s", exc)

    # ------------------------------------------------------------------
    # FileWatcher — detecta archivos que llegan por otras vías
    # ------------------------------------------------------------------

    def _file_watcher_loop(self):
        """
        Monitorea la carpeta ingress/ buscando .txt no procesados.
        Complementa el polling de SharePoint — captura archivos
        copiados manualmente o por otros procesos.
        """
        seen = set()
        log.info("FileWatcher iniciado en: %s", self.ingress_dir.resolve())

        while self._running:
            try:
                current = {
                    p for p in self.ingress_dir.glob("*.txt")
                    if p.is_file()
                }
                new_files = current - seen
                for path in sorted(new_files):
                    log.info("FileWatcher: nuevo archivo detectado: %s", path.name)
                    self.file_queue.put(path)
                    seen.add(path)

                # Limpiar seen: quitar archivos que ya no están en ingress
                seen = seen & current

            except Exception as exc:
                log.error("Error en FileWatcher: %s", exc)

            time.sleep(5)  # check cada 5 segundos

    # ------------------------------------------------------------------
    # Worker: procesa la cola de archivos
    # ------------------------------------------------------------------

    def _worker_loop(self):
        """Procesa archivos de la cola uno por uno."""
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
                log.error("Error en worker: %s", exc)

    # ------------------------------------------------------------------
    # Procesamiento de un archivo
    # ------------------------------------------------------------------

    def _process_file(self, file_path: Path):
        log.info("─" * 60)
        log.info("Procesando: %s", file_path.name)

        if not file_path.exists():
            log.warning("Archivo no encontrado (puede haber sido movido): %s", file_path)
            return

        # 1. Parsear headers
        parsed = self.analyzer.parse_txt_file(str(file_path))
        if not parsed:
            log.error("No se pudo parsear: %s", file_path.name)
            self._move_to_processed(file_path, "spam")  # mover igual para no bloquearlo
            return

        headers        = parsed["headers"]
        microsoft_urls = parsed["microsoft_urls"]
        content        = parsed["raw_content"]
        from_email     = headers.get("From", "")

        # 2. Whitelist check (bypass total)
        if self.analyzer.check_whitelist(from_email):
            log.info("Whitelist match: %s → legítimo", from_email)
            analysis = self.analyzer.analyze_txt_file(str(file_path))
            self._handle_result(file_path, analysis)
            return

        # 3. KNN rápido
        knn_result = self.knn.classify_email(headers, content, microsoft_urls)

        if knn_result["is_confident"]:
            # KNN confía → crear EmailAnalysis sintético sin pasar por Ollama
            log.info("KNN directo (%.0f%% confianza) → %s",
                     knn_result["confidence"] * 100, knn_result["classification"].upper())
            analysis = self._build_analysis_from_knn(file_path, parsed, knn_result)
        else:
            # Confianza baja → análisis completo con Ollama
            log.info("KNN inseguro (%.0f%%) → escalando a Ollama...", knn_result["confidence"] * 100)
            analysis = self.analyzer.analyze_txt_file(str(file_path))
            # Enriquecer con features KNN
            if analysis:
                analysis.reasons = [
                    f"KNN: {knn_result['classification']} ({knn_result['confidence']:.0%})"
                ] + analysis.reasons

        self._handle_result(file_path, analysis)

    def _build_analysis_from_knn(self, file_path: Path, parsed: Dict, knn_result: Dict) -> EmailAnalysis:
        """Construye un EmailAnalysis a partir del resultado KNN (sin llamar a Ollama)."""
        headers        = parsed["headers"]
        content        = parsed["raw_content"]
        microsoft_urls = parsed["microsoft_urls"]

        auth      = self.analyzer.check_authentication(headers)
        urls      = self.analyzer.extract_urls_from_content(content)
        sender_ip = self.analyzer.extract_sender_ip(headers)
        ip_rep    = self.analyzer.check_ip_reputation(sender_ip)
        homograph = self.analyzer.check_homograph_spoofing(headers.get("From", ""))
        reasons   = self.analyzer.check_suspicious_patterns(headers, content)
        risk_score = self.analyzer.calculate_risk_score(
            auth, reasons, urls, microsoft_urls, ip_rep, homograph
        )

        active_features = [
            FEATURE_NAMES[i] for i, v in enumerate(knn_result["vector"]) if v > 0
        ]

        return EmailAnalysis(
            mensaje_id          = headers.get("Message-ID", file_path.stem),
            classification      = knn_result["classification"],
            confidence          = knn_result["confidence"],
            reporter_email      = self.analyzer.extract_reporter_from_content(content),
            original_subject    = headers.get("Subject", "N/A"),
            original_from       = headers.get("From", "N/A"),
            reply_to            = self.analyzer.extract_reply_to(headers),
            sender_ip           = sender_ip,
            ip_reputation       = ip_rep,
            analysis_date       = datetime.now().isoformat(),
            indicators          = auth,
            headers_raw         = str(headers),
            body_preview        = content[:500],
            urls_found          = urls[:10],
            microsoft_url_check = microsoft_urls,
            risk_score          = risk_score,
            reasons             = reasons + [
                f"KNN features activas: {', '.join(active_features[:8])}"
            ]
        )

    # ------------------------------------------------------------------
    # Acciones según clasificación
    # ------------------------------------------------------------------

    def _handle_result(self, file_path: Path, analysis: Optional[EmailAnalysis]):
        if not analysis:
            log.error("Análisis nulo para: %s", file_path.name)
            self._move_to_processed(file_path, "spam")
            return

        classification = analysis.classification
        log.info(
            "RESULTADO → %s | Score: %d/100 | Confianza: %.0f%%",
            classification.upper(), analysis.risk_score, analysis.confidence * 100
        )

        # Guardar JSON del análisis
        self.analyzer.save_analysis(analysis)

        if classification == "sospechoso":
            log.info("→ Creando caso en IRIS DFIR...")
            case_id = self.analyzer.create_iris_case(analysis)
            if case_id:
                log.info("  Caso IRIS #%s creado", case_id)

            # Notificar al reporter que es sospechoso
            self._notify_reporter(analysis, "sospechoso")

            # Actualizar KNN con este ejemplo confirmado
            self._update_knn(analysis)

        elif classification == "spam":
            log.info("→ Enviando webhook Power Automate (spam)...")
            self.analyzer.send_to_powerautomate(analysis, "spam")
            self._notify_reporter(analysis, "spam")
            self._update_knn(analysis)

        elif classification == "legitimo":
            log.info("→ Enviando webhook Power Automate (legítimo)...")
            self.analyzer.send_to_powerautomate(analysis, "legitimo")
            self._notify_reporter(analysis, "legitimo")

        self._move_to_processed(file_path, classification)

    def _notify_reporter(self, analysis: EmailAnalysis, classification: str):
        """
        Notifica al destinatario del email reportado con el resultado del análisis.
        Usa el webhook de Power Automate configurado en webhook_notify_reporter.
        El Flow de PA se encarga de enviar el email real al reporter.
        """
        webhook_url = self.config.get("webhook_notify_reporter", "")
        if not webhook_url:
            log.debug("webhook_notify_reporter no configurado — notificación al reporter omitida.")
            return

        messages = {
            "legitimo":   (
                "✅ El email que reportaste fue revisado y corresponde a un remitente legítimo "
                "conocido. No se requiere ninguna acción adicional."
            ),
            "spam":       (
                "📧 El email que reportaste fue analizado y clasificado como SPAM o correo "
                "no deseado. Ha sido registrado para mejorar los filtros. "
                "No hay riesgo de seguridad asociado."
            ),
            "sospechoso": (
                "⚠️ El email que reportaste fue identificado como SOSPECHOSO y posible phishing. "
                "Nuestro equipo de seguridad ya fue notificado y está investigando el caso. "
                "Por favor NO hagas clic en ningún enlace ni descargues adjuntos de ese email."
            ),
        }

        payload = {
            "reporter_email":   analysis.reporter_email,
            "classification":   classification,
            "original_subject": analysis.original_subject,
            "original_from":    analysis.original_from,
            "risk_score":       analysis.risk_score,
            "message_to_user":  messages.get(classification, "Tu reporte fue procesado."),
            "analysis_date":    analysis.analysis_date,
            "case_id":          analysis.mensaje_id,
        }

        from phishing_analyzer_txt_08 import retry_post
        resp = retry_post(webhook_url, payload)
        if resp:
            log.info("Reporter notificado: %s (%s)", analysis.reporter_email, classification)
        else:
            log.warning("No se pudo notificar al reporter: %s", analysis.reporter_email)

    def _move_to_processed(self, file_path: Path, classification: str):
        """Mueve el archivo de ingress/ a processed/<clasificación>/."""
        dest_dir  = self.processed_dir / classification
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Agregar timestamp para evitar colisiones
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_name = f"{ts}_{file_path.name}"
        dest_path = dest_dir / dest_name

        try:
            shutil.move(str(file_path), str(dest_path))
            log.info("Archivo movido → processed/%s/%s", classification, dest_name)
        except Exception as exc:
            log.error("No se pudo mover %s: %s", file_path.name, exc)

    def _update_knn(self, analysis: EmailAnalysis):
        """Actualiza el modelo KNN con el nuevo ejemplo (aprendizaje activo)."""
        try:
            parsed = self.analyzer.parse_txt_file  # ya no tenemos el archivo (fue movido)
            # Reconstruir features desde el análisis guardado
            features = {
                "spf_fail":           1.0 if analysis.indicators.get("spf") in ("fail", "softfail") else 0.0,
                "dkim_none":          1.0 if analysis.indicators.get("dkim") in ("none", "fail") else 0.0,
                "dmarc_none":         1.0 if analysis.indicators.get("dmarc") in ("none", "fail") else 0.0,
                "auth_all_pass":      1.0 if (
                    analysis.indicators.get("spf") == "pass" and
                    analysis.indicators.get("dkim") == "pass" and
                    analysis.indicators.get("dmarc") == "pass"
                ) else 0.0,
                "ms_urls_detected":   1.0 if analysis.microsoft_url_check not in ("None", "") else 0.0,
                "has_attachment":     0.0,
                "url_count_norm":     min(len(analysis.urls_found) / 10.0, 1.0),
            }
            from knn_classifier import features_to_vector, FEATURE_NAMES
            vector = [features.get(n, 0.0) for n in FEATURE_NAMES]
            self.knn.add_training_example(vector, analysis.classification)
        except Exception as exc:
            log.debug("No se pudo actualizar KNN: %s", exc)

    # ------------------------------------------------------------------
    # Diagnóstico
    # ------------------------------------------------------------------

    def status(self) -> Dict:
        return {
            "running":         self._running,
            "queue_size":      self.file_queue.qsize(),
            "knn_stats":       self.knn.stats(),
            "poll_interval":   self.poll_interval,
            "ingress_pending": len(list(self.ingress_dir.glob("*.txt"))),
        }


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Agente de análisis de phishing v0.8")
    parser.add_argument("--config",  default="config.json",  help="Ruta al archivo de configuración")
    parser.add_argument("--file",    default=None,            help="Procesar un archivo puntual y salir")
    parser.add_argument("--status",  action="store_true",     help="Mostrar estado del agente y salir")
    args = parser.parse_args()

    agent = PhishingAgent(config_path=args.config)

    if args.status:
        print(json.dumps(agent.status(), indent=2))
        return

    if args.file:
        # Modo single-file (útil para debugging)
        log.info("Modo single-file: %s", args.file)
        path = Path(args.file)
        if not path.exists():
            log.error("Archivo no encontrado: %s", args.file)
            sys.exit(1)
        # Copiar a ingress y procesar
        dest = agent.ingress_dir / path.name
        shutil.copy(str(path), str(dest))
        agent._process_file(dest)
        return

    # Modo servicio — loop permanente
    log.info("Iniciando agente en modo servicio...")
    agent.start()


if __name__ == "__main__":
    main()
