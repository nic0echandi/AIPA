# 🏗️ SuperAgent - Arquitectura del Sistema

**Versión**: 2.0 (Actualizada Julio 2026)  
**Estado**: Producción - Consolidada

---

## 📊 Estructura del Proyecto

### Ubicación Única

```
/home/user/Documents/MyGithub/AIPA/SuperAgent/
```

**Carpetas eliminadas**:
- ❌ `agent/` - Consolidado en SuperAgent/
- ❌ `testing/` - Testing integrado en SuperAgent/
- ❌ `SuperAgent/` - v1.0 legado, consolidado en SuperAgent/ (test_superagent.py)

---

## 🗂️ Estructura de Directorios (Actual)

```
SuperAgent/
│
├── 📄 DOCUMENTACIÓN
│   ├── README.md                    ← Documento principal (45KB, índice completo)
│   ├── ARCHITECTURE.md              ← Esta arquitectura
│   └── requirements.txt
│
├── 🔧 CORE COMPONENTS
│   ├── superagent_2.py              ← Agente principal (ProductionON)
│   ├── phishingAnalizer.py          ← Análisis profundo con LLM
│   ├── knn_classifier.py            ← Clasificador KNN (33 features)
│
├── ✨ ETAPA 1: VALIDACIÓN CRUZADA
│   └── llm_validation.py            ← Valida decisiones de LLM (7.8KB)
│
├── ✨ ETAPA 2: CONTROL DE CALIDAD
│   └── data_quality.py              ← Valida datos antes de entrenar (6.0KB)
│
├── ✨ ETAPA 3: ANÁLISIS AVANZADO
│   └── compare_algorithms.py        ← Compara KNN vs Random Forest
│
├── 🧪 TESTING & REENTRENAMIENTO
│   ├── test_superagent.py           ← Test runner (3 modos: quick/full/train)
│   ├── test_emails/                 ← Emails de prueba (aislado de producción)
│   │   └── README.md
│   └── test_results/                ← Resultados de tests (JSON)
│
├── 📊 UTILIDADES & ESTADÍSTICAS
│   ├── view_stats.py                ← Visualiza estadísticas
│   ├── usage_stats.py               ← Registra uso del sistema
│   ├── verify_code.py               ← Verifica integridad de código
│   ├── check_config.py              ← Verifica configuración
│   ├── debug_parser.py              ← Debuggea parser de emails
│   ├── demo_knn.py                  ← Demo de KNN
│   ├── quick_start.py               ← Inicio rápido
│   └── quickstart_stats.py           ← Demo de estadísticas
│
├── ⚙️ CONFIGURACIÓN
│   ├── config.json                  ← Configuración principal
│   └── whitelist.txt                ← Dominios de confianza (recarga automática)
│
├── 💾 DATOS & LOGS
│   ├── logs/                        ← Logs del sistema
│   ├── manual_review/               ← Casos dudosos (Etapa 1)
│   ├── quarantine/                  ← Datos problemáticos (Etapa 2)
│   ├── stats.json                   ← Estadísticas acumuladas
│   ├── knn_model.pkl                ← Modelo KNN entrenado
│   ├── knn_model.pkl.backup         ← Backup del modelo
│   └── knn_scaler.pkl               ← Scaler del KNN
│
├── 📁 DIRECTORIOS EXTERNOS (parent)
│   ├── ../ingress/                  ← Emails de producción (entrada)
│   ├── ../processed/                ← Emails procesados
│   │   ├── legitimo/
│   │   ├── spam/
│   │   └── sospechoso/
│   └── ../analysis_results/         ← Resultados de análisis (históricos)
│
└── 🚀 SCRIPTS DE INICIO
    └── quick_train_example.sh       ← Helper para entrenar KNN
```

---

## 🔄 Flujo de Procesamiento

```
┌─────────────────────────────────────────────────────────┐
│ 1. INGRESS (Email entra)                                │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│ 2. WHITELIST CHECK (superagent_2.py)                    │
│    - Recarga automática cada 5 segundos                 │
└────────────┬──────────────────────────────────────────┘
             │
    ┌────────┴─────────┐
    │                  │
    ↓                  ↓
✓ WHITELISTED    ┌──────────────────┐
│                │ 3. KNN RÁPIDO    │
│                │ (5ms, 33 features)
│                └─────┬────────────┘
│                      │
│               ┌──────┴──────┐
│               ↓             ↓
│        CONFIANZA >85%  <85%
│               │             ↓
└───→ LEGITIMO  │       ┌──────────────┐
                │       │ 4. LLM ANÁLISIS
                │       │ (Ollama/Claude)
                └───────┤       │
                        └─┬─────┘
                          ↓
        ┌─────────────────────────────────┐
        │ 5. ETAPA 1: VALIDACIÓN CRUZADA  │
        │ llm_validation.py               │
        │ - KNN alineado?                 │
        │ - Risk score alineado?          │
        │ - Heurísticas confirman?        │
        └────┬──────────────────┬─────────┘
             │                  │
    ALTO >70%│                  │DUDOSO
             ↓                  ↓
        ACTUAR DIRECTO    manual_review/
             │                  │
             └──────┬───────────┘
                    ↓
        ┌─────────────────────────────────┐
        │ 6. ETAPA 2: DATA QUALITY        │
        │ data_quality.py                 │
        │ - Confianza ≥ 65%?              │
        │ - Risk score alineado?          │
        │ - Headers completos?            │
        └────┬──────────────────┬─────────┘
             │                  │
        OK ↓                      │PROBLEMÁTICO
             │                  ↓
        AGREGAR A KNN       quarantine/
        (entrenar)               │
             │                   │
             └───────┬───────────┘
                     ↓
        ┌──────────────────────┐
        │ 7. ACTUALIZAR KNN    │
        │ (Aprendizaje activo) │
        └──────────────────────┘
```

