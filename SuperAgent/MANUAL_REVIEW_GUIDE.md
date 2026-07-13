# 📋 Guía de Revisión Manual de Emails

## 🎯 ¿Cuándo aparecen emails para revisión manual?

El sistema marca emails para revisión cuando:
- **`knn_disagreement`**: El modelo KNN predice diferente al análisis LLM
- **`risk_mismatch`**: La puntuación de riesgo no coincide con la clasificación
- **`low_llm_confidence`**: La confianza del LLM está por debajo del umbral (< 70%)

Ejemplo del log:
```
KNN inseguro (61%) → escalando a análisis profundo...
RESULTADO → SPAM | Score: 0/100 | Confianza: 50%
KNN feedback: predijo 'legitimo' pero análisis final es 'spam'
Validación LLM: REVIEW (confianza: 42%)
⚠️  Email para revisión manual: knn_disagreement, risk_mismatch, low_llm_confidence
```

## 🚀 Cómo usar la herramienta

### 1. **Ver resumen de casos pendientes**
```bash
cd SuperAgent
python manual_review_tool.py summary
```

**Salida:**
```
CASO 1. sospechoso   | De: attacker@malicious.com        | file_20260708_165409.json
CASO 2. spam         | De: marketing@phishing-site.xyz   | file_20260708_165413.json
...
```

### 2. **Contar casos pendientes**
```bash
python manual_review_tool.py count
```

### 3. **Revisar casos interactivamente**
```bash
python manual_review_tool.py
```

**Interfaz:**
```
════════════════════════════════════════════════════════════════════════════════════
  CASO 1/3 - Revisión Manual
════════════════════════════════════════════════════════════════════════════════════

─ INFORMACIÓN DEL EMAIL ─────────────────────────────────────────────────────────────
  De:       attacker@malicious.com
  Asunto:   Verify Your Account Immediately

─ CLASIFICACIÓN ─────────────────────────────────────────────────────────────────────
  Clasificación LLM: sospechoso
  Confianza:         42%

─ VALIDACIÓN ────────────────────────────────────────────────────────────────────────
  Recomendación: REVIEW
  Confianza:     42%

  Flags:
    • knn_disagreement
    • risk_mismatch
    • low_llm_confidence

  Razones:
    • SPF: fail
    • DKIM: fail
    • URLs maliciosas detectadas

─ METADATA ──────────────────────────────────────────────────────────────────────────
  Timestamp: 2026-07-08T16:54:09Z

─ ACCIONES DISPONIBLES ──────────────────────────────────────────────────────────────
  [a] ✅ Aceptar clasificación
  [r] ❌ Rechazar clasificación
  [q] 🚫 Enviar a cuarentena
  [w] ✅ Agregar remitente a whitelist
  [s] ⏭️  Salitar por ahora
  [q] Salir

👉 Selecciona acción [a/r/q/w/s/q]:
```

## 📌 Opciones de acción

### **[a] Aceptar clasificación** ✅
- El modelo acertó, la clasificación es correcta
- El archivo se mueve a `manual_review/approved/`
- Se registra en `manual_review_feedback.jsonl`

### **[r] Rechazar clasificación** ❌
- La clasificación es incorrecta
- Solicita una nota opcional (ej: "es legítimo pero tiene keywords sospechosas")
- El archivo se mueve a `manual_review/rejected/`
- Esto retroalimenta al modelo

### **[q] Enviar a cuarentena** 🚫
- Email es definitivamente malicioso y requiere acción inmediata
- Se mueve a la carpeta `quarantine/`
- Se registra como caso crítico

### **[w] Agregar a whitelist** ✅
- Agregar el dominio del remitente a `whitelist.txt`
- Futuro: todos los emails de ese dominio se clasificarán como legítimos
- El archivo se mueve a `manual_review/approved/`
- Útil para falsos positivos

### **[s] Saltar** ⏭️
- Revisar más tarde
- El archivo se mantiene en `manual_review/`

## 📊 Archivos generados

### `manual_review_feedback.jsonl`
Registro de todas las decisiones tomadas. Cada línea es un JSON:

```json
{
  "timestamp": "2026-07-13T15:45:30.123456",
  "original_file": "manual_review/file_20260708_165409.json",
  "action": "accept",
  "notes": "correctamente clasificado como phishing"
}
```

