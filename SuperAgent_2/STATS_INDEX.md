# 📊 Estadísticas - Índice de archivos

Referencia rápida de todos los archivos relacionados con estadísticas de SuperAgent_2.

## 🚀 Para empezar

1. **Leer primero**: [README.md](README.md) - Sección "📊 Sistema de Estadísticas de Uso"
2. **Ejecutar demo**: `python quickstart_stats.py`
3. **Ver estadísticas**: `python view_stats.py`

---

## 📁 Archivos principales

### Módulos (importables)

| Archivo | Líneas | Propósito |
|---------|--------|----------|
| **usage_stats.py** | 325 | Sistema central de estadísticas. Usa: `from usage_stats import UsageStats` |

### Herramientas CLI

| Archivo | Líneas | Propósito | Uso |
|---------|--------|----------|-----|
| **view_stats.py** | 200+ | Visualizador de estadísticas desde terminal | `python view_stats.py [--month YYYY-MM] [--year YYYY] [--report]` |
| **ejemplo_stats.py** | 100+ | Demo que simula casos y muestra sistema funcionando | `python ejemplo_stats.py` |
| **quickstart_stats.py** | 140+ | Guía interactiva para comenzar | `python quickstart_stats.py` |

### Datos

| Archivo | Formato | Descripción |
|---------|---------|-------------|
| **stats.json** | JSON | Almacenamiento persistente de estadísticas. Se crea automáticamente en primera ejecución. **NO EDITAR MANUALMENTE** |

### Documentación

| Archivo | Tema | Audiencia |
|---------|------|-----------|
| **README.md** | Descripción general del sistema | Usuarios finales |
| **STATS.md** | Documentación técnica completa | Desarrolladores |
| **CAMBIOS_ESTADISTICAS.md** | Resumen de cambios implementados | Administradores |
| **este archivo** | Índice de referencia | Todos |

---

## 🎯 Casos de uso

### Ver estadísticas mensuales (más común)
```bash
python view_stats.py
```
Muestra gráficas de barra de clasificaciones, decisiones y precisión del KNN.

### Ver mes específico
```bash
python view_stats.py --month 2025-01
```

### Generar reporte formateado
```bash
python view_stats.py --report
```
Salida: texto legible con resúmenes históricos.

### Correr demo
```bash
python ejemplo_stats.py
```
Simula 11 casos y muestra cómo funciona el sistema internamente.

### Verificar instalación
```bash
python quickstart_stats.py
```
Guía interactiva paso a paso.

---

## 🔧 Integración en código

### Inicializar (en superagent_2.py)
```python
from usage_stats import UsageStats

class SuperAgent2:
    def __init__(self):
        self.stats = UsageStats()  # Se carga automáticamente
```

### Registrar un caso
```python
# Email clasificado como spam, decidido por KNN
self.stats.record_case("spam", "knn", knn_was_correct=True)

# Email de whitelist
self.stats.record_case("legitimo", "whitelist")

# Email que necesitó LLM
self.stats.record_case("sospechoso", "llm")
```

### Generar reporte
```python
report = self.stats.generate_report("reporte_enero.txt")
print(report)
```

---

## 📈 Estructura de datos

### stats.json (automático)
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
    }
  }
}
```

---

## 🎓 Jerarquía de documentación

```
README.md (visión general)
    ↓
    ├─→ Para usuarios: ver view_stats.py
    ├─→ Para técnicos: leer STATS.md
    └─→ Para admins: revisar CAMBIOS_ESTADISTICAS.md

quickstart_stats.py (verificación rápida)
    ↓
    ├─→ Si todo OK: empezar con view_stats.py
    └─→ Si hay problemas: consultar Troubleshooting en STATS.md
```

---

## ✅ Checklist de verificación

Después de descargar/actualizar:

- [ ] Ejecutar: `python quickstart_stats.py` (debe salir sin errores)
- [ ] Verificar: `stats.json` existe en SuperAgent_2/
- [ ] Probar: `python view_stats.py` (muestra resumen)
- [ ] Demo: `python ejemplo_stats.py` (muestra ejemplo funcionando)
- [ ] Leer: Primeras líneas de [README.md](README.md) - sección estadísticas

---

## 🚨 Problemas comunes

| Problema | Solución |
|----------|----------|
| `ModuleNotFoundError: No module named 'usage_stats'` | Verifica que estés en carpeta SuperAgent_2/ |
| `stats.json no se crea` | Verifica permisos de escritura en SuperAgent_2/ |
| `No veo datos` | Asegúrate de que SuperAgent_2 esté procesando emails |
| `KNN accuracy muy baja` | Normal al inicio, mejora con más ejemplos |

---

## 🔗 Referencias cruzadas

- **Modelo KNN**: ver [CAMBIOS_KNN.md](CAMBIOS_KNN.md) en SuperAgent_2/
- **Integración completa**: ver [STATS.md](STATS.md)
- **Uso desde Python**: revisar docstrings en [usage_stats.py](usage_stats.py)

---

## 📞 Soporte

Para preguntas:

1. Consulta la sección relevante en [STATS.md](STATS.md)
2. Ejecuta `python view_stats.py --help` para opciones CLI
3. Revisa logs en `logs/superagent_2.log` para debug

---

**Última actualización**: Enero 2025  
**Sistema**: Funcionando correctamente ✅  
**Mantener actualizado**: Sí, agregar nuevas métricas según sea necesario
