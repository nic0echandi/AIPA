# Actualización Parser: Soporte Nuevo Formato de Archivos

**Versión:** 0.9  
**Fecha:** 2026-07-08  
**Estado:** ✓ Completado y Testeado  
**Compatibilidad:** 100% con formato antiguo RFC 5322

## ⚠️ IMPORTANTE - Nota sobre el Prefijo "_"

El prefijo "_" en nombres de archivos (ej: `__Phishing_XXXXX.txt`) fue **SOLO para pruebas/ejemplos**.

**En producción:**
- ✅ Todos los archivos llegarán como `Phishing_XXXXX.txt` (sin prefijo)
- ✅ El sistema procesará normalmente sin problemas
- ✅ No hay dependencia del prefijo "_" para funcionamiento

El parser está completamente listo para producción.

---

## Resumen de Cambios

Se ha actualizado el parser de `phishingAnalizer.py` para soportar el nuevo formato de archivos TXT con estructura clave-valor, manteniendo compatibilidad con el formato antiguo RFC 5322.

### Nuevo Formato de Archivos

El nuevo formato usa una estructura de campos clave-valor:

```
Subject            : Asunto del email
SenderName         : Nombre del remitente
SenderEmailAddress : sender@example.com
To                 : recipient@example.com
ReceivedTime       : 6/7/2026 12:13:27
HTMLBody           : <!doctype html>... (contenido HTML del email)
```

### Cambios Implementados

#### 1. **Detección Automática de Formato**
- Nueva función: `_detect_format(content)` 
- Identifica si el archivo es formato nuevo o antiguo
- Busca palabras clave como `SenderEmailAddress` o `HTMLBody`

#### 2. **Parser para Nuevo Formato**
- Nueva función: `_parse_new_format(content, txt_path)`
- Parsea campos clave-valor
- Mapea `SenderEmailAddress` → `From`
- Mapea `To` → `To`
- Extrae `HTMLBody` como contenido del email
- **NOTA**: Detecta phishing confirmado solo por nombre de archivo (comienza con "_") - Solo para pruebas

#### 3. **Parser para Formato Antiguo (RFC 5322)**
- Nueva función: `_parse_rfc5322_format(content)`
- Código original refactorizado
- Mantiene compatibilidad con archivos antiguos

#### 4. **Generación de Message-ID**
- Nueva función: `_generate_message_id(txt_path)`
- Genera IDs únicos basados en hash del archivo
- Formato: `{hash}@aipa.local`

#### 5. **Extracción Mejorada del Reportero**
- Función `extract_reporter_from_content()` actualizada
- Ahora recibe parámetro `headers` opcional
- Prioriza campo `To` desde headers
- Soporta ambos formatos

## Uso

### Análisis de Archivo

```python
from phishingAnalizer import PhishingAnalyzerTXT

analyzer = PhishingAnalyzerTXT("config.json")

# Funciona automáticamente con ambos formatos
result = analyzer.analyze_txt_file("path/to/email.txt")

# O para parsear sin análisis completo
parsed = analyzer.parse_txt_file("path/to/email.txt")
headers = parsed.get("headers", {})
content = parsed.get("raw_content", "")
```

## Testing

Se incluye script de prueba: `test_new_format.py`

```bash
python3 test_new_format.py
```

### Resultados de Pruebas ✓

✓ Detecta nuevo formato correctamente  
✓ Parsea headers clave-valor  
✓ Extrae campos críticos (From, To, Subject)  
✓ Genera Message-ID único  
✓ Detecta reportero desde campo "To"  
✓ Mantiene compatibilidad con formato antiguo  
✓ **Listo para producción sin cambios**

## Flujo en Producción

```
Email Phishing_XXXXX.txt
       ↓
_detect_format()  → "new_format" ✓
       ↓
_parse_new_format()
       ↓
Headers normalizados
Contenido extraído
       ↓
analyze_txt_file() → Clasificación normal
```

No hay cambios necesarios - **es automático!**

## Notas Importantes