### Carpeta `manual_review/approved/`
Casos donde la clasificación fue correcta. Usar para auditoría y análisis de precisión.

### Carpeta `manual_review/rejected/`
Casos donde el modelo se equivocó. Usar para reentrenamiento.

### Carpeta `manual_review/` (original)
Casos pendientes de decisión.

## 🔄 Flujo de retroalimentación

```
Email analizado
         ↓
¿Desacuerdo KNN-LLM? → SÍ → Guardar en manual_review/
         ↓ NO
Procesar resultado
    
Revisión manual
         ↓
    ┌────┴────┬────────┬──────────┐
    ↓         ↓        ↓          ↓
 ACCEPT    REJECT   QUARANTINE  WHITELIST
    ↓         ↓        ↓          ↓
 approved  rejected  quarantine  approved
    ↓         ↓        ↓          ↓
 Auditoría  FEEDBACK  Crítico    Prevención
           al modelo
```

## 💾 Ver historial de decisiones

```bash
# Ver últimas 10 decisiones
tail -n 10 manual_review_feedback.jsonl

# Contar por acción
grep -o '"action":"[^"]*"' manual_review_feedback.jsonl | sort | uniq -c

# Ver todas las decisiones "reject" con notas
grep '"action":"reject"' manual_review_feedback.jsonl | jq .
```

## 🎓 Ejemplo práctico completo

```bash
$ cd SuperAgent

# Verificar cuántos casos hay
$ python manual_review_tool.py count
Casos pendientes: 5

# Ver resumen
$ python manual_review_tool.py summary
📋 Archivos pendientes de revisión: 5

Últimos 10 casos:
  1. sospechoso   | De: attacker@malicious.com        | file_20260708_165409.json
  2. spam         | De: marketing@phishing-site.xyz   | file_20260708_165413.json
  3. legitimo     | De: boss@company.com              | file_20260708_165420.json
  4. sospechoso   | De: suspicious@unknown.com        | file_20260708_165425.json
  5. spam         | De: newsletter@suspicious.co      | file_20260708_165430.json

# Revisar interactivamente
$ python manual_review_tool.py

CASO 1/5 - Revisión Manual
────────────────────────────
De: attacker@malicious.com
Asunto: Verify Your Account Immediately
Clasificación: sospechoso (42% confianza)

👉 Selecciona acción [a/r/q/w/s/q]: a
✅ Clasificación aceptada

CASO 2/5 - Revisión Manual
────────────────────────────
De: marketing@phishing-site.xyz
Asunto: Special Offer Today!
Clasificación: spam (55% confianza)

👉 Selecciona acción [a/r/q/w/s/q]: w
✅ phishing-site.xyz agregado a whitelist? (s/n): n
⏭️  Saltando...

CASO 3/5 - Revisión Manual
────────────────────────────
De: boss@company.com
Asunto: Urgent: Transfer funds
Clasificación: sospechoso (38% confianza)

👉 Selecciona acción [a/r/q/w/s/q]: r
Nota (opcional): Es from spoofed, debe ir a cuarentena
❌ Clasificación rechazada

# Ver historial
$ cat manual_review_feedback.jsonl
{"timestamp": "2026-07-13T15:45:30", "original_file": "...", "action": "accept", "notes": ""}
{"timestamp": "2026-07-13T15:45:45", "original_file": "...", "action": "reject", "notes": "Es from spoofed, debe ir a cuarentena"}
```

## 🔧 Integración automática

En el futuro, estas decisiones pueden:
- **Entrenar el modelo KNN** con nuevos ejemplos
- **Actualizar whitelist** automáticamente
- **Generar reportes** de precisión del modelo
- **Alertar** si hay múltiples desacuerdos en categoría específica

## 📞 Troubleshooting

### Error: "Directorio manual_review no existe"
```bash
mkdir -p manual_review manual_review/approved manual_review/rejected
python manual_review_tool.py
```

### Los archivos JSON no se están guardando
Verificar en `superagent.py` línea ~530:
```python
self.llm_validator.save_for_review(
    file_path, validation, 
    {"headers": self.last_email_headers},
    llm_result
)
```

Y en `config.json`:
```json
"manual_review_dir": "manual_review"
```

### ¿Dónde se guardan los JSON files?
```bash
ls -la SuperAgent/manual_review/
grep -l "validation" SuperAgent/manual_review/*.json
```
