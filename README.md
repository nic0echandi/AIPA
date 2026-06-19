# AIPA - Agente de Detección de Phishing y Spam

## Descripción
AIPA es un agente automatizado diseñado para analizar archivos sospechosos de phishing y spam. El agente procesa archivos de texto, los clasifica y los mueve a carpetas correspondientes según el resultado del análisis. Utiliza técnicas de machine learning (KNN con sklearn), aprendizaje activo y listas blancas para mejorar la precisión de la detección.

## Novedad: KNN con sklearn y Aprendizaje Activo

**v2.0 (Junio 2026)**: Migración a scikit-learn con optimizaciones:
- ✅ Modelo KNN optimizado con KDTree
- ✅ Aprendizaje activo: mejora con cada email clasificado
- ✅ Umbral de confianza dinámico (ajusta automáticamente según datos)
- ✅ Reduce progresivamente la dependencia del LLM
- ✅ Estadísticas y feedback tracking

[Ver detalles técnicos](SuperAgent_2/CAMBIOS_KNN.md)

## Estructura del Proyecto
- `agent/`: Contiene el código principal del agente y módulos auxiliares.
  - `agent.py`: Script principal para ejecutar el agente.
  - `phishingAnalizer.py`: Analizador de phishing basado en texto.
  - `knn_classifier.py`: Clasificador KNN con sklearn + aprendizaje activo.
  - `sharepoint_client.py`: Cliente para integración con SharePoint.
  - `whitelist.txt`: Lista blanca de remitentes o dominios confiables.
  - `config.json`: Configuración del agente.
  - `install_service.ps1`: Script para instalar el agente como servicio en Windows.
- `SuperAgent_2/`: Agente mejorado sin dependencia de SharePoint
  - `superagent_2.py`: Versión optimizada con FileSystemWatcher
  - `demo_knn.py`: Demo del modelo KNN y aprendizaje activo
  - `CAMBIOS_KNN.md`: Documentación técnica de los cambios
- `ingress/`: Carpeta de entrada de archivos sospechosos.
- `suspect/`: Archivos identificados como sospechosos.
- `processed/`: Archivos ya procesados, clasificados en `phishing/` y `spam/`.
- `proceso/`: Carpeta auxiliar para procesamiento temporal.
- `testing/`: Pruebas y scripts de desarrollo.

## Instalación y Ejecución

### 1. Requisitos
- Python 3.9 o superior
- Paquetes: `scikit-learn`, `joblib`, `pandas`, `requests`, etc. (ver requirements.txt)

### 2. Instalación de dependencias
Instala los paquetes necesarios ejecutando:

```bash
pip install -r SuperAgent_2/requirements.txt
```

### 3. Configuración
Edita el archivo `SuperAgent_2/config.json` para ajustar rutas, parámetros y credenciales según tu entorno.

### 4. Ejecución manual (SuperAgent_2 - RECOMENDADO)
Desde la raíz del proyecto, ejecuta:

```bash
python SuperAgent_2/superagent_2.py
```

### 5. Demo del modelo KNN
Prueba el modelo KNN y su aprendizaje activo:

```bash
python SuperAgent_2/demo_knn.py
```
Ejecuta el script PowerShell con permisos de administrador:

```powershell
powershell -ExecutionPolicy Bypass -File agent/install_service.ps1
```


## ¿Cómo funciona el agente?

El agente sigue un flujo automatizado y supervisado para la detección y gestión de correos sospechosos:

1. **Conexión y monitoreo de SharePoint:**
  - El agente se conecta periódicamente a una carpeta de SharePoint (configurada en `config.json`) usando Microsoft Graph API.
  - Descarga automáticamente todos los archivos `.txt` nuevos a la carpeta local `ingress/`.
  - Además, un FileSystemWatcher monitorea en tiempo real la carpeta `ingress/` para detectar archivos copiados manualmente o por otros procesos.

2. **Detección de nuevos archivos:**
  - Cada archivo nuevo detectado en `ingress/` se encola para su análisis.

3. **Análisis y clasificación:**
  - El agente extrae los encabezados y contenido del archivo.
  - Si el remitente está en la lista blanca (`whitelist.txt`), el archivo se clasifica automáticamente como legítimo.
  - Si no está en la lista blanca, se aplica un modelo KNN para una clasificación rápida:
    - Si la confianza del KNN es alta, se clasifica directamente (legítimo, spam o sospechoso).
    - Si la confianza es baja, se realiza un análisis profundo usando un modelo LLM (por ejemplo, Ollama o Anthropic).

