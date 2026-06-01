# Estructura de SuperAgent_2

## 📁 Contenido de la carpeta

```
SuperAgent_2/
│
├── superagent_2.py           ⭐ SCRIPT PRINCIPAL (ejecutar esto)
├── config.json               ⚙️  CONFIGURACIÓN (SMTP, IRIS, LLM)
│
├── 📖 DOCUMENTACIÓN
├── README.md                 └─ Descripción general del agente
├── SETUP.md                  └─ Guía completa de instalación
├── POWER_AUTOMATE.md         └─ Integración con Power Automate
│
├── 🛠️ HERRAMIENTAS
├── check_config.py           └─ Validar configuración
├── test_examples.py          └─ Crear emails de prueba
├── install_service.ps1       └─ Instalar como Windows Service
│
├── 📝 ARCHIVOS DE SOPORTE
├── whitelist.txt             └─ Lista de remitentes confiables
├── requirements.txt          └─ Dependencias Python
│
└── 📂 CARPETA DE LOGS (creada automáticamente)
    └── logs/
        └── superagent_2.log  ← Logs de ejecución
```

## 🚀 Inicio rápido

### 1. Verificar ambiente
```bash
python check_config.py
```

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 3. Configurar SMTP y IRIS
Editar `config.json` con tus credenciales

### 4. Crear archivos de prueba (opcional)
```bash
python test_examples.py
```

### 5. Ejecutar agente
```bash
python superagent_2.py
```

Verás logs en consola y en `logs/superagent_2.log`

## 📊 Flujo de datos

```
┌─────────────────────┐
│  Fuente de archivos │
│  (Power Automate,   │
│   procesos, etc.)   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   ingress/          │  ← Archivos .txt se depositan aquí
│  (carpeta monitor)  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  SuperAgent_2       │
│  - FileWatcher      │  ← Detecta nuevos .txt
│  - Parser           │  ← Extrae headers
│  - KNN rápido       │  ← Clasificación inicial
│  - LLM profundo     │  ← Análisis (si confianza baja)
│  - Acciones         │  ← IRIS, SMTP, etc.
└──────────┬──────────┘
           │
      ┌────┼────┐
      │    │    │
      ▼    ▼    ▼
  ┌───────┴──────┴───────┐
  │  processed/          │
  ├─ legitimo/  (emails válidos)
  ├─ spam/      (no deseados)
  └─ sospechoso/ (phishing → IRIS)
```

## 🔑 Componentes principales

### superagent_2.py

**Clase `SuperAgent2`**:
- `__init__()` - Inicialización con config
- `start()` - Inicia el agente (bloqueante)
- `_file_watcher_loop()` - Monitor de ingress/
- `_worker_loop()` - Procesa cola de archivos
- `_process_file()` - Parseo y clasificación
- `_build_analysis_from_knn()` - Análisis desde KNN
- `_handle_result()` - Acciones post-análisis
- `_register_case_in_iris()` - Registra en IRIS
- `_notify_reporter()` - Envía email
- `_move_to_processed()` - Archivo a carpeta destino
- `_update_knn()` - Aprendizaje activo

### Dependencias locales

Importa desde `../agent/`:
- `knn_classifier.KNNClassifier` - Clasificador rápido
- `phishingAnalizer.PhishingAnalyzerTXT` - Análisis profundo
- `phishingAnalizer.EmailAnalysis` - Estructura de datos

## ⚙️ Configuración (config.json)

```json
{
  "log_level": "INFO",
  "log_dir": "logs",
  "ingress_dir": "../ingress",
  "processed_dir": "../processed",
  "analysis_dir": "../analysis_results",
  "knn_confidence_threshold": 0.85,
  
  // LLM para análisis profundo
  "llm_provider": "ollama",
  "ollama_url": "http://localhost:11434/api/generate",
  "ollama_model": "llama3.2",
  
  // Notificaciones por email
  "smtp": {
    "host": "smtp.gmail.com",
    "port": 587,
    "username": "tu_email@gmail.com",
    "password": "tu_app_password",
    "use_tls": true,
    "from": "security-alerts@example.com"
  },
  
  // Registro de casos de seguridad
  "iris_dfir": {
    "url": "https://iris.company.com/api/v1/cases",
    "api_key": "tu_api_key",
    "verify_ssl": true
  }
}
```

## 📝 Logs

Archivo: `logs/superagent_2.log`

Formato: `TIMESTAMP | LEVEL | LOGGER | MESSAGE`

Ejemplo:
```
2026-05-28T14:30:45 | INFO     | superagent_2.main | ─────────────────────────────────────────────────────────────────
2026-05-28T14:30:45 | INFO     | superagent_2.main | Procesando: phishing_20260128_013237.txt
2026-05-28T14:30:46 | INFO     | superagent_2.main | KNN directo (92% confianza) → SOSPECHOSO
2026-05-28T14:30:47 | INFO     | superagent_2.main | RESULTADO → SOSPECHOSO | Score: 78/100 | Confianza: 92%
2026-05-28T14:30:47 | INFO     | superagent_2.main | → Registrando caso en IRIS...
2026-05-28T14:30:48 | INFO     | superagent_2.main | Caso registrado en IRIS: phishing_20260128_013237
2026-05-28T14:30:49 | INFO     | superagent_2.main | Notificación enviada a reporter@company.com (sospechoso)
2026-05-28T14:30:49 | INFO     | superagent_2.main | Archivo movido → processed/sospechoso/20260528_143049_phishing_20260128_013237.txt
```

Rotación: máx 10MB por archivo, 5 backups

## 🔒 Archivos de seguridad

- `config.json` - Credenciales SMTP/IRIS (no commitear)
- `logs/superagent_2.log` - Contiene información sensible (restringir acceso)
- `whitelist.txt` - Lista de remitentes confiables (auditable)

## ✅ Verificación

```bash
# Ver estructura
tree SuperAgent_2/

# Ver configuración
python check_config.py

# Crear archivos de prueba
python test_examples.py

# Ver logs
tail -f logs/superagent_2.log

# Ver emails procesados
ls -la ../processed/sospechoso/
```

## 🆘 Soporte

Si algo falla, ejecuta:

```bash
# 1. Validar configuración
python check_config.py

# 2. Ver logs
cat logs/superagent_2.log

# 3. Crear archivos de prueba
python test_examples.py

# 4. Ejecutar en consola (con debug)
python superagent_2.py
```

Contactar al equipo de seguridad con los logs y la salida de `check_config.py`
