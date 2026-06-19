# Cambios en modelo KNN (sklearn + Aprendizaje Activo)

## Resumen
Se reemplazó el modelo KNN manual por una implementación con **scikit-learn** que incluye:
- ✅ Algoritmo KNN optimizado con KDTree
- ✅ Aprendizaje activo: modelo mejora con cada email clasificado
- ✅ Umbral de confianza **dinámico**: se ajusta según cantidad de ejemplos
- ✅ Estadísticas de precisión y feedback
- ✅ Reducción progresiva de dependencia del LLM

---

## Cambios técnicos

### 1. Nuevas dependencias
```
scikit-learn>=1.0.0
joblib>=1.1.0
```

### 2. Clase `KNNClassifier` reescrita

#### Mejoras principales:
- **Modelo sklearn**: `KNeighborsClassifier` con `weights='distance'` (votación ponderada)
- **Persistencia**: cambió de pickle a joblib (más eficiente con sklearn)
- **Estadísticas**: archivo `knn_stats.json` con histórico de decisiones

#### Nuevos métodos:

**`record_feedback(predicted_label, actual_label)`**
```python
# Registra si KNN tuvo razón o se equivocó
# Mantiene histórico de últimos 100 feedbacks
# Calcula precisión reciente (últimos 20)
```

**`add_training_example(vector, label, feedback_correct=True)`**
```python
# Agrega ejemplo confirmado al modelo
# Si feedback_correct=False, ayuda a identificar debilidades
# Limita a 1000 ejemplos (FIFO si supera)
# Retraina automáticamente el modelo
```

**`_adjust_threshold_dynamically()`**
```
Ajusta el umbral de confianza según cantidad de ejemplos:
- <50 ejemplos:    threshold = 0.95 (muy exigente, depende de LLM)
- 50-200 ejemplos:  threshold = 0.85 (estándar)
- 200-500 ejemplos: threshold = 0.75 (confía más en KNN)
- >500 ejemplos:    threshold = 0.65 (experto, menos LLM)

Esto **reduce automáticamente** la necesidad del LLM conforme el modelo crece.
```

**`stats_summary()`**
```python
# Retorna resumen del modelo:
{
  "total_examples": 156,
  "by_label": {"legitimo": 50, "spam": 60, "sospechoso": 46},
  "training_count": 95,  # Ejemplos agregados desde init
  "current_threshold": 0.75,
  "base_threshold": 0.85,
  "feedback_count": 42,
  "last_retrain": "2026-06-19T14:23:15..."
}
```

---

## Cambios en `superagent_2.py`

### 1. Flujo mejorado de clasificación

```python
# Ahora pasa knn_result a _handle_result para análisis de feedback
if knn_result["is_confident"]:
    analysis = self._build_analysis_from_knn(...)
else:
    analysis = self.analyzer.analyze_txt_file(...)  # Usa LLM si inseguro

# Registra si KNN acertó o se equivocó
self._handle_result(file_path, analysis, knn_result)
```

### 2. Método `_update_knn()` mejorado

```python
# Calcula feedback_correct basado en si KNN acertó
# Agrega ejemplo de forma más inteligente
# Registra estadísticas del modelo (tamaño, threshold, etc.)
```

### 3. Tracking de feedback

```python
# Si KNN predijo diferente a análisis final:
knn.record_feedback(predicted="spam", actual="sospechoso")

# Esto ayuda a:
# - Identificar puntos débiles del modelo
# - Calcular precisión reciente
# - Optimizar features o thresholds en el futuro
```

---

## Beneficios

| Aspecto | Antes | Después |
|---------|-------|---------|
| **Rendimiento** | Manual + distancia euclidiana | sklearn + KDTree optimizado |
| **Escalabilidad** | 500 ejemplos máximo | 1000 ejemplos máximo |
| **Aprendizaje** | Pasivo (solo acumula) | Activo (registra feedback) |
| **Umbral** | Fijo 0.85 | Dinámico 0.65-0.95 |
| **Precisión** | Desconocida | Histórica y reciente |
| **Dependencia LLM** | Constante | Decrece con más datos |

---

## Archivos generados

```
knn_model.joblib      # Modelo sklearn persistido (matriz X, y, modelo)
knn_stats.json        # Estadísticas y histórico
```

---

## Cómo usar

### Verificar estado del modelo:
```python
knn = KNNClassifier()
stats = knn.stats_summary()
print(f"Ejemplos: {stats['total_examples']}")
print(f"Threshold: {stats['current_threshold']:.2%}")
```

### Agregar retroalimentación manual:
```python
# Si un analista encuentra que el modelo se equivocó
knn.record_feedback(predicted_label="spam", actual_label="sospechoso")
```

---

## Próximas mejoras recomendadas

1. **Optimización de features**: análisis de importancia de cada feature
2. **Historial de cambios**: auditoría completa de qué ejemplos mejoraron/empeoraron
3. **A/B testing**: comparar KNN vs LLM en muestras
4. **Curva de aprendizaje**: gráfico de precisión vs ejemplos de entrenamiento
5. **Reentrenamiento automático**: cada 50-100 ejemplos nuevos
