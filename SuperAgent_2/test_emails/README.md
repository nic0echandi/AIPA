# test_emails/ - Directorio de Testing y Reentrenamiento

**IMPORTANTE**: Este directorio es SOLO para testing y reentrenamiento. NO interfiere con el sistema de producción en `ingress/`.

## Modos de Testing

### 1. Quick (solo KNN)
```bash
python test_superagent.py --mode quick --input test_emails
```
- ⚡ Rápido (<5ms/email)
- ❌ Sin LLM
- ❌ Sin entrenar KNN

### 2. Full (KNN + LLM, SIN entrenar)
```bash
python test_superagent.py --mode full --input test_emails
```
- ✅ Completo (KNN + LLM)
- ⚠️ No entrena el modelo
- 📊 Genera reporte en test_results/

**Uso**: Validar clasificaciones sin afectar el modelo

### 3. Train (KNN + LLM + ENTRENA) ✨
```bash
python test_superagent.py --mode train --input test_emails
```
- ✅ Completo (KNN + LLM)
- ✅ **ENTRENA el modelo KNN**
- 📊 Genera reporte con estadísticas de entrenamiento
- 💾 Guarda modelo actualizado

**Uso**: Reentrenamiento del modelo

## Flujo Rápido de Entrenamiento

```bash
# 1. Copiar emails de entrenamiento
cp samples/*.txt .

# 2. Entrenar modelo
python test_superagent.py --mode train

# 3. Ver estadísticas
cat ../test_results/test_results.json | jq '.training'
```

## Ejemplo de Salida (Modo Train)

```
TEST RUNNER - Modo: TRAIN
⚠️  MODO TRAINING: KNN será actualizado con 3 ejemplos

[1/3] Procesando phishing_1.txt...
  ✓ SOSPECHOSO (confianza: 95%)
  → Agregado al entrenamiento: sospechoso

[2/3] Procesando spam_1.txt...
  ✓ SPAM (confianza: 88%)
  → Agregado al entrenamiento: spam

[3/3] Procesando legitimate_1.txt...
  ✓ LEGITIMO (confianza: 92%)
  → Agregado al entrenamiento: legitimo

🎓 INFORMACIÓN DE ENTRENAMIENTO:
  Ejemplos agregados: 3
  
  KNN ANTES:
    Total ejemplos: 47
    Clases: L:15 S:16 P:16
  
  KNN DESPUÉS:
    Total ejemplos: 50
    Clases: L:16 S:17 P:17
  
  ✓ Modelo KNN actualizado y guardado
```

## Comparación de Modos

| Modo | LLM | Entrenar | Caso de Uso |
|------|-----|----------|-----------|
| `quick` | No | No | Testing rápido |
| `full` | Sí | No | Validación sin riesgo |
| `train` | Sí | **Sí** | Mejorar el modelo |

## Ventajas de esta Estructura

✓ Testing completamente aislado de producción  
✓ Reentrenamiento controlado del KNN  
✓ No contamina datos de ingress/  
✓ Fácil debugging  
✓ Resultados claros en JSON  

---

**Nota**: Este directorio no afecta el sistema de producción en `ingress/`

