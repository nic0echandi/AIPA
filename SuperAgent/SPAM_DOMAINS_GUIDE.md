# 🚫 Sistema de Spam Domains (Blacklist)

## 📋 Descripción

El archivo `spam_domains.txt` contiene una **blacklist de dominios conocidos de spam**. Los emails que provengan de estos dominios se clasifican automáticamente como **SPAM** sin necesidad de análisis adicional, permitiendo una clasificación rápida y eficiente.

## ⚡ Características

- **Clasificación rápida**: Emails de dominios en spam_domains.txt se clasifican inmediatamente como SPAM (confianza: 95%)
- **Procesamiento sin LLM**: No requiere análisis del modelo LLM, mejorando rendimiento
- **Reautocarga en tiempo real**: El archivo se monitorea automáticamente; cambios se aplican sin reiniciar el sistema
- **Compatibilidad con subdominios**: Si `example.com` está en la lista, también se capturan emails de `mail.example.com`, `promo.example.com`, etc.

## 📝 Usar spam_domains.txt

### Agregar un dominio manualmente

Abre el archivo `SuperAgent/spam_domains.txt` y agrega un dominio por línea:

```txt
# Ejemplo: agregar promociones de GymPass
gympass.com

# Ejemplo: dominio de phishing conocido
amazon-fake-verify.com
```

**Reglas:**
- Un dominio por línea
- Sin espacios adicionales
- Las líneas que empiezan con `#` son comentarios y se ignoran
- Los dominios no diferencian mayúsculas de minúsculas (se normalizan automáticamente)

### Recargar automáticamente

El sistema monitorea `spam_domains.txt` continuamente. Si cambias el archivo, la recarga ocurre automáticamente en el siguiente ciclo (máx 5 segundos):

```
[WATCH] Spam domains actualizado detectado. Recargando...
[OK] Spam domains recargado exitosamente (17 dominios)
```

No necesitas reiniciar SuperAgent.

## 🔍 Cómo funciona la clasificación

Cuando SuperAgent procesa un email, sigue este flujo:

```
┌─────────────────────────────────┐
│ Email ingresa: From: user@domain.com
└──────────────┬──────────────────┘
               │
               ↓
    ┌──────────────────────┐
    │ ¿En whitelist.txt?   │
    └──────┬──────┬────────┘
           │ SÍ   │ NO
           ↓      ↓
       LEGÍTIMO  ┌────────────────────────┐
                 │ ¿En spam_domains.txt?  │
                 └──────┬──────┬──────────┘
                        │ SÍ   │ NO
                        ↓      ↓
                      SPAM  Análisis profundo
                            (KNN + LLM)
```

### Resultado de clasificación por spam_domains

Cuando un email se clasifica como SPAM por estar en spam_domains:

```json
{
  "classification": "spam",
  "confidence": 0.95,
  "risk_score": 85,
  "reasons": ["Dominio en spam_domains — clasificado automáticamente como SPAM"]
}
```

## 📊 Ejemplos de dominios

### Promociones y marketing agresivo
```txt
gympass.com          # Promociones constantes de fitness
getfit.app          # Otra plataforma de fitness
smartfit.com        # Idem
```

### Phishing conocido
```txt
paypal-security.net       # Falso (dominio oficial es paypal.com)
amazon-confirm.xyz        # Falso (dominio oficial es amazon.com)
apple-id-verify.com       # Falso (dominio oficial es apple.com)
```

### Financieros dudosos
```txt
creditoexpress.net   # Créditos rápidos con tasas sospechosas
instantcredit.biz    # Idem
```

## 🛠️ Integración con config.json

La ruta del archivo se configura en `config.json`:

```json
{
  "whitelist_path": "whitelist.txt",
  "spam_domains_path": "spam_domains.txt"
}
```

Para cambiar la ubicación:
```json
{
  "spam_domains_path": "/etc/phishing-detector/spam_domains.txt"
}
```

## 📈 Casos de uso

### 1. Acelerar clasificación de proveedores conocidos de spam

Si una empresa reporta 100 emails de `gympass.com` diarios, agregar este dominio a spam_domains evita análisis repetitivos:

**Antes**: 100 emails × 2-5 segundos LLM = 3-8 minutos
**Después**: 100 emails × <100ms = <10 segundos

### 2. Bloquear phishing conhecido

Cuando se detecta una campaña de phishing (ej: `fake-paypal.com`), agregarlo inmediatamente previene que más usuarios lo vean:

```bash
echo "fake-paypal.com" >> SuperAgent/spam_domains.txt
# ¡Recargado automáticamente! No requiere reinicio.
```

### 3. Feedback de revisión manual

Si un analista marca varios emails como SPAM y todos son del mismo dominio, agregar ese dominio acelera futuras clasificaciones.

## 🔐 Diferencia: whitelist.txt vs spam_domains.txt

| Aspecto | whitelist.txt | spam_domains.txt |
|---------|---------------|-----------------|
| **Propósito** | Dominios confiables | Dominios de spam/phishing |
| **Clasificación** | `legitimo` | `spam` |
| **Confianza** | 1.0 (100%) | 0.95 (95%) |
| **Risk score** | 0 | 85 |
| **Indicadores** | Se validan correctamente | Se reporta como automático |

## ⚠️ Notas importantes

- **No afecta estadísticas de confianza**: Los emails clasificados por spam_domains se reportan como tales en logs
- **No impide manual_review**: El sistema sigue registrando todas las clasificaciones
- **Orden de precedencia**: Whitelist se verifica primero, luego spam_domains
  - Si un dominio está en ambas listas, la clasificación de LEGÍTIMO (whitelist) toma precedencia

## 📞 Troubleshooting

### "El dominio se sigue clasificando como legítimo"
→ Verificar que no esté en `whitelist.txt` (tiene precedencia)

### "No se recarga el archivo automáticamente"
→ Verificar permisos de lectura en `spam_domains.txt`
→ Revisar logs: `tail -f SuperAgent/logs/phishing_analyzer.log | grep -i "spam_domains"`

### "Quiero remover un dominio"
→ Simplemente eliminar la línea del archivo y dejar que se recargue (< 5 segundos)

## 📝 Mantener spam_domains.txt actualizado

**Buenas prácticas:**

✅ Agregar dominios cuando:
- Múltiples usuarios reportan el mismo dominio
- Se detecta una campaña de phishing/spam
- Un proveedor hace promociones persistentes

❌ NO agregar:
- Dominios legítimos por error
- Dominios genéricos (.com, .net)
- Subdominios si ya existe el padre

Ejemplo correcto:
```txt
# ✅ CORRECTO
example.com        # Captura example.com, mail.example.com, etc.

# ❌ NO NECESARIO (si example.com ya está)
mail.example.com   # Redundante
shop.example.com   # Redundante
```
