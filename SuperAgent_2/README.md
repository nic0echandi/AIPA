# SuperAgent_2

Agente de análisis de phishing sin dependencia de SharePoint. Monitorea la carpeta `ingress/` donde se descargan automáticamente los archivos TXT con reportes de email.

## Características

- **FileSystemWatcher**: Monitorea carpeta `ingress/` para nuevos archivos .txt
- **Clasificación inteligente con KNN (sklearn)**:
  - KNN rápido con features de headers (SPF, DKIM, DMARC, URLs, etc.)
  - Optimizado con KDTree para mejor rendimiento
  - Análisis profundo con Ollama/LLM si confianza < umbral
- **Aprendizaje Activo**: Modelo mejora automáticamente con cada email clasificado
  - Registra feedback: identifica si KNN se equivocó
  - Ajusta dinámicamente el umbral de confianza
  - Reduce progresivamente la dependencia del LLM
- **Tres categorías**: Legítimo, Spam, Sospechoso
- **Acciones post-análisis**:
  - **Sospechoso**: Registra caso en IRIS DFIR + notifica reporter
  - **Spam**: Notifica reporter
  - **Legítimo**: Notifica reporter
- **Notificación por SMTP**: Envía email al destinatario del reporte (header "To:")
- **Logging estructurado**: Registra todas las acciones en archivo rotativo
- **Estadísticas del modelo**: Monitorea precisión y crecimiento del modelo

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

## Modelo KNN y Aprendizaje Activo

### Cómo funciona

El modelo KNN usa **scikit-learn** con optimizaciones (KDTree) y aprende progresivamente:

1. **Inicio**: Comienza con 16 ejemplos base (embebidos)
2. **Cada email**: Se agrega como ejemplo de entrenamiento
3. **Feedback**: Registra si el modelo se equivocó
4. **Umbral dinámico**: Se ajusta automáticamente según cantidad de ejemplos

### Umbral de Confianza (dinámico)

| Ejemplos | Threshold | Comportamiento |
|----------|-----------|-----------------|
| < 50 | 95% | Muy exigente → usa mucho Ollama |
| 50-200 | 85% | Estándar → balance KNN/Ollama |
| 200-500 | 75% | Confía en KNN → menos Ollama |
| > 500 | 65% | Experto → depende poco de Ollama |

**Beneficio**: Conforme el modelo aprende, **reduce automáticamente** la dependencia del LLM.

### Monitorear el modelo

Archivos generados automáticamente:

- `knn_model.joblib` - modelo persistido (matriz de datos + modelo sklearn)
- `knn_stats.json` - estadísticas y histórico

**Ejemplo de `knn_stats.json`:**
```json
{
  "total_examples": 156,
  "by_label": {
    "legitimo": 50,
    "spam": 60,
    "sospechoso": 46
  },
  "training_count": 95,
  "current_threshold": 0.75,
  "base_threshold": 0.85,
  "last_retrain": "2026-06-19T14:23:15...",
  "threshold_adjustments": [
    {
      "date": "2026-06-19T14:15:00...",
      "from": 0.85,
      "to": 0.75,
      "training_size": 200
    }
  ],
  "feedback_history": [...]
}
```

### Demo y testing

Ver script `demo_knn.py`:

```bash
python SuperAgent_2/demo_knn.py
```

Este script demuestra:
- Inicialización del modelo
- Agregación de ejemplos
- Ajuste dinámico de threshold
- Registro de feedback
- Clasificación de nuevo email

## Dependencias

- Python 3.9+
- scikit-learn (>=1.0.0) - modelo KNN optimizado
- joblib (>=1.1.0) - persistencia de modelos
- phishingAnalizer (en carpeta agent/)
- knn_classifier (en carpeta agent/)
- requests (para IRIS)
- Ollama (opcional, para análisis profundo cuando KNN tiene baja confianza)

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

### Error: "ImportError: No module named 'sklearn'"

Instalar dependencias nuevas:
```bash
pip install scikit-learn>=1.0.0 joblib>=1.1.0
```

### KNN siempre necesita Ollama (umbral muy alto)

Normale con pocos ejemplos de entrenamiento. Conforme agregues más emails:
- Monitorea `knn_stats.json`
- Verifica que `current_threshold` vaya bajando
- A los ~200 ejemplos debería usar más directamente KNN

### El modelo no mejora (siempre baja confianza)

Posibles causas:
1. **Features insuficientes**: Los headers no tienen información clara (SPF/DKIM/DMARC)
2. **Clases desbalanceadas**: Muchos ejemplos de una clase, pocos de otras
3. **Ruido en datos**: Emails mal clasificados al principio

Solución:
- Revisar `knn_stats.json` para ver distribución de clases
- Registrar feedback manual cuando veas errores
- Aumentar cantidad de ejemplos base

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
