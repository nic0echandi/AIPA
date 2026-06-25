"""
knn_classifier.py — Clasificador KNN con sklearn para análisis rápido de headers de email
Extrae features numéricas del header y clasifica sin necesidad de LLM.
Implementa aprendizaje activo: mejora con cada ejemplo clasificado.
Reduce progresivamente la dependencia del LLM conforme el modelo se entrena.
"""

import re
import json
import logging
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from sklearn.neighbors import KNeighborsClassifier
from joblib import dump, load

log = logging.getLogger("phishing_analyzer.knn")

# ---------------------------------------------------------------------------
# Extracción de features
# ---------------------------------------------------------------------------

PHISHING_KEYWORDS_SUBJECT = [
    "pago", "urgente", "verify", "suspend", "security alert",
    "confirm identity", "update payment", "account locked",
    "unusual activity", "prize", "winner", "congratulations",
    "felicitaciones", "ganador", "verificar", "ciberseguridad",
    "contraseña", "password", "click here", "limited time",
    "act now", "factura", "invoice", "transferencia"
]

SHORT_URL_SERVICES = [
    "bit.ly", "tinyurl.com", "goo.gl", "t.co", "ow.ly",
    "short.link", "rb.gy", "cutt.ly"
]


def extract_features(headers: Dict, content: str, microsoft_urls: str) -> Dict:
    """
    Extrae un vector de features numéricas del email para el clasificador KNN.
    Retorna dict con nombre → valor (todos numéricos o booleanos).
    """
    features = {}

    # --- Autenticación (3 features) ---
    auth = headers.get("authentication-results", "").lower()
    spf_raw = headers.get("received-spf", "").lower()

    spf_val  = _extract_auth_result(auth, "spf")  or _extract_auth_result(spf_raw, "")
    dkim_val = _extract_auth_result(auth, "dkim")
    dmarc_val = _extract_auth_result(auth, "dmarc")

    features["spf_fail"]      = 1.0 if spf_val  in ("fail", "softfail") else 0.0
    features["spf_softfail"]  = 1.0 if spf_val  == "softfail" else 0.0
    features["dkim_none"]     = 1.0 if dkim_val in ("none", "fail") else 0.0
    features["dmarc_none"]    = 1.0 if dmarc_val in ("none", "fail") else 0.0
    features["auth_all_pass"] = 1.0 if (
        spf_val == "pass" and dkim_val == "pass" and dmarc_val == "pass"
    ) else 0.0
    features["compauth_fail"] = 1.0 if "compauth=fail" in auth else 0.0

    # --- SCL (Spam Confidence Level) de Microsoft ---
    scl_match = re.search(r"SCL:(-?\d+)", headers.get("X-MS-Exchange-Organization-SCL", ""))
    scl = int(scl_match.group(1)) if scl_match else 0
    features["scl_high"]     = 1.0 if scl >= 5 else 0.0
    features["scl_negative"] = 1.0 if scl == -1 else 0.0

    # SFV (Spam Filtering Verdict)
    sfv_match = re.search(r"SFV:(\w+)", headers.get("x-forefront-antispam-report", ""))
    sfv = sfv_match.group(1) if sfv_match else ""
    features["sfv_spam"]     = 1.0 if sfv in ("SPM", "SKS") else 0.0
    features["sfv_skip"]     = 1.0 if sfv == "SKN" else 0.0

    # CAT (Threat Category)
    cat_match = re.search(r"CAT:(\w+)", headers.get("x-forefront-antispam-report", ""))
    cat = cat_match.group(1) if cat_match else "NONE"
    features["cat_spoof"]    = 1.0 if cat == "SPOOF" else 0.0
    features["cat_phish"]    = 1.0 if cat in ("PHSH", "MALW") else 0.0
    features["cat_none"]     = 1.0 if cat == "NONE" else 0.0

    # --- Asunto sospechoso ---
    subject = headers.get("Subject", "").lower()
    kw_hits = sum(1 for kw in PHISHING_KEYWORDS_SUBJECT if kw in subject)
    features["subject_keywords"] = min(kw_hits / 3.0, 1.0)  # normalizado

    # Asunto muy corto (ej: "pago", "urgente")
    features["subject_very_short"] = 1.0 if len(subject.strip()) <= 6 else 0.0

    # --- Reply-To diferente al From ---
    from_addr    = headers.get("From", "").lower()
    reply_to     = headers.get("Reply-To", "").lower()
    from_domain  = _extract_domain(from_addr)
    reply_domain = _extract_domain(reply_to)
    features["reply_to_mismatch"] = (
        1.0 if (reply_domain and from_domain and reply_domain != from_domain) else 0.0
    )

    # --- Infraestructura del sender ---
    # IP desde forefront
    ip_match = re.search(r"CIP:([\d.]+)", headers.get("x-forefront-antispam-report", ""))
    sender_ip = ip_match.group(1) if ip_match else ""

    # País (DE, RU, CN → sospechoso para emails corporativos argentinos)
    country_match = re.search(r"CTRY:(\w+)", headers.get("x-forefront-antispam-report", ""))
    country = country_match.group(1) if country_match else ""
    HIGH_RISK_COUNTRIES = {"RU", "CN", "KP", "IR", "NG", "BY", "UA"}
    features["high_risk_country"] = 1.0 if country in HIGH_RISK_COUNTRIES else 0.0

    # IPV:NLI = IP not listed (no en la lista blanca de remitentes)
    features["ipv_nli"] = 1.0 if "IPV:NLI" in headers.get("x-forefront-antispam-report", "") else 0.0

    # --- URLs ---
    url_pattern = r"https?://[^\s<>\"{}|\\^`\[\]]+"
    urls = re.findall(url_pattern, content)
    features["url_count_norm"]   = min(len(urls) / 10.0, 1.0)
    features["ms_urls_detected"] = 1.0 if microsoft_urls not in ("None", "") else 0.0

    # URLs acortadas
    short_url_count = sum(
        1 for u in urls
        if any(svc in u for svc in SHORT_URL_SERVICES)
    )
    features["short_urls"] = min(short_url_count / 2.0, 1.0)

    # --- Adjunto ---
    has_attach = headers.get("X-MS-Has-Attach", "").strip().lower()
    features["has_attachment"] = 1.0 if has_attach == "yes" else 0.0

    # --- Thread hijacking (In-Reply-To apunta a dominio externo) ---
    in_reply_to = headers.get("In-Reply-To", "").lower()
    if in_reply_to and from_domain:
        reply_ref_domain = _extract_domain(in_reply_to)
        if reply_ref_domain and reply_ref_domain != from_domain:
            features["thread_hijacking"] = 1.0
        else:
            features["thread_hijacking"] = 0.0
    else:
        features["thread_hijacking"] = 0.0

    # --- Display name ≠ email address ---
    dn_mismatch = 0.0
    dn_match    = re.search(r'^"?([^"<]+)"?\s*<', from_addr)
    email_match = re.search(r'<([^>]+)>', from_addr)
    if dn_match and email_match:
        display = dn_match.group(1).strip()
        email   = email_match.group(1).strip()
        if "@" in display and display != email:
            dn_mismatch = 1.0
    features["display_name_mismatch"] = dn_mismatch

    return features