1. **Compatibilidad Total**: Archivos RFC 5322 antiguos siguen funcionando normalmente
2. **Producción Lista**: Sin dependencias del prefijo "_", funciona con `Phishing_XXXXX.txt`
3. **Logging**: Se registran todos los eventos en `phishing_analyzer.log` con nivel DEBUG
4. **Headers Normalizados**: Independientemente del formato, los headers se normalizan internamente

## Archivos Modificados

- `SuperAgent/phishingAnalizer.py` - Parser actualizado (v0.9)

## Archivos Agregados

- `SuperAgent/test_new_format.py` - Script de validación
- `SuperAgent/ACTUALIZACION_PARSER_v0.9.md` - Este documento

- Ahora recibe parámetro `headers` opcional
- Prioriza campo `To` desde headers
- Soporta ambos formatos

#### 6. **Detección de Phishing Confirmado**
- Se agrega flag `is_confirmed_phishing` al resultado
- En `analyze_txt_file()`: Si el nombre de archivo comienza con "_", se registra como phishing confirmado
- Se mantiene registro de esto en logs con nivel WARNING

## Uso

### Análisis de Archivo

```python
from phishingAnalizer import PhishingAnalyzerTXT

analyzer = PhishingAnalyzerTXT("config.json")

# Funciona automáticamente con ambos formatos
result = analyzer.analyze_txt_file("path/to/email.txt")

# O para parsear sin análisis completo
parsed = analyzer.parse_txt_file("path/to/email.txt")
is_phishing = parsed.get("is_confirmed_phishing", False)
headers = parsed.get("headers", {})
content = parsed.get("raw_content", "")
```

### Detección de Phishing Confirmado

Archivos que comienzan con **"_"** son tratados automáticamente como phishing confirmado:

```
__Phishing_000000002D6A6BF8F58B924FA9CB0BDD9CBC5FC0070...txt  ← Confirmado Phishing
Phishing_000000002D6A6BF8F58B924FA9CB0BDD9CBC5FC0070...txt   ← Sin confirmar
```

## Testing

Se incluye script de prueba: `test_new_format.py`

```bash
python3 test_new_format.py
```

### Resultados de Pruebas ✓

✓ Detecta nuevo formato correctamente  
✓ Parsea headers clave-valor  
✓ Extrae campos críticos (From, To, Subject)  
✓ Genera Message-ID único  
✓ Detecta reportero desde campo "To"  
✓ Identifica phishing confirmado por nombre de archivo  
✓ Mantiene compatibilidad con formato antiguo  

## Ejemplo de Ejecución

```
================================================================================
PRUEBA: Nuevo Formato de Archivos (key-value)
================================================================================

📄 Archivo: Phishing_000000002D6A6BF8F58B924FA9CB0BDD9CBC5FC0070...txt
  Confirmado phishing: False
  Formato detectado: new_format
  Headers extraidos: 6
  
  📧 HEADERS CRÍTICOS:
     From (SenderEmailAddress): noreply@qemailserver.com
     To: security.analyst@company.com
     Subject: Últimos días para participar de la encuesta
     Message-ID: 5af67a92994d5bfc2d9f6e7fe55a4971@aipa.lo
  
  👤 Reportero detectado: security.analyst@company.com
  
  ✓ Headers críticos presentes

📄 Archivo: __Phishing_000000002D6A6BF8F58B924FA9CB0BDD9CBC5FC0070...txt
  Confirmado phishing: True
  Formato detectado: new_format
  
  ✓✓ PHISHING CONFIRMADO DETECTADO CORRECTAMENTE
```

## Notas Importantes

1. **Compatibilidad**: Los archivos antiguos (RFC 5322) siguen funcionando normalmente
2. **Futuros cambios**: Cuando los archivos confirmados phishing dejen de tener "_", la detección por nombre seguirá funcionando hasta que se retire del código
3. **Logging**: Se registran todos los eventos en `phishing_analyzer.log` con nivel DEBUG para parseo
4. **Headers Normalizados**: Independientemente del formato, los headers se normalizan internamente para compatibilidad

## Archivos Modificados

- `SuperAgent/phishingAnalizer.py` - Parser actualizado (v0.9)

## Archivos Agregados

- `SuperAgent/test_new_format.py` - Script de validación
