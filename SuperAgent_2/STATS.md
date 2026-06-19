# 📊 Sistema de Estadísticas de SuperAgent_2

Documentación técnica del sistema de estadísticas de uso y monitoreo del modelo KNN.

## Visión general

SuperAgent_2 registra automáticamente estadísticas mensuales sobre cada email procesado, permitiendo:

1. **Monitoreo del modelo**: Validar que el KNN mejora con el tiempo
2. **Análisis de cobertura**: Ver si whitelist, KNN o LLM dominan
3. **Auditoría**: Registrar cómo se clasificó cada email y por qué
4. **ROI de LLM**: Cuantificar el ahorro de llamadas a Ollama

---

## Integración en SuperAgent_2

### 1. Inicialización

En `superagent_2.py`:

```python
from usage_stats import UsageStats

class SuperAgent2:
    def __init__(self, config_path="config.json"):
        ...
        self.stats = UsageStats()  # Se carga automáticamente
```

### 2. Registro de casos

Se registra automáticamente en `_handle_result()`:

```python
def _handle_result(self, file_path, analysis, knn_result=None, classification_source="llm"):
    classification = analysis.classification  # "legitimo", "spam", "sospechoso"
    
    # Registrar con fuente de decisión
    self.stats.record_case(
        classification=classification,
        source=classification_source,  # "whitelist", "knn", "llm"
        knn_was_correct=(knn_result["classification"] == classification) if knn_result else None
    )
```

### 3. Flujo de fuentes

- **whitelist**: Email coincidió con lista blanca → clasificación inmediata
- **knn**: Clasificador KNN tuvo confianza > umbral dinámico
- **llm**: Análisis profundo con Ollama (KNN tuvo confianza baja)

---

## Clase UsageStats

Ubicación: `SuperAgent_2/usage_stats.py`

### Constructor

```python
stats = UsageStats()  # Carga stats.json automáticamente si existe
```

### Métodos principales

#### `record_case(classification, source, knn_was_correct=None)`

Registra un caso procesado.

**Parámetros**:
- `classification` (str): "legitimo" | "spam" | "sospechoso"
- `source` (str): "whitelist" | "knn" | "llm"
- `knn_was_correct` (bool|None): True si KNN acertó, False si falló, None si no aplica

**Ejemplo**:
```python
# Email whitelist
stats.record_case("legitimo", "whitelist")

# Email clasificado por KNN con acierto
stats.record_case("spam", "knn", True)

# Email que necesitó Ollama
stats.record_case("sospechoso", "llm")
```

#### `get_month_summary(year=None, month=None)`

Retorna resumen de mes específico.

**Retorna**: dict con:
```python
{
    "year": 2025,
    "month": 1,
    "total": 156,
    "by_classification": {"legitimo": 50, "spam": 60, "sospechoso": 46},
    "by_classification_pct": {"legitimo": 32.1, "spam": 38.5, "sospechoso": 29.5},
    "by_source": {"whitelist": 30, "knn": 85, "llm": 41},
    "by_source_pct": {"whitelist": 19.2, "knn": 54.5, "llm": 26.3},
    "knn_accuracy": {"correct": 78, "incorrect": 7},
    "knn_accuracy_pct": 91.8
}
```

#### `get_year_summary(year)`

Retorna agregación de todo el año.

#### `generate_report(output_file=None)`

Genera reporte formateado y lo guarda.

**Retorna**: string con reporte legible

**Ejemplo**:
```python
report = stats.generate_report("reporte_enero_2025.txt")
print(report)
```

---

## Archivo de datos: stats.json

Ubicación: `SuperAgent_2/stats.json`

### Estructura

```json
{
  "2025": {
    "1": {
      "total": 156,
      "by_classification": {
        "legitimo": 50,
        "spam": 60,
        "sospechoso": 46
      },
      "by_source": {
        "whitelist": 30,
        "knn": 85,
        "llm": 41
      },
      "knn_accuracy": {
        "correct": 78,
        "incorrect": 7
      }
    },
    "2": {
      "total": 203,
      ...
    }
  }
}
```

### Interpretación

- **total**: Emails procesados en ese mes
- **by_classification**: Cuántos de cada tipo
- **by_source**: De dónde vino la decisión
- **knn_accuracy**: De los que usó KNN, cuántos acertó

---

## Herramientas CLI

### view_stats.py

Ver estadísticas desde línea de comandos.

```bash
# Mes actual
python view_stats.py

# Mes específico
python view_stats.py --month 2025-01

# Año completo
python view_stats.py --year 2025

# Reporte formateado
python view_stats.py --report
```