def _extract_auth_result(text: str, proto: str) -> str:
    """Extrae el resultado de autenticación (pass/fail/softfail/none) para un protocolo."""
    prefix = f"{proto}=" if proto else ""
    for result in ("pass", "fail", "softfail", "none", "neutral", "permerror", "temperror"):
        if f"{prefix}{result}" in text:
            return result
    return "unknown"


def _extract_domain(addr: str) -> str:
    m = re.search(r"@([a-zA-Z0-9.-]+)", addr)
    return m.group(1).lower() if m else ""


# ---------------------------------------------------------------------------
# Feature vector (lista ordenada para el clasificador)
# ---------------------------------------------------------------------------

FEATURE_NAMES = [
    "spf_fail", "spf_softfail", "dkim_none", "dmarc_none", "auth_all_pass",
    "compauth_fail", "scl_high", "scl_negative", "sfv_spam", "sfv_skip",
    "cat_spoof", "cat_phish", "cat_none", "subject_keywords", "subject_very_short",
    "reply_to_mismatch", "high_risk_country", "ipv_nli", "url_count_norm",
    "ms_urls_detected", "short_urls", "has_attachment", "thread_hijacking",
    "display_name_mismatch"
]


def features_to_vector(features: Dict) -> List[float]:
    return [features.get(name, 0.0) for name in FEATURE_NAMES]


# ---------------------------------------------------------------------------
# Clasificador KNN
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Clasificador KNN con sklearn
# ---------------------------------------------------------------------------

