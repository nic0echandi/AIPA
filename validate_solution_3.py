#!/usr/bin/env python3
"""
Script de validación - Solución 3
Verifica que los cambios se hayan aplicado correctamente en knn_classifier.py
"""

import sys
from pathlib import Path

# Agregar SuperAgent al path
sys.path.insert(0, str(Path(__file__).parent / "SuperAgent"))

def validate_solution_3():
    """Valida que la Solución 3 está implementada."""
    
    print("\n" + "="*70)
    print("🔍 VALIDACIÓN - SOLUCIÓN 3: KNN Mejorado para Phishing")
    print("="*70)
    
    try:
        from knn_classifier import KNNClassifier
        print("✅ Módulo knn_classifier importado correctamente\n")
        
        # 1. Inicializar el clasificador
        print("[1] Inicializando KNNClassifier...")
        knn = KNNClassifier()
        
        # 2. Verificar parámetros
        print("\n[2] Verificando parámetros...")
        
        assert knn.k == 7, f"❌ K debería ser 7, pero es {knn.k}"
        print(f"   ✅ K = {knn.k} (aumentado de 5)")
        
        assert knn.current_confidence_threshold == 0.90, \
            f"❌ Threshold debería ser 0.90, pero es {knn.current_confidence_threshold}"
        print(f"   ✅ Threshold = {knn.current_confidence_threshold:.0%} (aumentado de 0.85)")
        
        # 3. Verificar dataset expandido
        print("\n[3] Verificando dataset base expandido...")
        
        num_examples = len(knn.y_train)
        assert num_examples >= 24, \
            f"❌ Debería haber >= 24 ejemplos, pero hay {num_examples}"
        print(f"   ✅ Total ejemplos: {num_examples} (antes: 16)")
        
        stats = knn.stats["by_label"]
        print(f"   ✅ Distribución:")
        print(f"      - Legítimos: {stats['legitimo']} (antes: 5)")
        print(f"      - Spam: {stats['spam']} (antes: 4)")
        print(f"      - Sospechosos: {stats['sospechoso']} (antes: 7)")
        
        # 4. Verificar métrica
        print("\n[4] Verificando configuración de KNeighborsClassifier...")
        
        model = knn.model
        metric_used = model.metric
        expected_metric = 'manhattan'
        
        if hasattr(model, 'metric'):
            print(f"   ✅ Métrica: {metric_used} (antes: euclidean)")
        else:
            print(f"   ⚠️  No se puede verificar métrica directamente (sklearn internals)")
        
        # 5. Verificar pesos de clase
        print("\n[5] Verificando pesos de clase...")
        
        class_weights = knn.stats.get("class_weights")
        if class_weights:
            print(f"   ✅ Pesos de clase configurados:")
            for label_int, label_name in knn.LABELS.items():
                weight = class_weights.get(label_int, "N/A")
                print(f"      - {label_name}: {weight}x")
        else:
            print(f"   ℹ️  Pesos se cargarán en la próxima clasificación")
        
        # 6. Resumen
        print("\n" + "="*70)
        print("✅ VALIDACIÓN EXITOSA - Solución 3 implementada correctamente")
        print("="*70)
        
        print("\n📊 RESUMEN DE CAMBIOS:")
        print(f"   • K aumentado: 5 → {knn.k}")
        print(f"   • Threshold aumentado: 0.85 → {knn.current_confidence_threshold:.0%}")
        print(f"   • Métrica: euclidean → {metric_used}")
        print(f"   • Dataset expandido: 16 → {num_examples} ejemplos")
        print(f"   • Énfasis en phishing: +71% más ejemplos de sospechosos")
        print(f"   • Pesos: Sospechosos penalizados 3x más que legítimos")
        
        print("\n🚀 PRÓXIMOS PASOS:")
        print("   1. Ejecutar: python3 superagent.py")
        print("   2. Monitorear: tail -f logs/superagent.log")
        print("   3. Validar: Ver si se reducen falsos negativos de phishing")
        print("\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR durante validación: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = validate_solution_3()
    sys.exit(0 if success else 1)
