# SuperAgent

SuperAgent es una versión del agente que no requiere conexión a SharePoint. Power Automate descarga los archivos TXT a la carpeta `ingress/` y el agente los procesa automáticamente.

## Características
- Observa la carpeta `ingress/` para nuevos archivos TXT
- Clasifica los archivos (phishing/spam)
- Registra el caso en IRIS
- Envía notificación por correo al remitente (header `To:`)
- Configuración SMTP y de IRIS en `config.json`
- Logging de todas las acciones

## Configuración
Edita `config.json` con los datos de tu servidor SMTP y de IRIS.

## Ejecución

```bash
python superagent.py
```