class KNNClassifier:
    """
    K-Nearest Neighbors para clasificación de emails usando scikit-learn.
    
    Características:
    - Modelo sklearn optimizado con KDTree
    - Aprendizaje activo: mejora con cada ejemplo clasificado
    - Ajuste dinámico del umbral de confianza según precisión
    - Estadísticas de rendimiento para optimizar el modelo
    
    En el primer arranque, usa el conjunto de entrenamiento embebido.
    Persiste el modelo con joblib para mejorar con el tiempo.
    """

    LABELS = {0: "legitimo", 1: "spam", 2: "sospechoso"}
    LABEL_TO_INT = {v: k for k, v in LABELS.items()}
    
    MODEL_PATH = Path("knn_model.joblib")
    STATS_PATH = Path("knn_stats.json")

    # Dataset de entrenamiento base (features embebidas)
    BASE_TRAINING = [
        # -------- LEGÍTIMOS --------
        ([0,0,0,0,1, 0,0,1,0,1, 0,0,1,0.33,0, 0,0,0,0,0, 0,0,0,0], 0),
        ([0,0,0,0,1, 0,0,1,0,1, 0,0,1,0,0, 0,0,0,0.1,0, 0,0,0,0], 0),
        ([0,0,0,0,1, 0,0,0,0,1, 0,0,1,0,0, 0,0,0,0.3,0, 0,0,0,0], 0),
        ([0,0,0,0,1, 0,0,1,0,1, 0,0,1,0,0, 0,0,0,0,0, 0,0,0,0], 0),
        ([0,0,0,0,1, 0,0,0,0,0, 0,0,1,0,0, 0,0,0,0.4,0, 0,0,0,0], 0),

        # -------- SPAM --------
        ([0,0,1,1,0, 0,0,0,0,0, 0,0,1,0,0, 0,0,0,0.5,0, 0,0,0,0], 1),
        ([0,1,0,1,0, 0,1,0,1,0, 0,0,1,0,0, 0,0,1,0.2,0, 0,0,0,0], 1),
        ([0,1,0,1,0, 0,1,0,1,0, 0,0,1,0.33,0, 0,0,0,0.6,0, 0,0,0,0], 1),
        ([0,0,1,0,0, 0,0,0,0,0, 0,0,1,0,0, 0,0,0,0.3,0, 0,0,0,0], 1),

        # -------- SOSPECHOSOS / PHISHING --------
        ([1,0,1,1,0, 1,1,0,1,0, 1,0,0,0.33,1, 0,0,1,0,0, 0,1,1,0], 2),
        ([1,0,1,1,0, 1,1,0,1,0, 1,0,0,0.66,0, 0,0,1,0.2,0, 0,0,0,1], 2),
        ([0,1,0,1,0, 0,1,0,1,0, 0,0,1,0.33,0, 0,0,0,0.4,1, 0.5,0,0,0], 2),
        ([1,0,1,1,0, 1,1,0,1,0, 1,0,0,0,0, 0,1,1,0,0, 0,1,1,0], 2),
        ([1,0,1,1,0, 1,1,0,1,0, 1,0,0,0,0, 1,1,1,0.1,0, 0,0,0,0], 2),
        ([1,0,1,0,0, 0,1,0,1,0, 0,0,1,0.66,0, 0,0,1,0.3,0, 1,0,0,1], 2),
    ]

    def __init__(self, k: int = 5, confidence_threshold: float = 0.85):
        """
        Inicializa el clasificador KNN.
        
        Args:
            k: número de vecinos a considerar
            confidence_threshold: umbral de confianza inicial (ajustable dinámicamente)
        """
        self.k = k
        self.base_confidence_threshold = confidence_threshold
        self.current_confidence_threshold = confidence_threshold
        
        # Modelo sklearn
        self.model: Optional[KNeighborsClassifier] = None
        self.X_train = np.array([])
        self.y_train = np.array([])
        
        # Estadísticas de aprendizaje activo
        self.stats = {
            "total_examples": 0,
            "by_label": {"legitimo": 0, "spam": 0, "sospechoso": 0},
            "training_count": 0,  # Ejemplos agregados desde init
            "accuracy_history": [],  # [fecha, confianza_promedio, correctas, totales]
            "threshold_adjustments": [],  # Historial de cambios de umbral
            "last_retrain": datetime.now().isoformat(),
        }
        
        self._load_or_init()

    def _load_or_init(self):
        """Carga modelo persistido o inicializa con dataset base."""
        if self.MODEL_PATH.exists():
            try:
                data = load(self.MODEL_PATH)
                self.X_train = data["X_train"]
                self.y_train = data["y_train"]
                self.model = data["model"]
                
                # Cargar estadísticas
                if self.STATS_PATH.exists():
                    with open(self.STATS_PATH, "r", encoding="utf-8") as f:
                        self.stats = json.load(f)
                
                # Ajustar threshold dinámicamente basado en histórico
                self._adjust_threshold_dynamically()
                
                log.info(
                    "Modelo KNN cargado: %d ejemplos | "
                    "Threshold: %.2f%% | %s",
                    len(self.y_train),
                    self.current_confidence_threshold * 100,
                    ", ".join(f"{k}:{v}" for k, v in self.stats["by_label"].items())
                )
                return
            except Exception as exc:
                log.warning("No se pudo cargar modelo KNN: %s — usando dataset base", exc)

        # Inicializar con dataset base
        self._init_from_base_training()
        log.info(
            "Modelo KNN inicializado con %d ejemplos base",
            len(self.y_train)
        )

    def _init_from_base_training(self):
        """Inicializa desde el dataset base embebido."""
        X = np.array([v for v, _ in self.BASE_TRAINING])
        y = np.array([l for _, l in self.BASE_TRAINING])
        
        self._retrain(X, y)
        
        # Inicializar estadísticas
        for vector, label in self.BASE_TRAINING:
            label_name = self.LABELS[label]
            self.stats["by_label"][label_name] = self.stats["by_label"].get(label_name, 0) + 1
        self.stats["total_examples"] = len(self.BASE_TRAINING)
        
        self._save()

    def _retrain(self, X: np.ndarray, y: np.ndarray):
        """Retraina el modelo con nuevos datos."""
        self.X_train = X.astype(np.float64)
        self.y_train = y.astype(np.int32)
        
        self.model = KNeighborsClassifier(
            n_neighbors=min(self.k, len(self.y_train)),
            weights='distance',  # Votación ponderada por distancia inversa
            metric='euclidean',
            algorithm='auto'  # sklearn elige automáticamente: kd_tree, ball_tree, brute
        )
        self.model.fit(self.X_train, self.y_train)
        self.stats["last_retrain"] = datetime.now().isoformat()

    def _save(self):
        """Persiste el modelo y estadísticas."""
        try:
            data = {
                "X_train": self.X_train,
                "y_train": self.y_train,
                "model": self.model,
            }
            dump(data, self.MODEL_PATH)
            
            with open(self.STATS_PATH, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, indent=2)
            
            log.debug("Modelo KNN guardado")
        except Exception as exc:
            log.warning("No se pudo guardar modelo KNN: %s", exc)

    def classify(self, vector: List[float]) -> Tuple[str, float]:
        """
        Clasifica un vector de features.
        
        Args:
            vector: lista de 24 features normalizados
            
        Returns:
            (label, confidence) donde confidence ∈ [0, 1]
        """
        if self.model is None or len(self.y_train) == 0:
            return "spam", 0.0

        X = np.array([vector], dtype=np.float64)
        
        # predict_proba retorna probabilidades para cada clase
        proba = self.model.predict_proba(X)[0]
        prediction = self.model.predict(X)[0]
        
        label = self.LABELS[prediction]
        confidence = float(proba[prediction])
        
        return label, round(confidence, 4)

    def classify_email(self, headers: Dict, content: str, microsoft_urls: str) -> Dict:
        """
        Interfaz completa: extrae features → clasifica → retorna resultado detallado.
        """
        features = extract_features(headers, content, microsoft_urls)
        vector = features_to_vector(features)
        label, conf = self.classify(vector)

        # Umbral dinámico: conforme el modelo crece, es menos exigente
        # Esto reduce dependencia del LLM con más datos de entrenamiento
        is_confident = conf >= self.current_confidence_threshold
        
        llm_required = "→ LLM" if not is_confident else "DIRECTO"
        training_size_indicator = f"({len(self.y_train)} ejemplos)"

        log.info(
            "KNN → %s (%.2f%%) [%s] %s",
            label.upper(), conf * 100, llm_required, training_size_indicator
        )

        return {
            "classification": label,
            "confidence": conf,
            "is_confident": is_confident,
            "features": features,
            "vector": vector,
            "model_size": len(self.y_train),
        }

    def add_training_example(self, vector: List[float], label: str, feedback_correct: bool = True):
        """
        Agrega nuevo ejemplo (aprendizaje activo).
        
        Args:
            vector: features del email
            label: clasificación confirmada (legitimo/spam/sospechoso)
            feedback_correct: si True, mejora score de confianza; si False, lo reduce
        """
        label_int = self.LABEL_TO_INT.get(label)
        if label_int is None:
            log.warning("Label desconocido: %s", label)
            return

        # Agregar ejemplo
        new_X = np.array([vector], dtype=np.float64)
        new_y = np.array([label_int], dtype=np.int32)
        
        self.X_train = np.vstack([self.X_train, new_X]) if len(self.X_train) > 0 else new_X
        self.y_train = np.hstack([self.y_train, new_y]) if len(self.y_train) > 0 else new_y
        
        # Limitar a 1000 ejemplos (FIFO si supera)
        if len(self.y_train) > 1000:
            self.X_train = self.X_train[-1000:]
            self.y_train = self.y_train[-1000:]
        
        self._retrain(self.X_train, self.y_train)
        
        # Actualizar estadísticas
        self.stats["total_examples"] = len(self.y_train)
        self.stats["by_label"][label] = self.stats["by_label"].get(label, 0) + 1
        self.stats["training_count"] = self.stats.get("training_count", 0) + 1
        
        # Ajustar threshold dinámicamente
        if self.stats["training_count"] % 10 == 0:  # Cada 10 ejemplos
            self._adjust_threshold_dynamically()
        
        self._save()
        log.info(
            "Ejemplo agregado (%s). Modelo: %d ejemplos | Threshold: %.2f%%",
            label, len(self.y_train), self.current_confidence_threshold * 100
        )

    def record_feedback(self, predicted_label: str, actual_label: str):
        """
        Registra feedback sobre una predicción para mejorar el modelo.
        
        Args:
            predicted_label: lo que el modelo predijo
            actual_label: lo que realmente era (según un analista)
        """
        is_correct = predicted_label == actual_label
        
        # Registrar en histórico
        entry = {
            "date": datetime.now().isoformat(),
            "predicted": predicted_label,
            "actual": actual_label,
            "correct": is_correct,
        }
        
        if "feedback_history" not in self.stats:
            self.stats["feedback_history"] = []
        
        self.stats["feedback_history"].append(entry)
        
        # Mantener últimos 100 feedbacks
        if len(self.stats["feedback_history"]) > 100:
            self.stats["feedback_history"] = self.stats["feedback_history"][-100:]
        
        # Calcular precisión reciente (últimos 20 feedbacks)
        recent = self.stats["feedback_history"][-20:]
        if recent:
            accuracy = sum(1 for fb in recent if fb["correct"]) / len(recent)
            log.info(
                "Precisión reciente (últimos 20): %.2f%%",
                accuracy * 100
            )
        
        self._save()

    def _adjust_threshold_dynamically(self):
        """
        Ajusta dinámicamente el umbral de confianza.
        
        Estrategia:
        - Con <50 ejemplos: threshold alto (0.95) → necesita LLM
        - Con 50-200 ejemplos: threshold medio (0.85)
        - Con >200 ejemplos: threshold bajo (0.70) → confía más en KNN
        
        Esto reduce dependencia del LLM conforme el modelo crece.
        """
        total = len(self.y_train)
        old_threshold = self.current_confidence_threshold
        
        if total < 50:
            self.current_confidence_threshold = 0.95
        elif total < 200:
            self.current_confidence_threshold = 0.85
        elif total < 500:
            self.current_confidence_threshold = 0.75
        else:
            # Con muchos ejemplos, reduce dependencia del LLM
            self.current_confidence_threshold = 0.65
        
        if old_threshold != self.current_confidence_threshold:
            log.info(
                "Threshold ajustado dinámicamente: %.2f%% → %.2f%% "
                "(%d ejemplos de entrenamiento)",
                old_threshold * 100,
                self.current_confidence_threshold * 100,
                total
            )
            self.stats["threshold_adjustments"].append({
                "date": datetime.now().isoformat(),
                "from": old_threshold,
                "to": self.current_confidence_threshold,
                "training_size": total,
            })

    def stats_summary(self) -> Dict:
        """Retorna resumen de estadísticas del modelo."""
        return {
            "total_examples": len(self.y_train),
            "by_label": self.stats["by_label"],
            "training_count": self.stats.get("training_count", 0),
            "current_threshold": round(self.current_confidence_threshold, 4),
            "base_threshold": round(self.base_confidence_threshold, 4),
            "last_retrain": self.stats.get("last_retrain", "N/A"),
            "feedback_count": len(self.stats.get("feedback_history", [])),
        }