Salida ejemplo:
```
📅 Estadísticas del 01/2025
============================================================

Total de casos procesados: 156

Clasificación de emails:
  legitimo         50 ( 32.1%) ██████████░░░░░░░░░░
  spam             60 ( 38.5%) ███████████████░░░░░░
  sospechoso       46 ( 29.5%) █████████░░░░░░░░░░░

Decisiones por:
  whitelist        30 ( 19.2%) ████░░░░░░░░░░░░░░░░
  knn              85 ( 54.5%) ███████████░░░░░░░░░░
  llm              41 ( 26.3%) █████░░░░░░░░░░░░░░░

Rendimiento del KNN:
  Aciertos: 78 / 85 (91.8%)
  Errores:  7 / 85 (8.2%)
```

### ejemplo_stats.py

Script de demostración que simula casos y muestra el sistema funcionando.

```bash
python ejemplo_stats.py
```

---

## Interpretación de datos

### Indicadores clave

| Métrica | Buena señal | Preocupante |
|---------|-------------|------------|
| **KNN accuracy** | > 90% | < 70% |
| **KNN usage %** | > 50% | < 30% |
| **LLM usage %** | 20-30% | > 50% |
| **Whitelist %** | 10-30% | > 60% |

### Escenarios

**Escenario A: Modelo maduro**
```
Total: 500
Legítimos: 150 (30%)
Spam: 250 (50%)
Sospechosos: 100 (20%)

Decisiones:
- Whitelist: 80 (16%)
- KNN: 300 (60%) ← Modelo muy usado
- LLM: 120 (24%)

KNN accuracy: 96% ✓ Excelente
```
**Interpretación**: El modelo está maduro, poco desperdicio en LLM.

---

**Escenario B: Modelo en desarrollo**
```
Total: 100
Legítimos: 20 (20%)
Spam: 50 (50%)
Sospechosos: 30 (30%)

Decisiones:
- Whitelist: 15 (15%)
- KNN: 25 (25%) ← Modelo poco usado
- LLM: 60 (60%) ← Depende mucho

KNN accuracy: 88% ✓ Normal pero sigue aprendiendo
```
**Interpretación**: Modelo joven, normal que dependa de LLM. Mejorará con más ejemplos.

---

**Escenario C: Problemas**
```
Total: 300
Legítimos: 100 (33%)
Spam: 100 (33%)
Sospechosos: 100 (34%) ← Demasiados sospechosos

Decisiones:
- Whitelist: 200 (67%) ← Excesivamente dependiente
- KNN: 50 (17%) ← Modelo infrautilizado
- LLM: 50 (17%)

KNN accuracy: 64% ✗ Muy baja
```
**Interpretación**: 
- Whitelist muy grande o muy permisivo
- KNN tiene problemas (features insuficientes o datos ruidosos)
- Demasiados falsos positivos (sospechosos)

---

## Casos de uso

### 1. Monitoreo semanal

```python
from usage_stats import UsageStats
from datetime import datetime, timedelta

stats = UsageStats()

# Comparar semana anterior vs actual
today = datetime.now()
this_week = stats.get_month_summary()

print(f"Esta semana: {this_week['total']} emails")
print(f"KNN accuracy: {this_week['knn_accuracy_pct']:.1f}%")
print(f"LLM usage: {this_week['by_source_pct']['llm']:.1f}%")
```

### 2. Reporte mensual automatizado

```bash
# Generar reporte de fin de mes
python view_stats.py --report > reporte_$(date +%Y-%m).txt

# Enviar por email (requiere configuración SMTP)
# ... integración con mailer
```

### 3. Dashboard en supervisión continua

```python
class Supervisor:
    def check_health(self):
        stats = UsageStats()
        summary = stats.get_month_summary()
        
        if summary['knn_accuracy_pct'] < 80:
            self.alert("KNN accuracy baja", severity="WARNING")
        
        if summary['by_source_pct']['llm'] > 40:
            self.alert("LLM usage muy alto", severity="INFO")
```

---

## Mantenimiento

### Limpiar datos (archivar año anterior)

```python
import json
from pathlib import Path

# Backup
Path("stats_2024_backup.json").write_text(Path("stats.json").read_text())

# Limpiar
stats_data = json.loads(Path("stats.json").read_text())
if "2024" in stats_data:
    del stats_data["2024"]
Path("stats.json").write_text(json.dumps(stats_data, indent=2))
```

---

## Limitaciones y mejoras futuras

**Limitaciones actuales**:
- No registra timestamp de cada email (solo mes/año)
- No diferencia entre usuarios/dominios
- No detecta patrones temporales (emails por hora/día)

**Mejoras futuras** (v2.0):
- Timestamp detallado (para análisis temporal)
- Filtros por remitente/dominio
- Gráficos HTML interactivos
- Alertas automáticas cuando métricas salen de rango
- Integración con dashboard web (Grafana, etc.)

