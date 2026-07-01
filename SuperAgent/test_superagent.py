#!/usr/bin/env python3
"""
test_superagent.py - Script de testing para SuperAgent

Procesa emails de test_emails/ sin interferir con ingress/
Útil para:
  - Testing de nuevas features
  - Reentrenamiento del modelo KNN
  - Validación de cambios
  - Debugging

Uso:
  python test_superagent.py [opciones]

Opciones:
  --config config.json          Archivo de configuración
  --input test_emails           Directorio de entrada (default: test_emails)
  --output test_results         Directorio de salida (default: test_results)
  --mode quick                  Modo rápido (sin LLM, solo KNN)
  --mode full                   Modo completo (con LLM, sin entrenar)
  --mode train                  Modo entrenamiento (procesa y ENTRENA KNN)
  --debug                       Mostrar información de debug
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger("test_superagent")

# Importar módulos locales
try:
    from superagent import SuperAgent2, load_config
    from phishingAnalizer import PhishingAnalyzerTXT
    from knn_classifier import KNNClassifier, extract_features, features_to_vector, FEATURE_NAMES
except ImportError as e:
    log.error(f"Error importando módulos: {e}")
    sys.exit(1)


class TestRunner:
    """Ejecuta tests de SuperAgent"""
    
    def __init__(self, config_path, input_dir, output_dir, mode="full", debug=False):
        self.config = load_config(config_path)
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.mode = mode
        self.debug = debug
        
        # Crear directorio de salida
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Componentes
        self.knn = KNNClassifier(
            k=5,
            confidence_threshold=float(self.config.get("knn_confidence_threshold", 0.85))
        )
        self.analyzer = PhishingAnalyzerTXT(config_path)
        
        # Resultados
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "mode": mode,
            "emails_tested": 0,
            "by_classification": {"legitimo": 0, "spam": 0, "sospechoso": 0},
            "by_source": {"knn": 0, "llm": 0, "error": 0},
            "training": {
                "enabled": mode == "train",
                "examples_added": 0,
                "knn_before": None,
                "knn_after": None
            },
            "errors": [],
            "details": []
        }
        
        # Guardar estadísticas KNN antes de entrenar
        if mode == "train":
            self.results["training"]["knn_before"] = self.knn.stats_summary()
    
    def run(self):
        """Ejecutar tests"""
        
        if not self.input_dir.exists():
            log.error(f"Directorio no existe: {self.input_dir}")
            return False
        
        # Obtener emails
        email_files = sorted(self.input_dir.glob("*.txt"))
        
        if not email_files:
            log.warning(f"No hay emails en {self.input_dir}")
            return False
        
        log.info(f"{'='*70}")
        log.info(f"TEST RUNNER - Modo: {self.mode.upper()}")
        log.info(f"Directorio: {self.input_dir}")
        log.info(f"Emails encontrados: {len(email_files)}")
        if self.mode == "train":
            log.info(f"⚠️  MODO TRAINING: KNN será actualizado con {len(email_files)} ejemplos")
        log.info(f"{'='*70}")
        
        # Procesar cada email
        for i, email_file in enumerate(email_files, 1):
            log.info(f"\n[{i}/{len(email_files)}] Procesando {email_file.name}...")
            
            try:
                result = self._process_email(email_file)
                self.results["details"].append(result)
                self.results["emails_tested"] += 1
                
                # Actualizar estadísticas
                classification = result.get("classification")
                if classification:
                    self.results["by_classification"][classification] += 1
                    source = result.get("source")
                    if source:
                        self.results["by_source"][source] += 1
                
                log.info(f"  ✓ {classification.upper()} (confianza: {result.get('confidence', 0):.0%})")
                
            except Exception as e:
                log.error(f"  ✗ Error: {e}")
                self.results["errors"].append({
                    "file": email_file.name,
                    "error": str(e)
                })
                self.results["by_source"]["error"] += 1
        
        # Si es modo train: guardar modelo actualizado
        if self.mode == "train":
            self.results["training"]["knn_after"] = self.knn.stats_summary()
            self.results["training"]["examples_added"] = self.results["emails_tested"]
            self._save_knn_model()
        
        # Guardar resultados
        self._save_results()
        self._print_summary()
        
        return True
    
    def _process_email(self, email_file):
        """Procesar un email"""
        
        # Parsear
        parsed = self.analyzer.parse_txt_file(str(email_file))
        if not parsed:
            raise ValueError("No se pudo parsear")
        
        headers = parsed["headers"]
        content = parsed["raw_content"]
        microsoft_urls = parsed["microsoft_urls"]
        
        # KNN
        knn_result = self.knn.classify_email(headers, content, microsoft_urls)
        
        result = {
            "file": email_file.name,
            "timestamp": datetime.now().isoformat(),
            "classification": None,
            "confidence": 0.0,
            "source": None,
            "knn": {
                "classification": knn_result.get("classification"),
                "confidence": knn_result.get("confidence"),
                "is_confident": knn_result.get("is_confident")
            }
        }
        
        # Modo quick: solo KNN
        if self.mode == "quick":
            result["classification"] = knn_result["classification"]
            result["confidence"] = knn_result["confidence"]
            result["source"] = "knn"
            return result
        
        # Modo full y train: KNN + LLM si es necesario
        if knn_result["is_confident"]:
            result["classification"] = knn_result["classification"]
            result["confidence"] = knn_result["confidence"]
            result["source"] = "knn"
        else:
            # Análisis profundo
            analysis = self.analyzer.analyze_txt_file(str(email_file))
            if analysis:
                result["classification"] = analysis.classification
                result["confidence"] = analysis.confidence
                result["source"] = "llm"
                result["llm"] = {
                    "risk_score": analysis.risk_score,
                    "reasons": analysis.reasons[:3]  # Primeros 3 motivos
                }
            else:
                raise ValueError("LLM no respondió")
        
        # ✨ NUEVO: Si es modo TRAIN, agregar al modelo
        if self.mode == "train":
            try:
                # Extraer features
                features_dict = extract_features(headers, content, microsoft_urls)
                features_vector = features_to_vector(features_dict)
                
                # Agregar al entrenamiento
                self.knn.add_training_example(
                    features_vector,
                    result["classification"],
                    feedback_correct=True  # Asumimos que la clasificación es correcta
                )
                
                result["training_added"] = True
                log.debug(f"  → Agregado al entrenamiento: {result['classification']}")
                
            except Exception as e:
                log.warning(f"  ⚠️  No se pudo agregar al entrenamiento: {e}")
                result["training_added"] = False
        
        return result
    
    def _save_knn_model(self):
        """Guardar modelo KNN actualizado"""
        import joblib
        
        model_file = Path("knn_model.pkl")
        scaler_file = Path("knn_scaler.pkl")
        
        try:
            joblib.dump(self.knn.model, model_file)
            joblib.dump(self.knn.scaler, scaler_file)
            
            log.info(f"\n✓ Modelo KNN guardado: {model_file}")
            log.info(f"✓ Scaler guardado: {scaler_file}")
            
        except Exception as e:
            log.warning(f"No se pudo guardar modelo: {e}")
    
    def _save_results(self):
        """Guardar resultados en JSON"""
        
        output_file = self.output_dir / "test_results.json"
        
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2)
        
        log.info(f"\nResultados guardados: {output_file}")
    
    def _print_summary(self):
        """Imprimir resumen"""
        
        log.info(f"\n{'='*70}")
        log.info(f"RESUMEN - MODO {self.mode.upper()}")
        log.info(f"{'='*70}")
        log.info(f"Total procesados: {self.results['emails_tested']}")
        log.info(f"Errores: {len(self.results['errors'])}")
        
        log.info(f"\nClasificaciones:")
        for cls, count in self.results["by_classification"].items():
            pct = (count / self.results["emails_tested"] * 100) if self.results["emails_tested"] > 0 else 0
            log.info(f"  {cls:15s}: {count:3d} ({pct:5.1f}%)")
        
        log.info(f"\nFuentes:")
        for source, count in self.results["by_source"].items():
            pct = (count / self.results["emails_tested"] * 100) if self.results["emails_tested"] > 0 else 0
            log.info(f"  {source:15s}: {count:3d} ({pct:5.1f}%)")
        
        # Información de entrenamiento (si aplica)
        if self.mode == "train":
            log.info(f"\n🎓 INFORMACIÓN DE ENTRENAMIENTO:")
            log.info(f"  Ejemplos agregados: {self.results['training']['examples_added']}")
            
            if self.results['training']['knn_before']:
                before = self.results['training']['knn_before']
                after = self.results['training']['knn_after']
                
                log.info(f"\n  KNN ANTES:")
                log.info(f"    Total ejemplos: {before.get('total_examples', 0)}")
                log.info(f"    Clases: L:{before.get('by_label', {}).get('legitimo', 0)} "
                        f"S:{before.get('by_label', {}).get('spam', 0)} "
                        f"P:{before.get('by_label', {}).get('sospechoso', 0)}")
                
                log.info(f"\n  KNN DESPUÉS:")
                log.info(f"    Total ejemplos: {after.get('total_examples', 0)}")
                log.info(f"    Clases: L:{after.get('by_label', {}).get('legitimo', 0)} "
                        f"S:{after.get('by_label', {}).get('spam', 0)} "
                        f"P:{after.get('by_label', {}).get('sospechoso', 0)}")
                
                log.info(f"\n  ✓ Modelo KNN actualizado y guardado")
        
        if self.results["errors"]:
            log.warning(f"\nErrores encontrados:")
            for err in self.results["errors"]:
                log.warning(f"  - {err['file']}: {err['error']}")
        
        log.info(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Test Runner para SuperAgent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--config",
        default="config.json",
        help="Archivo de configuración (default: config.json)"
    )
    
    parser.add_argument(
        "--input",
        default="test_emails",
        help="Directorio de entrada con emails (default: test_emails)"
    )
    
    parser.add_argument(
        "--output",
        default="test_results",
        help="Directorio de salida (default: test_results)"
    )
    
    parser.add_argument(
        "--mode",
        choices=["quick", "full", "train"],
        default="full",
        help="Modo de ejecución:\n"
             "  quick: Solo KNN, sin LLM\n"
             "  full: KNN + LLM si necesario, SIN entrenar\n"
             "  train: KNN + LLM + ENTRENA el modelo (default: full)"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Mostrar información de debug"
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Ejecutar tests
    runner = TestRunner(
        config_path=args.config,
        input_dir=args.input,
        output_dir=args.output,
        mode=args.mode,
        debug=args.debug
    )
    
    success = runner.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
