"""
test_agent.py — Versión de prueba del agente de análisis de phishing
Lee archivos .txt desde la carpeta local "suspect/", analiza y mueve
según clasificación. Sin SharePoint, sin IRIS, sin notificaciones.

Carpetas:
  suspect/                 → archivos a analizar (input)
  analyzed/legitimo/       → emails clasificados como legítimos
  analyzed/spam/           → emails clasificados como spam
  analyzed/sospechoso/     → emails clasificados como sospechosos
  test_log.txt             → log consolidado de todos los análisis
"""

import os
import sys
import json
import shutil
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from knn_classifier           import KNNClassifier, FEATURE_NAMES
from phishing_analyzer_txt_08 import PhishingAnalyzerTXT, EmailAnalysis


# ---------------------------------------------------------------------------
# Carpetas
# ---------------------------------------------------------------------------

SUSPECT_DIR  = Path("suspect")
ANALYZED_DIR = Path("analyzed")
TEST_LOG     = Path("test_log.txt")
CONFIG_PATH  = "test_config.json"


# ---------------------------------------------------------------------------
# Logger de prueba
# ---------------------------------------------------------------------------

def setup_test_logger() -> logging.Logger:
    logger = logging.getLogger("test_agent")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )

    # Consola
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # test_log.txt (append — acumula runs)
    fh = logging.FileHandler(TEST_LOG, mode="a", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


log = setup_test_logger()


# ---------------------------------------------------------------------------
# Config mínima para pruebas
# ---------------------------------------------------------------------------

TEST_CONFIG_DEFAULTS = {
    "llm_provider":             "ollama",
    "ollama_url":               "http://localhost:11434/api/generate",
    "ollama_model":             "llama3.2",
    "anthropic_api_key":        "",
    "abuseipdb_api_key":        "",
    "whitelist_path":           "legitimos.txt",
    "log_level":                "DEBUG",
    "max_workers":              1,
    "knn_confidence_threshold": 0.85,
    "analysis_dir":             "analyzed/json",
    # Webhooks vacíos — en test no se usan
    "webhook_spam":             "",
    "webhook_legitimo":         "",
    "webhook_notify_reporter":  "",
    # IRIS vacío — en test no se usa
    "iris_dfir": {
        "url":     "",
        "api_key": ""
    }
}


def load_test_config() -> Dict:
    config = TEST_CONFIG_DEFAULTS.copy()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                overrides = json.load(f)
            config.update(overrides)
            log.info("Configuración de prueba cargada: %s", CONFIG_PATH)
        except Exception as exc:
            log.warning("Error leyendo %s: %s — usando defaults", CONFIG_PATH, exc)
    else:
        # Crear template de config de prueba
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(TEST_CONFIG_DEFAULTS, f, indent=2, ensure_ascii=False)
        log.info("Template %s creado. Editar si necesitás Ollama/Anthropic.", CONFIG_PATH)
    return config


# ---------------------------------------------------------------------------
# Clase agente de prueba
# ---------------------------------------------------------------------------

class TestAgent:
    """
    Agente de prueba: lee de suspect/, analiza con KNN + Ollama (opcional),
    mueve resultados a analyzed/<clasificacion>/, escribe test_log.txt.
    Sin SharePoint, sin IRIS, sin emails al reporter.
    """

    def __init__(self):
        self.config   = load_test_config()
        self.analyzer = PhishingAnalyzerTXT(CONFIG_PATH)
        self.knn      = KNNClassifier(
            k=5,
            confidence_threshold=float(self.config.get("knn_confidence_threshold", 0.85))
        )

        # Crear estructura de carpetas
        for sub in ("legitimo", "spam", "sospechoso", "json"):
            (ANALYZED_DIR / sub).mkdir(parents=True, exist_ok=True)
        SUSPECT_DIR.mkdir(parents=True, exist_ok=True)

        self.results: List[Dict] = []   # resumen de todos los análisis del run

    # ------------------------------------------------------------------
    # Escaneo y procesamiento
    # ------------------------------------------------------------------

    def run(self):
        txt_files = sorted(SUSPECT_DIR.glob("*.txt"))

        if not txt_files:
            log.warning("No hay archivos .txt en la carpeta '%s'.", SUSPECT_DIR)
            log.info("Copiar archivos phishing_*.txt a la carpeta '%s' y volver a ejecutar.", SUSPECT_DIR)
            return

        self._log_run_header(len(txt_files))

        for file_path in txt_files:
            result = self._process_file(file_path)
            if result:
                self.results.append(result)

        self._log_run_summary()

    def _process_file(self, file_path: Path) -> Optional[Dict]:
        log.info("")
        log.info("━" * 64)
        log.info("ARCHIVO : %s", file_path.name)
        log.info("━" * 64)

        # 1. Parsear
        parsed = self.analyzer.parse_txt_file(str(file_path))
        if not parsed:
            log.error("No se pudo parsear: %s", file_path.name)
            self._move(file_path, "spam")
            return None

        headers        = parsed["headers"]
        microsoft_urls = parsed["microsoft_urls"]
        content        = parsed["raw_content"]
        from_email     = headers.get("From", "N/A")
        subject        = headers.get("Subject", "N/A")

        log.info("FROM    : %s", from_email)
        log.info("SUBJECT : %s", subject)

        # 2. Whitelist check
        if self.analyzer.check_whitelist(from_email):
            log.info("WHITELIST: dominio conocido → clasificado como LEGÍTIMO directamente")
            analysis = self.analyzer.analyze_txt_file(str(file_path))
            return self._finalize(file_path, analysis, method="whitelist")

        # 3. KNN rápido
        knn_result = self.knn.classify_email(headers, content, microsoft_urls)
        log.info(
            "KNN     : %s (confianza %.1f%%) [umbral %.0f%%]",
            knn_result["classification"].upper(),
            knn_result["confidence"] * 100,
            float(self.config.get("knn_confidence_threshold", 0.85)) * 100
        )
        self._log_active_features(knn_result["features"])

        if knn_result["is_confident"]:
            log.info("MÉTODO  : KNN directo (confianza suficiente — Ollama omitido)")
            analysis = self._build_analysis_from_knn(file_path, parsed, knn_result)
            return self._finalize(file_path, analysis, method="knn_direct")
        else:
            log.info("MÉTODO  : KNN inseguro → escalando a Ollama para análisis profundo")
            analysis = self.analyzer.analyze_txt_file(str(file_path))
            if analysis:
                analysis.reasons = [
                    f"KNN sugirió: {knn_result['classification']} ({knn_result['confidence']:.0%})"
                ] + analysis.reasons
            return self._finalize(file_path, analysis, method="ollama")

    def _finalize(self, file_path: Path, analysis: Optional[EmailAnalysis], method: str) -> Optional[Dict]:
        if not analysis:
            log.error("Análisis nulo — moviendo a spam por defecto")
            self._move(file_path, "spam")
            return None

        cls        = analysis.classification
        score      = analysis.risk_score
        confidence = analysis.confidence

        log.info("")
        log.info("┌─ RESULTADO ─────────────────────────────────────┐")
        log.info("│  Clasificación : %-32s│", cls.upper())
        log.info("│  Risk score    : %-3d/100                         │", score)
        log.info("│  Confianza     : %-5.1f%%                          │", confidence * 100)
        log.info("│  Método        : %-32s│", method)
        log.info("│  From          : %-32s│", (analysis.original_from or "")[:32])
        log.info("│  Reply-To      : %-32s│", (analysis.reply_to or "N/A")[:32])
        log.info("│  IP origen     : %-32s│", (analysis.sender_ip or "N/A")[:32])
        log.info("│  MS URLs       : %-32s│", (analysis.microsoft_url_check or "None")[:32])
        log.info("│  SPF/DKIM/DMARC: %-4s / %-4s / %-16s│",
                 analysis.indicators.get("spf",   "?"),
                 analysis.indicators.get("dkim",  "?"),
                 analysis.indicators.get("dmarc", "?"))
        log.info("└─────────────────────────────────────────────────┘")

        if analysis.reasons:
            log.info("RAZONES :")
            for r in analysis.reasons[:8]:
                if r:
                    log.info("  • %s", r)

        # Guardar JSON del análisis
        self._save_json(analysis, method)

        # Mover archivo
        self._move(file_path, cls)

        # Construir resumen para el reporte final
        return {
            "archivo":        file_path.name,
            "clasificacion":  cls,
            "risk_score":     score,
            "confianza":      round(confidence, 4),
            "metodo":         method,
            "from":           analysis.original_from,
            "subject":        analysis.original_subject,
            "reply_to":       analysis.reply_to,
            "sender_ip":      analysis.sender_ip,
            "spf":            analysis.indicators.get("spf",   "unknown"),
            "dkim":           analysis.indicators.get("dkim",  "unknown"),
            "dmarc":          analysis.indicators.get("dmarc", "unknown"),
            "ms_urls":        analysis.microsoft_url_check,
            "razones":        [r for r in analysis.reasons if r][:5],
            "timestamp":      analysis.analysis_date,
        }

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _log_active_features(self, features: Dict):
        """Muestra en el log las features con valor > 0 (las que influyeron)."""
        activas = {k: round(v, 2) for k, v in features.items() if v > 0}
        if activas:
            log.debug("KNN features activas: %s", json.dumps(activas))

    def _build_analysis_from_knn(self, file_path: Path, parsed: Dict, knn_result: Dict) -> EmailAnalysis:
        """Construye un EmailAnalysis desde el resultado KNN (sin Ollama)."""
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

        active = [FEATURE_NAMES[i] for i, v in enumerate(knn_result["vector"]) if v > 0]

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
            reasons             = reasons + [f"KNN features: {', '.join(active[:8])}"]
        )

    def _save_json(self, analysis: EmailAnalysis, method: str):
        """Guarda el análisis completo como JSON en analyzed/json/."""
        from dataclasses import asdict
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"test_{ts}_{analysis.classification}.json"
        dest     = ANALYZED_DIR / "json" / filename
        try:
            data = asdict(analysis)
            data["_test_method"] = method
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            log.debug("JSON guardado: %s", dest)
        except Exception as exc:
            log.warning("No se pudo guardar JSON: %s", exc)

    def _move(self, file_path: Path, classification: str):
        """Mueve el archivo de suspect/ a analyzed/<clasificacion>/."""
        dest_dir = ANALYZED_DIR / classification
        dest_dir.mkdir(parents=True, exist_ok=True)
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_name = f"test_{ts}_{file_path.name}"
        dest_path = dest_dir / dest_name
        try:
            shutil.move(str(file_path), str(dest_path))
            log.info("MOVIDO  : suspect/%s → analyzed/%s/%s",
                     file_path.name, classification, dest_name)
        except Exception as exc:
            log.error("No se pudo mover %s: %s", file_path.name, exc)

    # ------------------------------------------------------------------
    # Resumen final del run
    # ------------------------------------------------------------------

    def _log_run_header(self, total: int):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.info("")
        log.info("═" * 64)
        log.info("  TEST RUN — Agente de análisis de phishing v0.8")
        log.info("  Inicio   : %s", ts)
        log.info("  Archivos : %d archivo(s) en suspect/", total)
        log.info("═" * 64)

    def _log_run_summary(self):
        total      = len(self.results)
        legitimos  = sum(1 for r in self.results if r["clasificacion"] == "legitimo")
        spams      = sum(1 for r in self.results if r["clasificacion"] == "spam")
        sospechosos = sum(1 for r in self.results if r["clasificacion"] == "sospechoso")

        knn_direct = sum(1 for r in self.results if r["metodo"] == "knn_direct")
        ollama_used = sum(1 for r in self.results if r["metodo"] == "ollama")
        whitelist  = sum(1 for r in self.results if r["metodo"] == "whitelist")

        avg_score  = (
            sum(r["risk_score"] for r in self.results) / total
            if total > 0 else 0
        )

        log.info("")
        log.info("═" * 64)
        log.info("  RESUMEN DEL RUN")
        log.info("═" * 64)
        log.info("  Total procesados : %d", total)
        log.info("  ├─ Legítimos     : %d", legitimos)
        log.info("  ├─ Spam          : %d", spams)
        log.info("  └─ Sospechosos   : %d", sospechosos)
        log.info("")
        log.info("  Método de clasificación:")
        log.info("  ├─ Whitelist     : %d", whitelist)
        log.info("  ├─ KNN directo   : %d", knn_direct)
        log.info("  └─ Ollama        : %d", ollama_used)
        log.info("")
        log.info("  Risk score promedio: %.1f/100", avg_score)
        log.info("")

        # Detalle por archivo
        log.info("  ─── Detalle por archivo ────────────────────────")
        for r in self.results:
            flag = {"legitimo": "✓", "spam": "~", "sospechoso": "!"}.get(r["clasificacion"], "?")
            log.info(
                "  [%s] %-35s → %-12s (score %3d | %s)",
                flag,
                r["archivo"][:35],
                r["clasificacion"].upper(),
                r["risk_score"],
                r["metodo"]
            )

        log.info("")
        log.info("  Archivos procesados guardados en: analyzed/")
        log.info("  JSON detallados en             : analyzed/json/")
        log.info("  Log completo en                : %s", TEST_LOG)
        log.info("═" * 64)
        log.info("")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="test_agent.py — Prueba local del analizador de phishing"
    )
    parser.add_argument(
        "--suspect-dir", default=str(SUSPECT_DIR),
        help="Carpeta con archivos .txt a analizar (default: suspect/)"
    )
    parser.add_argument(
        "--config", default=CONFIG_PATH,
        help=f"Archivo de configuración (default: {CONFIG_PATH})"
    )
    parser.add_argument(
        "--threshold", type=float, default=None,
        help="Override del umbral de confianza KNN (0.0-1.0)"
    )
    args = parser.parse_args()

    # Override de carpeta si se especificó
    if args.suspect_dir != str(SUSPECT_DIR):
        import test_agent as _self
        _self.SUSPECT_DIR = Path(args.suspect_dir)

    agent = TestAgent()

    # Override de threshold si se especificó por CLI
    if args.threshold is not None:
        agent.knn.confidence_threshold = args.threshold
        log.info("Threshold KNN sobreescrito por CLI: %.0f%%", args.threshold * 100)

    agent.run()


if __name__ == "__main__":
    main()
