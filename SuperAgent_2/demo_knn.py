#!/usr/bin/env python3
"""
Ejemplo de uso del nuevo modelo KNN con sklearn y aprendizaje activo.
Demuestra cómo el modelo mejora con cada ejemplo clasificado.
"""

import sys
import os
from pathlib import Path

# Agregar agent/ al path
agent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agent'))
sys.path.insert(0, agent_dir)

from knn_classifier import KNNClassifier, extract_features, features_to_vector


def main():
    print("=" * 70)
    print("DEMO: Modelo KNN con Aprendizaje Activo y sklearn")
    print("=" * 70)
    print()
    
    # Crear instancia del modelo
    knn = KNNClassifier(k=5, confidence_threshold=0.85)
    
    # 1. Ver estado inicial
    print("📊 Estado inicial del modelo:")
    stats = knn.stats_summary()
    print(f"   - Total ejemplos: {stats['total_examples']}")
    print(f"   - Threshold actual: {stats['current_threshold']:.2%}")
    print(f"   - Threshold base: {stats['base_threshold']:.2%}")
    print(f"   - Ejemplos por clase: {stats['by_label']}")
    print()
    
    # 2. Simular algunos ejemplos de entrenamiento
    print("🎓 Agregando ejemplos de entrenamiento...")
    print()
    
    # Ejemplo legítimo
    legit_vector = [0,0,0,0,1, 0,0,1,0,1, 0,0,1,0,0, 0,0,0,0.1,0, 0,0,0,0]
    knn.add_training_example(legit_vector, "legitimo", feedback_correct=True)
    print("   ✓ Ejemplo legítimo agregado (feedback correcto)")
    
    # Ejemplo spam
    spam_vector = [0,1,0,1,0, 0,1,0,1,0, 0,0,1,0.33,0, 0,0,0,0.6,0, 0,0,0,0]
    knn.add_training_example(spam_vector, "spam", feedback_correct=True)
    print("   ✓ Ejemplo spam agregado (feedback correcto)")
    
    # Ejemplo phishing
    phish_vector = [1,0,1,1,0, 1,1,0,1,0, 1,0,0,0.33,1, 0,0,1,0,0, 0,1,1,0]
    knn.add_training_example(phish_vector, "sospechoso", feedback_correct=True)
    print("   ✓ Ejemplo sospechoso agregado (feedback correcto)")
    print()
    
    # Simular más ejemplos (para demostrar ajuste de threshold)
    print("📈 Simulando 15 ejemplos más para demostrar crecimiento...")
    ejemplos = [
        (legit_vector, "legitimo"),
        (spam_vector, "spam"),
        (phish_vector, "sospechoso"),
    ]
    
    for i in range(5):
        for vector, label in ejemplos:
            knn.add_training_example(vector, label, feedback_correct=True)
    
    print()
    
    # 3. Ver estado después del entrenamiento
    print("📊 Estado después del aprendizaje activo:")
    stats = knn.stats_summary()
    print(f"   - Total ejemplos: {stats['total_examples']}")
    print(f"   - Threshold actual: {stats['current_threshold']:.2%}")
    print(f"   - Threshold base: {stats['base_threshold']:.2%}")
    print(f"   - Cambio de threshold: {stats['base_threshold'] - stats['current_threshold']:.2%}")
    print(f"   - Ejemplos por clase: {stats['by_label']}")
    print(f"   - Total entrenamiento agregado: {stats['training_count']}")
    print()
    
    # 4. Registrar feedback (modelo se equivocó)
    print("📝 Registrando feedback sobre predicción incorrecta...")
    knn.record_feedback(predicted_label="spam", actual_label="sospechoso")
    knn.record_feedback(predicted_label="legitimo", actual_label="spam")
    knn.record_feedback(predicted_label="legitimo", actual_label="spam")
    print("   ✓ Feedbacks registrados")
    print()
    
    # 5. Clasificar un nuevo email
    print("🔍 Clasificando un nuevo email...")
    test_headers = {
        "From": "admin@microsoft.com",
        "To": "usuario@empresa.com",
        "Subject": "Verify your account urgently",
        "X-MS-Has-Attach": "no",
        "Authentication-Results": "spf=fail; dkim=none; dmarc=fail",
        "x-forefront-antispam-report": "CAT:PHSH;SCL:9"
    }
    test_content = "Click here to verify: http://fake-microsoft.com/verify?token=xyz"
    microsoft_urls = "Detected"
    
    result = knn.classify_email(test_headers, test_content, microsoft_urls)
    
    print(f"   Predicción: {result['classification'].upper()}")
    print(f"   Confianza: {result['confidence']:.2%}")
    print(f"   Es confiable: {'SÍ (DIRECTO)' if result['is_confident'] else 'NO (requiere LLM)'}")
    print(f"   Tamaño del modelo: {result['model_size']} ejemplos")
    print()
    
    # 6. Resumen final
    print("=" * 70)
    print("✅ DEMO completado")
    print("=" * 70)
    print()
    print("Archivos generados:")
    print(f"   - {KNNClassifier.MODEL_PATH} (modelo sklearn persistido)")
    print(f"   - {KNNClassifier.STATS_PATH} (estadísticas y histórico)")
    print()
    print("Beneficios del nuevo modelo:")
    print("   ✓ Usa sklearn optimizado con KDTree")
    print("   ✓ Aprendizaje activo: mejora con cada ejemplo")
    print("   ✓ Umbral dinámico: reduce dependencia del LLM con más datos")
    print("   ✓ Registra feedback: identifica débilidades")
    print("   ✓ Escalable: hasta 1000 ejemplos")
    print()


if __name__ == "__main__":
    main()