---

## 🏛️ Componentes Principales

### 1. **superagent_2.py** (Agente Principal)
- **Función**: Orquesta el flujo completo
- **Características**:
  - FileSystemWatcher: Monitorea ingress/
  - Thread-safe con cola de procesamiento
  - Recarga automática de whitelist (cada 5s)
  - Integración con 3 etapas de validación
  - Logging estructurado

### 2. **knn_classifier.py** (Modelo Rápido)
- **Función**: Clasificación rápida (5ms)
- **Features**: 33 (24 originales + 9 nuevos)
- **Características**:
  - KDTree para búsqueda rápida
  - Persistencia con joblib
  - Aprendizaje activo (add_training_example)
  - Estadísticas en tiempo real

### 3. **phishingAnalizer.py** (Análisis Profundo)
- **Función**: Análisis detallado con LLM
- **Soporta**:
  - Ollama (local)
  - Anthropic Claude (API)
- **Calcula**:
  - Risk score (0-100)
  - Indicadores de phishing
  - URLs y patrones sospechosos

### 4. **llm_validation.py** (Etapa 1) ✨
- **Función**: Valida decisiones de LLM antes de actuar
- **Criterios** (25% cada uno):
  1. ¿KNN está de acuerdo?
  2. ¿Heurísticas simples confirman?
  3. ¿Risk score alineado?
  4. ¿LLM reporta confianza alta?
- **Salida**: Casos dudosos → manual_review/

### 5. **data_quality.py** (Etapa 2) ✨
- **Función**: Protege el modelo KNN de datos corruptos
- **Valida**:
  - Confianza ≥ 65%
  - Risk score alineado
  - Headers completos
  - Sin encoding sospechoso
- **Salida**: Datos problemáticos → quarantine/

### 6. **compare_algorithms.py** (Etapa 3)
- **Función**: Compara KNN vs Random Forest
- **Genera**: Reporte HTML con métricas
- **Decide**: Cuándo escalar a RF

### 7. **test_superagent.py** (Testing & Entrenamiento)
- **3 Modos**:
  - `--mode quick`: Solo KNN
  - `--mode full`: KNN + LLM (sin entrenar)
  - `--mode train`: KNN + LLM + **ENTRENA el modelo**
- **Salida**: test_results/test_results.json

---

## 🚀 Flujo de Inicio

```bash
# 1. Navegar a directorio
cd /home/user/Documents/MyGithub/AIPA/SuperAgent

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar (editar config.json)
# - SMTP para notificaciones
# - IRIS para alertas
# - LLM provider (Ollama/Claude)

# 4. Iniciar agente
python superagent_2.py --config config.json

# Logs mostrarán:
# ✓ Monitoreo de whitelist activado
# ✓ Validadores cargados: LLM + Data Quality
# SuperAgent iniciado. Observando ingress/...
```

---

## 📦 Dependencias Principales

```python
# requirements.txt contiene:
numpy              # Procesamiento numérico
pandas             # DataFrames
scikit-learn       # KNN, Random Forest, métricas
joblib             # Persistencia de modelos
requests           # API calls (IRIS, LLM)
anthropic          # Claude API (opcional)
```

---

## 🔐 Seguridad y Monitoreo

### Recarga Automática de Whitelist
```python
# Monitorea cambios cada 5 segundos
def _check_and_reload_whitelist(self):
    if archivo_cambió:
        recarga whitelist en memoria
        log info: "Whitelist recargado"
```

### Logging Completo
```
logs/superagent_2.log  # Rotativo, 50MB max
- Acciones de clasificación
- Errores y excepciones
- Estadísticas mensuales
```

### Auditoría
```
manual_review/     # Casos que requieren revisión (Etapa 1)
quarantine/        # Datos cuestionables (Etapa 2)
stats.json         # Estadísticas acumuladas
```

---

## 📊 Métricas de Éxito

| Métrica | Target | Status |
|---------|--------|--------|
| Precisión | >92% | ✅ Implementado |
| Falsos Positivos | <5% | ✅ Etapa 1 |
| Falsos Negativos | <3% | ✅ Etapa 2 |
| Latencia KNN | <5ms | ✅ Validado |
| Latencia LLM | <2s | ⏳ Depends on LLM |
| Auditabilidad | 100% | ✅ manual_review/ + quarantine/ |

---

## 🛠️ Mantenimiento

### Reentrenar KNN
```bash
# Modo entrenamiento
python test_superagent.py --mode train --input test_emails

# Ver resultados
cat test_results/test_results.json | jq '.training'
```

### Actualizar Whitelist
```bash
# Agregar dominio
echo "trusted-domain.com" >> whitelist.txt

# Automático en próximos 5 segundos, sin reinicio
```

### Backup de Modelo
```bash
# Ya existe:
knn_model.pkl.backup    # Backup automático
```

---

## 📝 Cambios Recientes

### Consolidación (Julio 2024)
- ❌ Eliminada carpeta `/agent/` - archivos integrados en SuperAgent/
- ❌ Eliminada carpeta `/testing/` - testing integrado en test_superagent.py
- ✅ Recarga automática de whitelist sin downtime
- ✅ Arquitectura única y centralizada

---

## 🎯 Próximos Pasos

### Etapa 4 (Planeada)
- A/B testing con sistema anterior
- Optimización de parámetros KNN
- Deployment a producción

### Etapa 5 (Escalabilidad)
- Soporte para múltiples LLMs en paralelo
- Embeddings para análisis más profundo
- Multi-worker processing
