# SuperAgent_2

Agente de análisis de phishing sin dependencia de SharePoint. Monitorea la carpeta `ingress/` donde se descargan automáticamente los archivos TXT con reportes de email.

## Características

- **FileSystemWatcher**: Monitorea carpeta `ingress/` para nuevos archivos .txt
- **Clasificación inteligente**: 
  - KNN rápido con features de headers (SPF, DKIM, DMARC, URLs)
  - Análisis profundo con Ollama/LLM si confianza < umbral
- **Tres categorías**: Legítimo, Spam, Sospechoso
- **Acciones post-análisis**:
  - **Sospechoso**: Registra caso en IRIS DFIR + notifica reporter
  - **Spam**: Notifica reporter
  - **Legítimo**: Notifica reporter
- **Notificación por SMTP**: Envía email al destinatario del reporte (header "To:")
- **Logging estructurado**: Registra todas las acciones en archivo rotativo
- **Aprendizaje activo**: Actualiza modelo KNN con nuevos ejemplos

## Configuración

Editar `config.json`:

```json
{
  "smtp": {
    "host": "smtp.gmail.com",
    "port": 587,
    "username": "your_email@gmail.com",
    "password": "your_app_password",
    "use_tls": true,
    "from": "security-alerts@example.com"
  },
  "iris_dfir": {
    "url": "https://iris.example.com/api/cases",
    "api_key": "your_iris_api_key",
    "verify_ssl": true
  }
}
```

## Estructura de carpetas

```
AIPA/
├── ingress/              # Power Automate descarga archivos aquí
├── processed/
│   ├── legitimo/
│   ├── spam/
│   └── sospechoso/
├── analysis_results/     # Resultados en JSON
├── agent/                # Módulos compartidos (phishingAnalizer, knn_classifier)
└── SuperAgent_2/         # Este agente
    ├── superagent_2.py   # Script principal
    ├── config.json       # Configuración
    ├── requirements.txt
    ├── logs/             # Archivo de log (creado automáticamente)
    └── README.md
```

## Ejecución

### Instalación de dependencias

```bash
cd SuperAgent_2
pip install -r requirements.txt
```

### Ejecutar agente

```bash
python superagent_2.py
```

El agente correrá indefinidamente, monitoreando `ingress/` para nuevos archivos.

### Como servicio (Windows)

Crear script PowerShell para instalar como Windows Service:

```powershell
# install_service.ps1
$pythonPath = "C:\Python311\python.exe"
$scriptPath = "C:\path\to\SuperAgent_2\superagent_2.py"

nssm install SuperAgent_2 $pythonPath $scriptPath
nssm start SuperAgent_2
```

## Flujo de procesamiento

```
ingress/ (archivo nuevo)
    ↓
[FileWatcher detecta]
    ↓
[Parsea headers: From, To, Subject, Message-ID]
    ↓
[Whitelist check] → Si es whitelist: legítimo ✓
    ↓ No
[KNN rápido] → Si confianza > umbral: usar resultado ✓
    ↓ No (confianza baja)
[Análisis profundo Ollama] → clasificación final
    ↓
[Acciones según clasificación]
├─ Sospechoso → Crear caso en IRIS + email al reporter
├─ Spam → Email al reporter
└─ Legítimo → Email al reporter
    ↓
[Mover a processed/<clasificación>/]
    ↓
[Actualizar modelo KNN (aprendizaje activo)]
    ↓
[Log de todas las acciones]
```

## Logging

Archivo: `SuperAgent_2/logs/superagent_2.log`

Niveles: INFO (predeterminado), DEBUG, WARNING, ERROR

Rotación automática: máx 10MB por archivo, 5 backups

## Dependencias

- Python 3.9+
- phishingAnalizer (en carpeta agent/)
- knn_classifier (en carpeta agent/)
- requests (para IRIS)
- Ollama (opcional, para análisis profundo)

## Troubleshooting

### No encuentra módulos de agent/

Asegúrate de que la estructura sea:
```
AIPA/
├── agent/
│   ├── phishingAnalizer.py
│   ├── knn_classifier.py
│   └── ...
├── SuperAgent_2/
│   └── superagent_2.py
```

### SMTP falla

- Verificar credenciales en `config.json`
- Para Gmail: usar contraseña de aplicación (no la contraseña normal)
- Puerto: 587 (TLS) o 465 (SSL)

### IRIS no registra

- Verificar endpoint y API key en `config.json`
- Revisar logs para detalles del error
- SSL/TLS puede requerir `verify_ssl: false` en desarrollo

## Contacto

Para reportes o sugerencias, contactar al equipo de seguridad.
