# Reportes de reportantes por campaña

Para generar un CSV con los reportantes de un dominio en un período, ejecuta desde la carpeta `SuperAgent`:

```bash
python generar_reporte_reportantes.py
```

El programa solicita las fechas de inicio y fin en formato `YYYY-MM-DD`. Ambas fechas se incluyen en la búsqueda. Por defecto busca remitentes del dominio `movistarbeneficios.support-email.info` en `logs/superagent.log` y sus archivos rotados (`superagent.log.1`, etc.).

El CSV se guarda en la carpeta `SuperAgent` con el nombre `reportantes_<dominio>_<inicio>_<fin>.csv`. Incluye las columnas `email`, `reportes` y `fecha_reporte` (formato `YYYY-MM-DD`). Cada fila agrupa los reportes de una misma dirección en una misma fecha; si alguien reportó en días distintos, aparece en varias filas.

Para generar un informe de otro dominio o indicar directorios distintos:

```bash
python generar_reporte_reportantes.py --domain ejemplo.com --log-dir logs --output-dir reportes
```

Los reportes se basan en los bloques `Procesando`, el remitente extraído (`EXTRACT From`) y el campo `Para (reporter)` presentes en los logs.
