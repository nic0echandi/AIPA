# Análisis: ¿Por qué KNN no clasifica? ¿Se necesita manual review?

## 📊 Estado Actual (91 casos analizados)
- **7 casos**: Whitelist (genuinos)
- **84 casos**: LLM (spam y legítimos)
- **0 casos**: KNN

## 🔴 PROBLEMA IDENTIFICADO

### 1. **Umbral de confianza muy alto (90%)**
El modelo KNN requiere **≥90% de confianza** para clasificar directamente. Caso contrario, escala a LLM.

```python
if knn_result["confidence"] >= 0.90:  # ← 90% es muy exigente
    use_knn_classification()
else:
    escalate_to_llm()  # ← Por eso SIEMPRE va a LLM
```

### 2. **Modelo KNN con muy pocos datos de entrenamiento**
El modelo se inicializa con solo **24 ejemplos hardcodeados**:
- 7 legítimos
- 5 spam
- 12 sospechosos

Con tan pocos ejemplos, la confianza nunca alcanza 90% en casos reales.

### 3. **Ciclo roto de aprendizaje**
```
KNN nace con 24 ejemplos
    ↓
Threshold = 90%
    ↓
KNN nunca tiene 90% confianza
    ↓
Todos los emails → LLM
    ↓
Los 63 emails en manual_review/ nunca reentrenaon KNN
    ↓
KNN sigue teniendo 24 ejemplos
    ↓
El ciclo no avanza
```

### 4. **Archivos de persistencia ausentes**
- ✗ `knn_stats.json` → No existe (KNN nunca guardó datos)
- ✗ `manual_review_feedback.jsonl` → No existe (feedback loop nunca se ejecutó)
- ✗ `knn_model.pkl` (982 bytes) → Corrupto o vacío

---

## ✅ SOLUCIÓN: SÍ necesitas manual review

### Paso 1: Procesar emails en manual_review/

Tienes **63 emails clasificados manualmente** en `SuperAgent/manual_review/`:
- Que están etiquetados por nombre (Phishing_*, Spam_*, etc.)
- Que pueden usarse para reentrenar KNN

Ejecuta el script nuevo:

```bash
cd /home/user/Documents/MyGithub/AIPA/SuperAgent
python3 knn_retrain_from_manual_review.py
```

**Esto hará:**
1. Leer los 63 emails en `manual_review/`
2. Extraer features de cada uno
3. Combinar con los 24 ejemplos base
4. Reentrenar KNN con ~87 ejemplos totales
5. **Bajar automáticamente el threshold** a 75-80% (conforme crece el dataset)
6. Guardar el modelo en `knn_model.joblib` y stats en `knn_stats.json`

### Paso 2: Reinicia SuperAgent

```bash
python3 superagent.py
```

El modelo ahora:
- Tendrá ~87 ejemplos (3.6x más datos)
- Threshold bajado automáticamente
- **Debería clasificar KNN directamente más casos**

### Paso 3: Monitorea el progreso

En los logs verás:

**ANTES:**
```
KNN → sospechoso (62.34%) [→ LLM] (24 ejemplos)
KNN inseguro (62%) - escalando a análisis profundo...
```

**DESPUÉS:**
```
KNN → sospechoso (78.12%) [DIRECTO] (87 ejemplos)
KNN directo (78% confianza) - phishing_analyzer.py
```

---

## 📈 Estrategia de mejora continua

El sistema ahora implementará **aprendizaje activo progresivo**:

| Ejemplos | Threshold | Comportamiento |
|----------|-----------|---|
| <50 | 80% | Muy conservador |
| 50-100 | 75% | Moderado |
| 100-200 | 70% | Agresivo |
| >200 | 65% | Muy agresivo |

**Conforme KNN acumule datos:**
1. Se vuelve más confiable
2. El threshold baja automáticamente
3. Menos dependencia de LLM
4. Clasificaciones más rápidas

---

## 🎯 Flujo recomendado

### Para los próximos emails nuevos:

1. **KNN clasifica con confianza**
   - Si ≥ threshold actual → acepta clasificación
   - Si < threshold → LLM refina

2. **Guardar feedback en `manual_review_feedback.jsonl`**
   ```json
   {"file": "email.txt", "action": "accept", "knn_confidence": 0.78}
   ```

3. **Cada N dias o M emails**
   - Ejecutar `knn_retrain_from_manual_review.py`
   - KNN crece → Threshold baja → LLM necesario menos veces

---

## 🔍 Verificación

Después de ejecutar el script:

```bash
# Ver stats del modelo
python3 -c "
import json
with open('knn_stats.json') as f:
    s = json.load(f)
print(f'Ejemplos: {s[\"total_examples\"]}')
print(f'Threshold: {s.get(\"current_confidence_threshold\", 0.9)*100:.0f}%')
print(f'Por label: {s[\"by_label\"]}')
"
```

Deberías ver:
- **total_examples**: ~87 (en lugar de 24)
- **current_confidence_threshold**: 0.75-0.80 (en lugar de 0.90)
- **by_label**: Distribución actualizada

---

## ⚠️ Notas importantes

1. **Los nombres de archivos en manual_review/ importan:**
   - `Phishing_*` → label = "sospechoso"
   - `Spam_*` → label = "spam"
   - `Legit_*` o `Legitimate_*` → label = "legitimo"
   - Si inicia con `__` → se ignora

2. **Si los nombres no son claros**, debes:
   - Renombrar los archivos según su clase real
   - O usar `manual_review_tool.py` para revisar uno por uno

3. **El modelo NUNCA debe usarse en producción con <30 ejemplos**
   - 24 es el mínimo peligroso
   - 87 es aceptable
   - 150+ es robusto

---

## 📋 Próximos pasos

```bash
# 1. Verificar que el script existe
ls -la knn_retrain_from_manual_review.py

# 2. Ejecutar el reentrenamiento
python3 knn_retrain_from_manual_review.py

# 3. Verificar que se crearon los archivos
ls -la knn_stats.json knn_model.joblib

# 4. Reiniciar SuperAgent
python3 superagent.py

# 5. Monitorear que KNN clasifique directamente
tail -f logs/superagent.log | grep "KNN"
```

---

**Conclusión:** SÍ, necesitas manual review para bootstrappear el modelo. Una vez que acumules datos, el aprendizaje activo hace el resto automáticamente.