4. **Acciones según clasificación:**
  - **Legítimo:**
    - El archivo se mueve a `processed/legitimo/`.
    - Se notifica al denunciante (reporter) mediante un webhook de Power Automate.
    - Se puede enviar un webhook adicional para registro o auditoría.
  - **Spam:**
    - El archivo se mueve a `processed/spam/`.
    - Se notifica al denunciante indicando que el correo es spam y no representa riesgo.
    - Se actualiza el modelo KNN con este ejemplo para aprendizaje activo.

  - **Sospechoso (phishing):**
    - El archivo se mueve a `processed/sospechoso/`.
    - **Conexión y generación de caso en IRIS DFIR:**
      - Si el análisis determina que el correo es phishing/sospechoso, el agente se conecta automáticamente a la plataforma IRIS DFIR (Digital Forensics and Incident Response) usando la API configurada en `config.json`.
      - Se envía toda la información relevante del análisis (encabezados, remitente, score de riesgo, URLs, razones, etc.) y se crea un caso de incidente en IRIS.
      - El ID del caso generado se registra en el informe y en los logs, permitiendo su trazabilidad y seguimiento por el equipo de respuesta a incidentes.
      - Esta integración permite que el equipo de seguridad reciba alertas inmediatas y pueda iniciar la investigación forense de manera automatizada y documentada.
    - Se notifica al denunciante con advertencias de seguridad.
    - Se actualiza el modelo KNN con este ejemplo.

5. **Emisión de informes y notificaciones:**
  - Para cada archivo analizado, se genera un informe JSON con todos los detalles del análisis (clasificación, score de riesgo, razones, indicadores, URLs, etc.).
  - El informe se guarda en la carpeta configurada (`analysis_dir`).
  - Las notificaciones al denunciante se realizan mediante Power Automate, que envía un correo personalizado según el resultado.

6. **Registro y logs:**
  - Todas las acciones, errores y resultados se registran en archivos de log rotativos en la carpeta `logs/`.
  - Los logs permiten auditar el funcionamiento y diagnosticar problemas.

7. **Análisis de resultados:**
  - Los archivos procesados quedan organizados en subcarpetas de `processed/` según su clasificación (`legitimo/`, `spam/`, `sospechoso/`).
  - Los informes JSON pueden consultarse para revisar el detalle de cada caso.
  - El archivo de log principal (`logs/agent.log`) muestra el historial de actividad, errores y notificaciones.
  - El modelo KNN se va ajustando automáticamente con los ejemplos confirmados, mejorando la precisión con el tiempo.


### Ejemplo de informe generado (caso phishing con integración IRIS)

```json
{
  "mensaje_id": "<1234.5678@correo.com>",
  "classification": "sospechoso",
  "confidence": 0.97,
  "reporter_email": "usuario@empresa.com",
  "original_subject": "Alerta de seguridad bancaria",
  "original_from": "Banco Falso <alerta@bancofalso.com>",
  "reply_to": "soporte@bancofalso.com",
  "sender_ip": "203.0.113.45",
  "ip_reputation": {"abuse_score": 85, "country": "RU"},
  "analysis_date": "2026-05-26T14:32:10",
  "indicators": {"spf": "fail", "dkim": "none", "dmarc": "fail"},
  "headers_raw": "...headers SMTP...",
  "body_preview": "Estimado cliente, su cuenta ha sido bloqueada...",
  "urls_found": [
    "http://bancofalso.com/seguridad",
    "http://malicioso.ru/phish"
  ],
  "microsoft_url_check": "http://malicioso.ru/phish",
  "risk_score": 92,
  "reasons": [
    "Dominio remitente no está en whitelist",
    "SPF fail, DKIM none, DMARC fail",
    "URL sospechosa detectada",
    "KNN: sospechoso (97%)"
  ],
  "iris_case_id": 4567
}
```

En este ejemplo, el agente clasificó el correo como sospechoso (phishing), generó un caso en IRIS (ID 4567) y notificó al denunciante. El informe JSON contiene todos los detalles relevantes para auditoría y respuesta a incidentes.

## Personalización
- Modifica `whitelist.txt` para agregar o quitar remitentes confiables.
- Ajusta los parámetros del modelo en los scripts de la carpeta `agent/`.

## Soporte
Para dudas o problemas, contacta al desarrollador principal o revisa los comentarios en el código fuente.