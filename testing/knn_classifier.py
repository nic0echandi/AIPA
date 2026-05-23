"""
knn_classifier.py — Clasificador KNN para análisis rápido de headers de email
Extrae features numéricas del header y clasifica sin necesidad de LLM.
Si la confianza supera el umbral, el resultado va directo a acción.
Si no, el resultado se pasa a Ollama para análisis profundo.
"""

import re
import json
import math
import logging
import pickle
from pathlib import Path
from typing import Dict, List, Tuple, Optional

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

class KNNClassifier:
    """
    K-Nearest Neighbors para clasificación de emails.
    Usa distancia euclidiana sobre el vector de features.

    En el primer arranque, usa el conjunto de entrenamiento embebido.
    Persiste el modelo en disco para mejorar con el tiempo (aprendizaje activo).
    """

    LABELS = {0: "legitimo", 1: "spam", 2: "sospechoso"}
    MODEL_PATH = Path("knn_model.pkl")

    # Dataset de entrenamiento base (features embebidas)
    # Formato: (vector, label_int)
    # Generado a partir de los dos emails de ejemplo + conocimiento del dominio
    BASE_TRAINING = [
        # -------- LEGÍTIMOS --------
        # zepo.app training email (todos pass, SCL=-1, SFV=SKN)
        ([0,0,0,0,1, 0,0,1,0,1, 0,0,1,0.33,0, 0,0,0,0,0, 0,0,0,0], 0),
        # Microsoft notification estándar
        ([0,0,0,0,1, 0,0,1,0,1, 0,0,1,0,0, 0,0,0,0.1,0, 0,0,0,0], 0),
        # Newsletter SendGrid con buena autenticación
        ([0,0,0,0,1, 0,0,0,0,1, 0,0,1,0,0, 0,0,0,0.3,0, 0,0,0,0], 0),
        # Email interno Office365
        ([0,0,0,0,1, 0,0,1,0,1, 0,0,1,0,0, 0,0,0,0,0, 0,0,0,0], 0),
        # Mailchimp marketing
        ([0,0,0,0,1, 0,0,0,0,0, 0,0,1,0,0, 0,0,0,0.4,0, 0,0,0,0], 0),

        # -------- SPAM --------
        # Marketing masivo sin DKIM
        ([0,0,1,1,0, 0,0,0,0,0, 0,0,1,0,0, 0,0,0,0.5,0, 0,0,0,0], 1),
        # Boletín con SPF softfail pero sin otras señales
        ([0,1,0,1,0, 0,1,0,1,0, 0,0,1,0,0, 0,0,1,0.2,0, 0,0,0,0], 1),
        # Offer email con múltiples URLs
        ([0,1,0,1,0, 0,1,0,1,0, 0,0,1,0.33,0, 0,0,0,0.6,0, 0,0,0,0], 1),
        # Newsletter sin autenticación completa
        ([0,0,1,0,0, 0,0,0,0,0, 0,0,1,0,0, 0,0,0,0.3,0, 0,0,0,0], 1),

        # -------- SOSPECHOSOS / PHISHING --------
        # BEC pago (como el ejemplo del 19/04)
        ([1,0,1,1,0, 1,1,0,1,0, 1,0,0,0.33,1, 0,0,1,0,0, 0,1,1,0], 2),
        # Spear phishing con homógrafo
        ([1,0,1,1,0, 1,1,0,1,0, 1,0,0,0.66,0, 0,0,1,0.2,0, 0,0,0,1], 2),
        # URLs sospechosas detectadas por MS
        ([0,1,0,1,0, 0,1,0,1,0, 0,0,1,0.33,0, 0,0,0,0.4,1, 0.5,0,0,0], 2),
        # Thread hijacking + adjunto + SPF fail
        ([1,0,1,1,0, 1,1,0,1,0, 1,0,0,0,0, 0,1,1,0,0, 0,1,1,0], 2),
        # SPOOF con país de riesgo
        ([1,0,1,1,0, 1,1,0,1,0, 1,0,0,0,0, 1,1,1,0.1,0, 0,0,0,0], 2),
        # URL acortada + SPF fail + display mismatch
        ([1,0,1,0,0, 0,1,0,1,0, 0,0,1,0.66,0, 0,0,1,0.3,0, 1,0,0,1], 2),
    ]

    def __init__(self, k: int = 5, confidence_threshold: float = 0.85):
        self.k = k
        self.confidence_threshold = confidence_threshold
        self.training_data: List[Tuple[List[float], int]] = []
        self._load_or_init()

    def _load_or_init(self):
        """Carga el modelo persistido o inicializa con el dataset base."""
        if self.MODEL_PATH.exists():
            try:
                with open(self.MODEL_PATH, "rb") as f:
                    self.training_data = pickle.load(f)
                log.info("Modelo KNN cargado: %d ejemplos", len(self.training_data))
                return
            except Exception as exc:
                log.warning("No se pudo cargar el modelo KNN: %s — usando dataset base", exc)

        self.training_data = [(v, l) for v, l in self.BASE_TRAINING]
        log.info("Modelo KNN inicializado con %d ejemplos base", len(self.training_data))
        self._save()

    def _save(self):
        try:
            with open(self.MODEL_PATH, "wb") as f:
                pickle.dump(self.training_data, f)
        except Exception as exc:
            log.warning("No se pudo guardar el modelo KNN: %s", exc)

    def _euclidean(self, v1: List[float], v2: List[float]) -> float:
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(v1, v2)))

    def classify(self, vector: List[float]) -> Tuple[str, float]:
        """
        Clasifica un vector de features.
        Retorna (label, confidence) donde confidence ∈ [0, 1].
        """
        if not self.training_data:
            return "spam", 0.0

        # Calcular distancias a todos los ejemplos
        distances = [
            (self._euclidean(vector, v), label)
            for v, label in self.training_data
        ]
        distances.sort(key=lambda x: x[0])

        # Tomar los K más cercanos
        k_nearest = distances[:self.k]

        # Votación ponderada por distancia inversa
        votes: Dict[int, float] = {0: 0.0, 1: 0.0, 2: 0.0}
        for dist, label in k_nearest:
            weight = 1.0 / (dist + 1e-6)  # evitar división por cero
            votes[label] += weight

        total_weight  = sum(votes.values())
        winner_label  = max(votes, key=votes.get)
        confidence    = votes[winner_label] / total_weight if total_weight > 0 else 0.0

        return self.LABELS[winner_label], round(confidence, 4)

    def classify_email(self, headers: Dict, content: str, microsoft_urls: str) -> Dict:
        """
        Interfaz completa: extrae features → clasifica → retorna resultado con metadatos.
        """
        features   = extract_features(headers, content, microsoft_urls)
        vector     = features_to_vector(features)
        label, conf = self.classify(vector)

        is_confident = conf >= self.confidence_threshold

        log.info(
            "KNN → %s (confianza: %.2f%%) [%s]",
            label.upper(), conf * 100,
            "DIRECTO" if is_confident else "→ Ollama"
        )

        return {
            "classification":  label,
            "confidence":      conf,
            "is_confident":    is_confident,  # True = no necesita Ollama
            "features":        features,
            "vector":          vector,
        }

    def add_training_example(self, vector: List[float], label: str):
        """
        Agrega un nuevo ejemplo de entrenamiento (aprendizaje activo).
        Llamado cuando un analista confirma/corrige una clasificación.
        """
        label_int = {v: k for k, v in self.LABELS.items()}.get(label)
        if label_int is None:
            log.warning("Label desconocido para entrenamiento: %s", label)
            return

        self.training_data.append((vector, label_int))
        # Mantener máximo 500 ejemplos (FIFO)
        if len(self.training_data) > 500:
            self.training_data = self.training_data[-500:]

        self._save()
        log.info("Ejemplo agregado al modelo KNN. Total: %d", len(self.training_data))

    def stats(self) -> Dict:
        label_counts = {self.LABELS[i]: 0 for i in range(3)}
        for _, label in self.training_data:
            label_counts[self.LABELS[label]] += 1
        return {"total": len(self.training_data), "by_label": label_counts}
