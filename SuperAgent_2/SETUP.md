# SuperAgent_2 - Guía de Instalación y Configuración

## 📋 Requisitos

- Python 3.9 o superior
- Acceso a servidor SMTP (Gmail, Office 365, etc.)
- Acceso a IRIS DFIR (opcional pero recomendado)
- Acceso a Ollama (para análisis profundo, opcional)

## 🚀 Instalación Rápida

### 1. Verificar estructura de carpetas

```
AIPA/
├── agent/
│   ├── phishingAnalizer.py   ← Módulo de análisis
│   ├── knn_classifier.py     ← Clasificador KNN
│   └── config.json
├── ingress/                   ← Archivos .txt se depositan aquí
├── processed/
│   ├── legitimo/
│   ├── spam/
│   └── sospechoso/
├── analysis_results/          ← JSON con análisis
└── SuperAgent_2/              ← Este agente
```

### 2. Instalar dependencias

```bash
cd SuperAgent_2
pip install -r requirements.txt
```

### 3. Verificar configuración

```bash
python check_config.py
```

### 4. Configurar `config.json`

#### SMTP (Correo)

**Para Gmail:**
```json
{
  "smtp": {
    "host": "smtp.gmail.com",
    "port": 587,
    "username": "tu_email@gmail.com",
    "password": "tu_contraseña_aplicación",  // Generar en myaccount.google.com/apppasswords
    "use_tls": true,
    "from": "security-alerts@example.com"
  }
}
```

**Para Office 365:**
```json
{
  "smtp": {
    "host": "smtp.office365.com",
    "port": 587,
    "username": "tu_email@company.com",
    "password": "tu_contraseña",
    "use_tls": true,
    "from": "security-alerts@company.com"
  }
}
```

#### IRIS DFIR (Registro de alertas en IRIS 2.5.0)

```json
{
  "iris_dfir": {
    "url": "https://iris.company.com/alerts/add",
    "api_key": "tu_api_key_aqui",
    "verify_ssl": true,
    "iris_version": "2.5.0",
    "default_customer_id": 1,
    "default_severity": "high"
  }
}
```

Si no tienes IRIS, déjalo en blanco y funciona igual.

#### LLM (Análisis profundo)

```json
{
  "llm_provider": "ollama",
  "ollama_url": "http://localhost:11434/api/generate",
  "ollama_model": "llama3.2"
}
```

O usa Anthropic:
```json
{
  "llm_provider": "anthropic",
  "anthropic_api_key": "sk-..."
}
```

## ▶️ Ejecución

### Modo interactivo (pruebas)

```bash
python superagent_2.py
```

Verás logs en la consola y en `logs/superagent_2.log`

### Crear archivos de prueba

```bash
python test_examples.py
```

Crea 3 emails de ejemplo en `ingress/`:
- `phishing_example_001.txt` - Email sospechoso
- `spam_example_001.txt` - Email spam
- `legitimate_example_001.txt` - Email legítimo

### Como Windows Service (ejecución permanente)

#### Opción 1: Con nssm

1. Descargar [nssm](https://nssm.cc/download)
2. Extraer a una carpeta y agregar a PATH
3. Ejecutar como Administrator:

```powershell
cd SuperAgent_2
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
.\install_service.ps1
```

Ver estado:
```powershell
nssm status SuperAgent_2
```

Detener:
```powershell
nssm stop SuperAgent_2
```

Desinstalar:
```powershell
nssm remove SuperAgent_2 confirm
```

#### Opción 2: Con Task Scheduler

1. Abrir Task Scheduler (Programador de tareas)
2. Crear tarea básica:
   - Nombre: SuperAgent_2
   - Trigger: Al iniciar
   - Acción: Ejecutar programa
   - Programa: `C:\Python311\python.exe`
   - Argumentos: `C:\ruta\a\SuperAgent_2\superagent_2.py`
   - Carpeta de inicio: `C:\ruta\a\SuperAgent_2\`

## 📊 Monitoreo

### Ver logs en tiempo real

```bash
# Windows PowerShell
Get-Content logs/superagent_2.log -Wait -Tail 50

# Linux/Mac
tail -f logs/superagent_2.log
```

### Archivos procesados

Los emails se mueven automáticamente a:
- `processed/sospechoso/` - Alertas de seguridad → registradas en IRIS 2.5.0
- `processed/spam/` - Emails no deseados
- `processed/legitimo/` - Emails auténticos

### Análisis JSON

Cada email procesado genera un JSON en:
```
analysis_results/2026-05-28_14-30-45_mensaje_id.json
```

Contiene:
- Clasificación y score de riesgo
- Indicadores de seguridad (SPF, DKIM, DMARC)
- URLs detectadas
- Features de KNN utilizadas
- Razones de clasificación

## 🔧 Solución de Problemas

### El agente no inicia

1. Verificar Python:
   ```bash
   python --version
   ```

2. Verificar config:
   ```bash
   python check_config.py
   ```

### No envía emails

- Verificar credenciales SMTP en `config.json`
- Para Gmail: usar contraseña de aplicación (no contraseña normal)
- Ver logs: `logs/superagent_2.log`

### IRIS no registra alertas

- Verificar endpoint y API key
- Revisar logs para detalles del error
- Verificar que la versión sea IRIS 2.5.0
- Si hay problemas SSL: `"verify_ssl": false`

### El proceso se bloquea

- Revisar si hay archivo corrupto en `ingress/`
- Ver logs para identificar dónde se bloquea
- Mover archivo a otra carpeta para aislarlo

### Logs vacíos

- Crear carpeta manualmente: `mkdir logs`
- Verificar permisos de escritura en `logs/`

## 🔐 Seguridad

- **No commits SMTP credentials**: Usar variables de entorno en producción
- **API Keys seguras**: Usar gestores de secretos (Azure Key Vault, HashiCorp Vault)
- **HTTPS obligatorio** para IRIS en producción
- **Logs en carpeta privada**: Restringir acceso a `logs/`

## ✅ Checklist de Implementación

- [ ] Estructura de carpetas completa (ingress, processed, analysis_results)
- [ ] config.json configurado con SMTP
- [ ] IRIS DFIR configurado (opcional)
- [ ] Dependencias instaladas: `pip install -r requirements.txt`
- [ ] Validación: `python check_config.py`
- [ ] Test: `python test_examples.py` + `python superagent_2.py`
- [ ] Servicio instalado y corriendo (nssm o Task Scheduler)
- [ ] Logs habilitados y monitoreados
- [ ] Archivos .txt depositándose en `ingress/` automáticamente

## 🆘 Contacto y Soporte

Para reportes o preguntas:
- Revisar logs en `logs/superagent_2.log`
- Ejecutar `python check_config.py` para verificación
- Contactar al equipo de seguridad
