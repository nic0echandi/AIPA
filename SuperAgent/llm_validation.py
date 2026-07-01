#!/usr/bin/env python3
"""
llm_validation.py — Módulo de validación cruzada de resultados LLM

Valida clasificaciones del LLM contra múltiples criterios antes de aplicarlas:
  - ¿KNN está de acuerdo?
  - ¿Risk score alineado con clasificación?
  - ¿Heurísticas simples confirman?

Previene que errores del LLM contaminen IRIS y el modelo de ML.
"""

import logging
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
import json
import re
import numpy as np

log = logging.getLogger(__name__)


class LLMValidator:
    """Valida clasificaciones del LLM antes de aplicarlas."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.manual_review_dir = Path(config.get("manual_review_dir", "manual_review"))
        self.manual_review_dir.mkdir(exist_ok=True, parents=True)
    
    def validate(
        self,
        email_headers: Dict,
        email_body: str,
        llm_result: Dict,
        knn_result: Optional[Dict] = None,
        risk_score: Optional[float] = None
    ) -> Dict:
        """
        Valida resultado del LLM en múltiples dimensiones.
        
        Args:
            email_headers: Headers del email
            email_body: Contenido del email
            llm_result: {classification, confidence}
            knn_result: {classification, confidence} o None
            risk_score: Score de riesgo calculado (0-100)
        
        Returns:
            {
                "is_valid": bool,
                "confidence": float (0-1),
                "flags": [list of risk flags],
                "recommendation": "SAFE|REVIEW|REJECT",
                "details": {...}
            }
        """
        
        flags = []
        confidence = 0.0
        
        # Validación 1: KNN vs LLM acuerdan?
        if knn_result:
            knn_ok, knn_conf = self._validate_knn_agreement(knn_result, llm_result)
            if not knn_ok:
                flags.append("knn_disagreement")
            confidence += knn_conf * 0.25
        else:
            confidence += 0.125  # Sin KNN, neutral
        
        # Validación 2: Heurísticas independientes
        heur_ok, heur_conf = self._validate_heuristics(email_headers, email_body, llm_result)
        if not heur_ok:
            flags.append("heuristic_mismatch")
        confidence += heur_conf * 0.25
        
        # Validación 3: Risk score alineado?
        if risk_score is not None:
            risk_ok, risk_conf = self._validate_risk_score(risk_score, llm_result)
            if not risk_ok:
                flags.append("risk_mismatch")
            confidence += risk_conf * 0.25
        else:
            confidence += 0.125  # Sin risk score, neutral
        
        # Validación 4: LLM mismo tiene confianza?
        llm_conf_score = llm_result.get("confidence", 0.5)
        if llm_conf_score < 0.70:
            flags.append("low_llm_confidence")
        confidence += min(llm_conf_score, 1.0) * 0.25
        
        # Decisión final
        error_flags = sum(1 for f in flags if f != "low_llm_confidence")
        
        if error_flags >= 2:
            recommendation = "REVIEW"
        elif error_flags == 1 and confidence < 0.70:
            recommendation = "REVIEW"
        elif confidence > 0.85:
            recommendation = "SAFE"
        else:
            recommendation = "REVIEW"
        
        return {
            "is_valid": recommendation != "REJECT",
            "confidence": confidence,
            "flags": flags,
            "recommendation": recommendation,
            "details": {
                "knn_agreement": knn_result is not None and not any(f == "knn_disagreement" for f in flags),
                "llm_self_confidence": llm_conf_score,
                "heuristic_match": not any(f == "heuristic_mismatch" for f in flags),
                "risk_aligned": not any(f == "risk_mismatch" for f in flags),
            }
        }
    
    def _validate_knn_agreement(self, knn_result: Dict, llm_result: Dict) -> tuple:
        """Verifica si KNN y LLM predicen lo mismo."""
        if knn_result["confidence"] < 0.60:
            # KNN muy inseguro, no validar
            return True, 0.5
        
        knn_class = knn_result["classification"]
        llm_class = llm_result["classification"]
        
        if knn_class == llm_class:
            return True, 1.0
        else:
            log.debug(f"KNN({knn_class}) ≠ LLM({llm_class})")
            return False, 0.2
    
    def _validate_heuristics(self, headers: Dict, body: str, llm_result: Dict) -> tuple:
        """Clasificación simple basada en heurísticas."""
        
        risk_score = 0.0
        
        # Palabras clave phishing
        phishing_words = [
            "verify", "confirm", "urgent", "suspended", "password", "click here",
            "update payment", "security alert", "account locked", "unusual activity"
        ]
        if any(word in body.lower() for word in phishing_words):
            risk_score += 0.3
        
        # URLs sospechosas
        short_url_services = ["bit.ly", "tinyurl.com", "goo.gl", "t.co", "ow.ly"]
        if any(svc in body for svc in short_url_services):
            risk_score += 0.2
        
        # Formularios HTML
        if re.search(r"<form[^>]*>", body, re.IGNORECASE):
            risk_score += 0.3
        
        # Fallos de autenticación
        auth = headers.get("authentication-results", "").lower()
        if "spf=fail" in auth:
            risk_score += 0.2
        if "dkim=fail" in auth:
            risk_score += 0.2
        
        # Mapear risk score a clasificación
        if risk_score > 0.60:
            heur_class = "sospechoso"
        elif risk_score > 0.30:
            heur_class = "spam"
        else:
            heur_class = "legitimo"
        
        # Comparar con LLM
        llm_class = llm_result["classification"]
        
        if heur_class == llm_class:
            return True, 1.0
        elif (heur_class == "legitimo" and llm_class == "spam") or \
             (heur_class == "spam" and llm_class == "legitimo"):
            # Diferencia pequeña
            return True, 0.7
        else:
            log.debug(f"Heurísticas({heur_class}) ≠ LLM({llm_class})")
            return False, 0.3
    
    def _validate_risk_score(self, risk_score: float, llm_result: Dict) -> tuple:
        """Verifica alineación entre risk score y clasificación."""
        classification = llm_result["classification"]
        
        if classification == "sospechoso":
            acceptable = risk_score >= 65
        elif classification == "spam":
            acceptable = 40 <= risk_score <= 75
        else:  # legitimo
            acceptable = risk_score <= 40
        
        confidence = 1.0 if acceptable else 0.3
        return acceptable, confidence
    
    def save_for_review(
        self,
        file_path: Path,
        validation_result: Dict,
        email_data: Dict,
        llm_result: Dict
    ):
        """Guarda email cuestionable para revisión manual."""
        if validation_result["recommendation"] != "REVIEW":
            return
        
        review_file = (
            self.manual_review_dir /
            f"{file_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        
        with open(review_file, "w") as f:
            json.dump({
                "original_file": str(file_path),
                "from": email_data.get("headers", {}).get("From", ""),
                "subject": email_data.get("headers", {}).get("Subject", ""),
                "classification_llm": llm_result.get("classification"),
                "confidence_llm": llm_result.get("confidence"),
                "validation": validation_result,
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
        
        log.warning(f"📋 Email para revisión manual: {review_file}")
        return review_file
