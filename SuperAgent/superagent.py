
import os
import sys
import time
import json
import shutil
import logging
import logging.handlers
import threading
import queue
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from smtplib import SMTP, SMTP_SSL
from email.message import EmailMessage

# --- Dependencias locales ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agent')))
from knn_classifier import KNNClassifier, extract_features, features_to_vector, FEATURE_NAMES
from phishingAnalizer import PhishingAnalyzerTXT, EmailAnalysis

def setup_superagent_logger(log_level: str = "INFO", log_dir: str = "logs") -> logging.Logger:
    Path(log_dir).mkdir(exist_ok=True)
    logger = logging.getLogger("superagent")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    fh = logging.handlers.RotatingFileHandler(
        Path(log_dir) / "superagent.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger

def load_config(config_path: str = "config.json") -> Dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

class SuperAgent:
    def __init__(self, config_path: str = "config.json"):
        self.config = load_config(config_path)
        self.logger = setup_superagent_logger(self.config.get("log_level", "INFO"), self.config.get("log_dir", "logs"))
        self.ingress_dir = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'ingress')))
        self.processed_dir = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'processed')))
        for sub in ("legitimo", "spam", "sospechoso"):
            (self.processed_dir / sub).mkdir(parents=True, exist_ok=True)
        self.ingress_dir.mkdir(parents=True, exist_ok=True)
        self.knn = KNNClassifier(k=5, confidence_threshold=0.85)
        self.analyzer = PhishingAnalyzerTXT(config_path)
        self.file_queue: queue.Queue = queue.Queue()
        self._running = False

    def start(self):
        self._running = True
        watcher_thread = threading.Thread(target=self._file_watcher_loop, daemon=True, name="file-watcher")
        worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="analysis-worker")
        watcher_thread.start()
        worker_thread.start()
        self.logger.info("SuperAgent iniciado. Observando carpeta ingress...")
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            self._running = False
        self.logger.info("SuperAgent detenido.")

    def _file_watcher_loop(self):
        seen = set()
        self.logger.info(f"FileWatcher iniciado en: {self.ingress_dir.resolve()}")
        while self._running:
            try:
                current = {p for p in self.ingress_dir.glob("*.txt") if p.is_file()}
                new_files = current - seen
                for path in sorted(new_files):
                    self.logger.info(f"Nuevo archivo detectado: {path.name}")
                    self.file_queue.put(path)
                    seen.add(path)
                seen = seen & current
            except Exception as exc:
                self.logger.error(f"Error en FileWatcher: {exc}")
            time.sleep(5)

    def _worker_loop(self):
        self.logger.info("Worker de análisis iniciado.")
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
                self.logger.error(f"Error en worker: {exc}")

    def _process_file(self, file_path: Path):
        self.logger.info("─" * 60)
        self.logger.info(f"Procesando: {file_path.name}")
        if not file_path.exists():
            self.logger.warning(f"Archivo no encontrado: {file_path}")
            return
        parsed = self.analyzer.parse_txt_file(str(file_path))
        if not parsed:
            self.logger.error(f"No se pudo parsear: {file_path.name}")
            self._move_to_processed(file_path, "spam")
            return
        headers = parsed["headers"]
        microsoft_urls = parsed["microsoft_urls"]
        content = parsed["raw_content"]
        from_email = headers.get("From", "")
        # Whitelist
        if self.analyzer.check_whitelist(from_email):
            self.logger.info(f"Whitelist match: {from_email} → legítimo")
            analysis = self.analyzer.analyze_txt_file(str(file_path))
            self._handle_result(file_path, analysis)
            return
        # KNN
        knn_result = self.knn.classify_email(headers, content, microsoft_urls)
        if knn_result["is_confident"]:
            self.logger.info(f"KNN directo ({knn_result['confidence']*100:.0f}%) → {knn_result['classification'].upper()}")
            analysis = self._build_analysis_from_knn(file_path, parsed, knn_result)
        else:
            self.logger.info(f"KNN inseguro ({knn_result['confidence']*100:.0f}%) → análisis profundo...")
            analysis = self.analyzer.analyze_txt_file(str(file_path))
            if analysis:
                analysis.reasons = [f"KNN: {knn_result['classification']} ({knn_result['confidence']:.0%})"] + analysis.reasons
        self._handle_result(file_path, analysis)

    def _build_analysis_from_knn(self, file_path: Path, parsed: Dict, knn_result: Dict) -> EmailAnalysis:
        headers = parsed["headers"]
        content = parsed["raw_content"]
        microsoft_urls = parsed["microsoft_urls"]
        auth = self.analyzer.check_authentication(headers)
        urls = self.analyzer.extract_urls_from_content(content)
        sender_ip = self.analyzer.extract_sender_ip(headers)
        ip_rep = self.analyzer.check_ip_reputation(sender_ip)
        homograph = self.analyzer.check_homograph_spoofing(headers.get("From", ""))
        reasons = self.analyzer.check_suspicious_patterns(headers, content)
        risk_score = self.analyzer.calculate_risk_score(auth, reasons, urls, microsoft_urls, ip_rep, homograph)
        active_features = [FEATURE_NAMES[i] for i, v in enumerate(knn_result["vector"]) if v > 0]
        return EmailAnalysis(
            mensaje_id=headers.get("Message-ID", file_path.stem),
            classification=knn_result["classification"],
            confidence=knn_result["confidence"],
            reporter_email=self.analyzer.extract_reporter_from_content(content),
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
            reasons=reasons + [f"KNN features activas: {', '.join(active_features[:8])}"]
        )

    def _handle_result(self, file_path: Path, analysis: Optional[EmailAnalysis]):
        if not analysis:
            self.logger.error(f"Análisis nulo para: {file_path.name}")
            self._move_to_processed(file_path, "spam")
            return
        classification = analysis.classification
        self.logger.info(f"RESULTADO → {classification.upper()} | Score: {analysis.risk_score}/100 | Confianza: {analysis.confidence*100:.0f}%")
        # Guardar JSON del análisis
        self.analyzer.save_analysis(analysis)
        if classification == "sospechoso":
            self.logger.info("→ Registrando caso en IRIS...")
            self._register_case_in_iris(analysis)
            self._notify_reporter(analysis, "sospechoso")
            self._update_knn(analysis)
        elif classification == "spam":
            self._notify_reporter(analysis, "spam")
            self._update_knn(analysis)
        elif classification == "legitimo":
            self._notify_reporter(analysis, "legitimo")
        self._move_to_processed(file_path, classification)

    def _register_case_in_iris(self, analysis: EmailAnalysis):
        iris_cfg = self.config.get("iris", {})
        url = iris_cfg.get("endpoint", "")
        api_key = iris_cfg.get("api_key", "")
        if not url or not api_key:
            self.logger.warning("IRIS no configurado correctamente.")
            return
        import requests
        data = {
            'filename': analysis.mensaje_id,
            'classification': analysis.classification,
            'risk_score': analysis.risk_score,
            'reporter_email': analysis.reporter_email
        }
        headers = {'Authorization': f'Bearer {api_key}'}
        try:
            response = requests.post(url, json=data, headers=headers)
            response.raise_for_status()
            self.logger.info(f"Caso registrado en IRIS: {data}")
        except Exception as e:
            self.logger.error(f"Error registrando caso en IRIS: {e}")

    def _notify_reporter(self, analysis: EmailAnalysis, classification: str):
        smtp_cfg = self.config.get("smtp", {})
        to_addr = analysis.reporter_email
        if not to_addr:
            self.logger.warning(f"No se encontró email del reporter para notificar.")
            return
        msg = EmailMessage()
        msg['Subject'] = f"[SuperAgent] Resultado de análisis: {classification.upper()}"
        msg['From'] = smtp_cfg.get('from', 'noreply@example.com')
        msg['To'] = to_addr
        body = f"El archivo fue clasificado como {classification}.\n\nDetalles:\nScore: {analysis.risk_score}/100\nConfianza: {analysis.confidence*100:.0f}%\n"
        msg.set_content(body)
        try:
            if smtp_cfg.get('use_tls', False):
                with SMTP(smtp_cfg['host'], smtp_cfg['port']) as smtp:
                    smtp.starttls()
                    smtp.login(smtp_cfg['username'], smtp_cfg['password'])
                    smtp.send_message(msg)
            else:
                with SMTP_SSL(smtp_cfg['host'], smtp_cfg['port']) as smtp:
                    smtp.login(smtp_cfg['username'], smtp_cfg['password'])
                    smtp.send_message(msg)
            self.logger.info(f"Notificación enviada a {to_addr}")
        except Exception as e:
            self.logger.error(f"Error enviando email a {to_addr}: {e}")

    def _move_to_processed(self, file_path: Path, classification: str):
        dest_dir = self.processed_dir / classification
        dest_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_name = f"{ts}_{file_path.name}"
        dest_path = dest_dir / dest_name
        try:
            shutil.move(str(file_path), str(dest_path))
            self.logger.info(f"Archivo movido → processed/{classification}/{dest_name}")
        except Exception as exc:
            self.logger.error(f"No se pudo mover {file_path.name}: {exc}")

    def _update_knn(self, analysis: EmailAnalysis):
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
            self.knn.add_training_example(vector, analysis.classification)
        except Exception as exc:
            self.logger.debug(f"No se pudo actualizar KNN: {exc}")

def main():
    agent = SuperAgent(config_path=os.path.join(os.path.dirname(__file__), 'config.json'))
    agent.start()

if __name__ == "__main__":
    main()
