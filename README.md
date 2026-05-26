# AIPA - Agente de Detección de Phishing y Spam

## Descripción
AIPA es un agente automatizado diseñado para analizar archivos sospechosos de phishing y spam. El agente procesa archivos de texto, los clasifica y los mueve a carpetas correspondientes según el resultado del análisis. Utiliza técnicas de machine learning y listas blancas para mejorar la precisión de la detección.

## Estructura del Proyecto
- `agent/`: Contiene el código principal del agente y módulos auxiliares.
  - `agent.py`: Script principal para ejecutar el agente.
  - `phishing_analyzer_txt_08.py`: Analizador de phishing basado en texto.
  - `knn_classifier.py`: Clasificador KNN para detección.
  - `sharepoint_client.py`: Cliente para integración con SharePoint.
  - `whitelist.txt`: Lista blanca de remitentes o dominios confiables.
  - `config.json`: Configuración del agente.
  - `install_service.ps1`: Script para instalar el agente como servicio en Windows.
- `ingress/`: Carpeta de entrada de archivos sospechosos.
- `suspect/`: Archivos identificados como sospechosos.
- `processed/`: Archivos ya procesados, clasificados en `phishing/` y `spam/`.
- `proceso/`: Carpeta auxiliar para procesamiento temporal.
- `testing/`: Pruebas y scripts de desarrollo.

## Instalación y Ejecución

### 1. Requisitos
- Python 3.8 o superior
- Paquetes: `scikit-learn`, `pandas`, `requests`, etc. (ver requerimientos en el código)

### 2. Instalación de dependencias
Instala los paquetes necesarios ejecutando:

```bash
pip install -r requirements.txt
```

Si no existe `requirements.txt`, instala manualmente:

```bash
pip install scikit-learn pandas requests
```

### 3. Configuración
Edita el archivo `agent/config.json` para ajustar rutas, parámetros y credenciales según tu entorno.

### 4. Ejecución manual
Desde la raíz del proyecto, ejecuta:

```bash
python agent/agent.py
```

### 5. Instalación como servicio (Windows)
Ejecuta el script PowerShell con permisos de administrador:

```powershell
powershell -ExecutionPolicy Bypass -File agent/install_service.ps1
```

## ¿Cómo funciona el agente?
1. **Ingreso de archivos:** Los archivos sospechosos se colocan en la carpeta `ingress/`.
2. **Procesamiento:** El agente lee los archivos, los analiza usando modelos de machine learning y reglas basadas en listas blancas.
3. **Clasificación:** Según el resultado, mueve los archivos a `processed/phishing/`, `processed/spam/` o los deja en `suspect/` si no puede clasificarlos.
4. **Integración:** Puede subir resultados a SharePoint si está configurado.
5. **Registro:** El agente mantiene logs de actividad y errores.

## Personalización
- Modifica `whitelist.txt` para agregar o quitar remitentes confiables.
- Ajusta los parámetros del modelo en los scripts de la carpeta `agent/`.

## Soporte
Para dudas o problemas, contacta al desarrollador principal o revisa los comentarios en el código fuente.