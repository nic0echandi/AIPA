#!/usr/bin/env python3
"""
data_quality.py — Control de calidad de datos de entrenamiento

Valida datos antes de agregarlos al modelo KNN para prevenir que
correcciones incorrectas del LLM contaminen el conjunto de entrenamiento.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import json
import numpy as np

log = logging.getLogger(__name__)


class DataQualityController:
    """Valida datos antes de agregarlos al modelo."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.quarantine_dir = Path(config.get("quarantine_dir", "quarantine"))
        self.quarantine_dir.mkdir(exist_ok=True, parents=True)
        self.quarantine_log = self.quarantine_dir / "quarantine_log.jsonl"
    
    def should_add_to_training(
        self,
        email_headers: Dict,
        classification: str,
        confidence: float,
        risk_score: float
    ) -> Dict:
        """
        Determina si un ejemplo debería agregarse al conjunto de entrenamiento.
        
        Args:
            email_headers: Headers del email
            classification: "legitimo", "spam" o "sospechoso"
            confidence: Confianza de la clasificación (0-1)
            risk_score: Score de riesgo (0-100)
        
        Returns:
            {
                "is_safe": bool,
                "issues": [list of issues],
                "action": "ADD|QUARANTINE|MANUAL_REVIEW"
            }
        """
        
        issues = []
        
        # Verificación 1: Confianza mínima
        if confidence < 0.65:
            issues.append({
                "type": "LOW_CONFIDENCE",
                "value": confidence,
                "threshold": 0.65,
                "severity": "WARNING"
            })
        
        # Verificación 2: Risk score alineado?
        if not self._risk_score_aligns(risk_score, classification):
            issues.append({
                "type": "RISK_MISALIGNED",
                "risk_score": risk_score,
                "classification": classification,
                "severity": "ERROR"
            })
        
        # Verificación 3: Valores anómalos en headers
        if self._has_suspicious_headers(email_headers):
            issues.append({
                "type": "SUSPICIOUS_HEADERS",
                "severity": "WARNING"
            })
        
        # Verificación 4: Headers muy incompletos
        if len(email_headers) < 5:
            issues.append({
                "type": "INCOMPLETE_HEADERS",
                "count": len(email_headers),
                "severity": "ERROR"
            })
        
        # Decisión
        error_count = sum(1 for i in issues if i["severity"] == "ERROR")
        warning_count = sum(1 for i in issues if i["severity"] == "WARNING")
        
        if error_count > 0:
            action = "QUARANTINE"
        elif warning_count > 1 or (warning_count > 0 and confidence < 0.70):
            action = "MANUAL_REVIEW"
        else:
            action = "ADD"
        
        return {
            "is_safe": action == "ADD",
            "issues": issues,
            "action": action
        }
    
    def _risk_score_aligns(self, risk_score: float, classification: str) -> bool:
        """Verifica alineación entre risk score y clasificación."""
        if classification == "sospechoso":
            return risk_score >= 65
        elif classification == "spam":
            return 40 <= risk_score <= 75
        else:  # legitimo
            return risk_score <= 40
    
    def _has_suspicious_headers(self, headers: Dict) -> bool:
        """Detecta valores anómalos en headers."""
        
        # Headers críticos
        critical_headers = ["From", "Subject", "Message-ID"]
        for header in critical_headers:
            if header not in headers or not str(headers.get(header, "")).strip():
                return True
        
        # Headers en blanco o None
        for key, value in headers.items():
            if not value or (isinstance(value, str) and len(value.strip()) == 0):
                return True
        
        return False
    
    def quarantine_example(
        self,
        file_path: Path,
        issues: List[Dict],
        classification: str,
        context: Dict
    ) -> Optional[Path]:
        """Guarda ejemplo problemático en cuarentena."""
        
        quarantine_file = (
            self.quarantine_dir /
            f"{file_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        
        record = {
            "file": str(file_path),
            "classification": classification,
            "quarantine_reasons": issues,
            "context": context,
            "timestamp": datetime.now().isoformat()
        }
        
        with open(quarantine_file, "w") as f:
            json.dump(record, f, indent=2)
        
        # Agregar a log
        with open(self.quarantine_log, "a") as f:
            f.write(json.dumps(record) + "\n")
        
        log.warning(f"⚠️  Ejemplo en cuarentena: {quarantine_file}")
        return quarantine_file
    
    def get_quarantine_summary(self) -> Dict:
        """Genera resumen de ejemplos en cuarentena."""
        if not self.quarantine_log.exists():
            return {"total": 0, "by_reason": {}}
        
        by_reason = {}
        total = 0
        
        try:
            with open(self.quarantine_log) as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        for reason in record.get("quarantine_reasons", []):
                            reason_type = reason["type"]
                            by_reason[reason_type] = by_reason.get(reason_type, 0) + 1
                        total += 1
                    except:
                        pass
        except Exception as exc:
            log.warning(f"Error leyendo quarantine log: {exc}")
        
        return {"total": total, "by_reason": by_reason}
