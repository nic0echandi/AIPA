#!/usr/bin/env python3
"""
Script para procesar emails en manual_review/ y reentrenar KNN.
Extrae features de los emails ya clasificados y los usa para mejorar el modelo.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np

# Importar módulos locales
from knn_classifier import KNNClassifier, extract_features, features_to_vector, FEATURE_NAMES
from phishingAnalizer import PhishingAnalyzerTXT

def extract_classification_from_filename(filename: str) -> str:
    """
    Extrae la clasificación desde el nombre del archivo en manual_review/.
    
    Nomenclatura esperada:
    - Phishing_XXXX.txt → "sospechoso" (phishing)
    - Spam_XXXX.txt → "spam"
    - Legit_XXXX.txt → "legitimo"
    - Si inicia con __ → puede ser un archivo temporal/error
    """
    basename = Path(filename).stem
    
    if basename.startswith("__"):
        return None  # Ignorar archivos que empiezan con __
    
    if "Phishing" in basename or "phishing" in basename.lower():
        return "sospechoso"
    elif "Spam" in basename or "spam" in basename.lower():
        return "spam"
    elif "Legit" in basename or "legitimo" in basename.lower():
        return "legitimo"
    else:
        # Por defecto, si no tiene prefijo claro, asumir que está en manual_review
        # porque fue detectado como sospechoso por el LLM
        return "sospechoso"

def process_manual_review_emails(manual_review_dir: Path = Path("manual_review")) -> Tuple[List[np.ndarray], List[int], int]:
    """
    Procesa todos los emails en manual_review/ y extrae features + labels.
    
    Returns:
        (vectors, labels, count_processed)
    """
    if not manual_review_dir.exists():
        print(f"❌ Directorio {manual_review_dir} no existe")
        return [], [], 0
    
    vectors = []
    labels = []
    errors = []
    processed = 0
    
    # Obtener todos los archivos .txt
    email_files = sorted(manual_review_dir.glob("*.txt"))
    total = len(email_files)
    
    print(f"\n📧 Procesando {total} emails en {manual_review_dir}...\n")
    
    knn = KNNClassifier()
    parser = PhishingAnalyzerTXT()
    
    for i, email_file in enumerate(email_files, 1):
        try:
            # Extraer clasificación desde nombre
            label_str = extract_classification_from_filename(email_file.name)
            
            if label_str is None:
                # Ignorar archivos con prefijo __
                continue
            
            label_int = KNNClassifier.LABEL_TO_INT.get(label_str)
            if label_int is None:
                errors.append(f"{email_file.name}: label '{label_str}' desconocido")
                continue
            
            # Parsear email
            try:
                parsed = parser.parse_txt_file(str(email_file))
            except Exception as e:
                errors.append(f"{email_file.name}: parse error - {str(e)[:60]}")
                continue
            
            if not parsed:
                errors.append(f"{email_file.name}: no se pudo parsear")
                continue
            
            headers = parsed.get("headers", {})
            content = parsed.get("raw_content", "")
            microsoft_urls = parsed.get("microsoft_urls", "None")
            
            # Extraer features
            features = extract_features(headers, content, microsoft_urls)
            vector = features_to_vector(features)
            
            vectors.append(vector)
            labels.append(label_int)
            processed += 1
            
            # Mostrar progreso
            label_display = KNNClassifier.LABELS[label_int]
            print(f"  [{i:3d}/{total}] {email_file.name[:60]:60s} → {label_display:10s} ✓")
            
        except Exception as e:
            errors.append(f"{email_file.name}: {str(e)[:80]}")
    
    print(f"\n✅ Procesados: {processed}/{total} emails")
    
    if errors:
        print(f"\n⚠️  Errores ({len(errors)}):")
        for err in errors[:10]:
            print(f"   • {err}")
        if len(errors) > 10:
            print(f"   ... y {len(errors) - 10} más")
    
    return vectors, labels, processed

def retrain_knn_with_manual_review(vectors: List[np.ndarray], labels: List[int]):
    """
    Retraina el modelo KNN con los nuevos datos de manual_review.
    """
    if not vectors or not labels:
        print("❌ No hay datos para reentrenar")
        return None
    
    print(f"\n🔄 Reentrainando KNN con {len(vectors)} nuevos ejemplos...")
    
    # Cargar o crear KNN
    knn = KNNClassifier()
    
    # Datos actuales
    X_current = knn.X_train
    y_current = knn.y_train
    
    # Nuevos datos
    X_new = np.array(vectors, dtype=np.float64)
    y_new = np.array(labels, dtype=np.int32)
    
    # Combinar
    X_combined = np.vstack([X_current, X_new])
    y_combined = np.hstack([y_current, y_new])
    
    print(f"  Datos anteriores: {len(y_current)} ejemplos")
    print(f"  Datos nuevos:     {len(y_new)} ejemplos")
    print(f"  Total combinado:  {len(y_combined)} ejemplos")
    
    # Mostrar distribución
    unique, counts = np.unique(y_combined, return_counts=True)
    print(f"\n  Distribución por clase:")
    for label_int, count in zip(unique, counts):
        label_str = KNNClassifier.LABELS.get(label_int, "desconocido")
        print(f"    • {label_str:12s}: {count:3d} ejemplos")
    
    # Reentrenar
    knn._retrain(X_combined, y_combined)
    knn.stats["by_label"] = {
        "legitimo": int(counts[unique == 0].sum() if (unique == 0).any() else 0),
        "spam": int(counts[unique == 1].sum() if (unique == 1).any() else 0),
        "sospechoso": int(counts[unique == 2].sum() if (unique == 2).any() else 0),
    }
    knn.stats["total_examples"] = int(len(y_combined))
    knn._save()
    
    print(f"\n✅ Modelo reentrainado y guardado")
    return knn

def lower_confidence_threshold():
    """
    Baja el umbral de confianza para que KNN clasifique más directo sin escalar a LLM.
    Con más datos, el modelo es más confiable.
    """
    knn = KNNClassifier()
    
    old_threshold = knn.current_confidence_threshold
    
    # Estrategia: mientras más ejemplos, menos exigente con confianza
    total_examples = len(knn.y_train)
    
    if total_examples < 50:
        new_threshold = 0.80  # Muy conservador
    elif total_examples < 100:
        new_threshold = 0.75
    elif total_examples < 200:
        new_threshold = 0.70
    else:
        new_threshold = 0.65
    
    knn.current_confidence_threshold = new_threshold
    knn.stats["current_confidence_threshold"] = new_threshold
    knn.stats["threshold_adjustments"].append({
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "old_threshold": old_threshold,
        "new_threshold": new_threshold,
        "reason": f"Auto-adjusted based on {total_examples} training examples"
    })
    knn._save()
    
    print(f"\n📊 Umbral de confianza actualizado:")
    print(f"  Anterior: {old_threshold * 100:.0f}%")
    print(f"  Nuevo:    {new_threshold * 100:.0f}%")
    print(f"  Razón:    {total_examples} ejemplos de entrenamiento")

if __name__ == "__main__":
    print("=" * 80)
    print("REENTRENAMIENTO DE KNN CON MANUAL REVIEW")
    print("=" * 80)
    
    # Procesar emails en manual_review/
    vectors, labels, processed = process_manual_review_emails()
    
    if processed == 0:
        print("\n❌ No se pudieron procesar emails. Abortando.")
        sys.exit(1)
    
    # Reentrenar KNN
    knn = retrain_knn_with_manual_review(vectors, labels)
    
    if knn is None:
        print("\n❌ Error durante reentrenamiento. Abortando.")
        sys.exit(1)
    
    # Bajar el umbral dinámicamente
    lower_confidence_threshold()
    
    print("\n" + "=" * 80)
    print("✅ REENTRENAMIENTO COMPLETADO")
    print("=" * 80)
    print("\n📋 Próximos pasos:")
    print("  1. Reinicia el superagent.py")
    print("  2. Verifica que KNN ahora clasifique más emails directamente")
    print("  3. Monitorea los logs: debería ver 'KNN directo' en lugar de 'LLM'")
    print("\n")
