#!/usr/bin/env python3
"""
usage_stats.py — Gestor de estadísticas de uso para SuperAgent_2

Registra y reporta:
- Cantidad de casos por clasificación (legitimo, spam, sospechoso)
- Cantidad resuelta por fuente (whitelist, knn, llm)
- Mes calendario
- Precisión del KNN
- Estadísticas generales
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
import sys

log = logging.getLogger("superagent_2.stats")


class UsageStats:
    """
    Gestor de estadísticas de uso mes a mes.
    
    Estructura:
    {
      "2026": {
        "06": {  # mes (01-12)
          "total": 150,
          "by_classification": {
            "legitimo": 50,
            "spam": 60,
            "sospechoso": 40
          },
          "by_source": {
            "whitelist": 30,
            "knn": 80,
            "llm": 40
          },
          "knn_accuracy": {
            "correct": 75,
            "incorrect": 5
          }
        }
      }
    }
    """
    
    # Ruta absoluta del archivo stats.json basada en la ubicación del módulo
    STATS_FILE = Path(__file__).resolve().parent / "stats.json"
    
    def __init__(self):
        """Inicializa estadísticas desde archivo o crea nuevas."""
        self.stats: Dict = {}
        self._load_or_init()
    
    def _load_or_init(self):
        """Carga estadísticas del archivo o inicializa vacías."""
        if self.STATS_FILE.exists():
            try:
                with open(self.STATS_FILE, "r", encoding="utf-8") as f:
                    self.stats = json.load(f)
                log.debug(f"Estadísticas cargadas desde {self.STATS_FILE}")
            except Exception as exc:
                log.warning(f"No se pudo cargar {self.STATS_FILE}: {exc}. Iniciando vacío.")
                self.stats = {}
        else:
            self.stats = {}
    
    def _save(self):
        """Persiste estadísticas en JSON."""
        try:
            with open(self.STATS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, indent=2)
        except Exception as exc:
            log.error(f"Error guardando estadísticas: {exc}")
    
    def _get_month_key(self) -> tuple:
        """Retorna (año, mes) del actual."""
        now = datetime.now()
        return (str(now.year), f"{now.month:02d}")
    
    def _ensure_month_exists(self, year: str, month: str):
        """Asegura que la estructura del mes existe."""
        if year not in self.stats:
            self.stats[year] = {}
        if month not in self.stats[year]:
            self.stats[year][month] = {
                "total": 0,
                "by_classification": {
                    "legitimo": 0,
                    "spam": 0,
                    "sospechoso": 0
                },
                "by_source": {
                    "whitelist": 0,
                    "knn": 0,
                    "llm": 0
                },
                "knn_accuracy": {
                    "correct": 0,
                    "incorrect": 0
                }
            }
    
    def record_case(
        self,
        classification: str,
        source: str,
        knn_was_correct: Optional[bool] = None
    ):
        """
        Registra un caso procesado.
        
        Args:
            classification: "legitimo", "spam" o "sospechoso"
            source: "whitelist", "knn" o "llm"
            knn_was_correct: True si KNN acertó, False si se equivocó, None si no aplica
        """
        year, month = self._get_month_key()
        self._ensure_month_exists(year, month)
        
        month_stats = self.stats[year][month]
        
        # Incrementar total y clasificación
        month_stats["total"] += 1
        month_stats["by_classification"][classification] = \
            month_stats["by_classification"].get(classification, 0) + 1
        
        # Incrementar fuente
        month_stats["by_source"][source] = \
            month_stats["by_source"].get(source, 0) + 1
        
        # Si hay feedback de KNN, registrarlo
        if knn_was_correct is not None:
            if knn_was_correct:
                month_stats["knn_accuracy"]["correct"] += 1
            else:
                month_stats["knn_accuracy"]["incorrect"] += 1
        
        self._save()
        
        log.debug(
            f"Caso registrado: {classification} via {source} "
            f"(KNN {'✓' if knn_was_correct else '✗' if knn_was_correct is False else 'N/A'})"
        )
    
    def get_month_summary(self, year: Optional[str] = None, month: Optional[str] = None) -> Dict:
        """
        Retorna resumen de estadísticas de un mes.
        Si no se especifica, usa el mes actual.
        """
        if year is None or month is None:
            year, month = self._get_month_key()
        
        if year not in self.stats or month not in self.stats[year]:
            return {
                "year": year,
                "month": month,
                "total": 0,
                "by_classification": {},
                "by_source": {},
                "knn_accuracy": {}
            }
        
        data = self.stats[year][month]
        
        # Calcular porcentajes
        total = data["total"]
        summary = {
            "year": year,
            "month": month,
            "total": total,
            "by_classification": data["by_classification"],
            "by_classification_pct": {
                k: round(v / total * 100, 1) if total > 0 else 0
                for k, v in data["by_classification"].items()
            },
            "by_source": data["by_source"],
            "by_source_pct": {
                k: round(v / total * 100, 1) if total > 0 else 0
                for k, v in data["by_source"].items()
            },
            "knn_accuracy": data["knn_accuracy"],
        }
        
        # Precisión del KNN
        knn_total = data["knn_accuracy"]["correct"] + data["knn_accuracy"]["incorrect"]
        if knn_total > 0:
            summary["knn_accuracy_pct"] = round(
                data["knn_accuracy"]["correct"] / knn_total * 100, 1
            )
        else:
            summary["knn_accuracy_pct"] = 0
        
        return summary
    
    def get_year_summary(self, year: Optional[str] = None) -> Dict:
        """Retorna resumen anual agregado."""
        if year is None:
            year = str(datetime.now().year)
        
        if year not in self.stats:
            return {
                "year": year,
                "total": 0,
                "by_classification": {},
                "by_source": {},
                "by_month": {}
            }
        
        # Agregar todos los meses
        year_data = self.stats[year]
        
        totals = {
            "total": 0,
            "by_classification": {"legitimo": 0, "spam": 0, "sospechoso": 0},
            "by_source": {"whitelist": 0, "knn": 0, "llm": 0},
        }
        
        for month, month_data in year_data.items():
            totals["total"] += month_data["total"]
            for cls, count in month_data["by_classification"].items():
                totals["by_classification"][cls] += count
            for src, count in month_data["by_source"].items():
                totals["by_source"][src] += count
        
        # Calcular porcentajes
        total = totals["total"]
        summary = {
            "year": year,
            "total": total,
            "by_classification": totals["by_classification"],
            "by_classification_pct": {
                k: round(v / total * 100, 1) if total > 0 else 0
                for k, v in totals["by_classification"].items()
            },
            "by_source": totals["by_source"],
            "by_source_pct": {
                k: round(v / total * 100, 1) if total > 0 else 0
                for k, v in totals["by_source"].items()
            },
            "by_month": {}
        }
        
        # Incluir resumen de cada mes
        for month in sorted(year_data.keys()):
            month_summary = self.get_month_summary(year, month)
            summary["by_month"][month] = {
                "total": month_summary["total"],
                "by_classification": month_summary["by_classification"],
                "by_source": month_summary["by_source"],
            }
        
        return summary
    
    def generate_report(self, output_file: Optional[str] = None) -> str:
        """
        Genera reporte textual formateado.
        
        Args:
            output_file: si se especifica, guarda el reporte en archivo
            
        Returns:
            Reporte como string
        """
        year, month = self._get_month_key()
        
        report = []
        report.append("=" * 70)
        report.append("REPORTE DE ESTADÍSTICAS - SuperAgent_2")
        report.append("=" * 70)
        report.append("")
        
        # Resumen anual
        year_summary = self.get_year_summary(year)
        report.append(f"📊 RESUMEN ANUAL {year}")
        report.append(f"  Total casos: {year_summary['total']}")
        report.append("")
        report.append("  Clasificación:")
        for cls, count in year_summary["by_classification"].items():
            pct = year_summary["by_classification_pct"][cls]
            report.append(f"    • {cls:12} {count:4} ({pct:5.1f}%)")
        report.append("")
        report.append("  Fuente de decisión:")
        for src, count in year_summary["by_source"].items():
            pct = year_summary["by_source_pct"][src]
            report.append(f"    • {src:12} {count:4} ({pct:5.1f}%)")
        report.append("")
        
        # Resumen mes actual
        month_summary = self.get_month_summary(year, month)
        month_name = datetime.strptime(month, "%m").strftime("%B")
        
        report.append(f"📅 MES ACTUAL ({month_name} {year})")
        report.append(f"  Total casos: {month_summary['total']}")
        report.append("")
        report.append("  Clasificación:")
        for cls, count in month_summary["by_classification"].items():
            pct = month_summary["by_classification_pct"][cls]
            report.append(f"    • {cls:12} {count:4} ({pct:5.1f}%)")
        report.append("")
        report.append("  Fuente de decisión:")
        for src, count in month_summary["by_source"].items():
            pct = month_summary["by_source_pct"][src]
            report.append(f"    • {src:12} {count:4} ({pct:5.1f}%)")
        report.append("")
        
        # KNN Accuracy
        knn_acc = month_summary["knn_accuracy"]
        report.append("🎯 Precisión del KNN (mes actual):")
        report.append(f"  • Correctas: {knn_acc['correct']}")
        report.append(f"  • Incorrectas: {knn_acc['incorrect']}")
        report.append(f"  • Tasa de acierto: {month_summary['knn_accuracy_pct']:.1f}%")
        report.append("")
        
        # Historial por mes
        report.append("📆 HISTORIAL POR MES (últimos 6 meses)")
        report.append("")
        
        months_to_show = sorted(year_summary["by_month"].keys(), reverse=True)[:6]
        for m in months_to_show:
            m_summary = year_summary["by_month"][m]
            m_name = datetime.strptime(m, "%m").strftime("%B")
            report.append(f"  {m_name:10} | Total: {m_summary['total']:4} | "
                         f"L:{m_summary['by_classification']['legitimo']:3} "
                         f"S:{m_summary['by_classification']['spam']:3} "
                         f"P:{m_summary['by_classification']['sospechoso']:3} | "
                         f"WL:{m_summary['by_source']['whitelist']:3} "
                         f"KNN:{m_summary['by_source']['knn']:3} "
                         f"LLM:{m_summary['by_source']['llm']:3}")
        
        report.append("")
        report.append("=" * 70)
        report.append(f"Generado: {datetime.now().isoformat()}")
        report.append("=" * 70)
        
        report_text = "\n".join(report)
        
        # Guardar en archivo si se especifica
        if output_file:
            try:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(report_text)
                log.info(f"Reporte guardado en: {output_file}")
            except Exception as exc:
                log.error(f"Error guardando reporte: {exc}")
        
        return report_text
    
    def stats_summary(self) -> Dict:
        """Retorna resumen simple para logging."""
        year, month = self._get_month_key()
        month_summary = self.get_month_summary(year, month)
        year_summary = self.get_year_summary(year)
        
        return {
            "mes_actual": month_summary,
            "año_actual": year_summary
        }
