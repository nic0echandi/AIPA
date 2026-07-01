# Install SuperAgent_2 as Windows Service
# Requires: nssm (Non-Sucking Service Manager) - https://nssm.cc/download

# Paso 1: Descargar nssm desde https://nssm.cc/download y agregar a PATH

# Paso 2: Abrir PowerShell como Administrator y ejecutar:

$pythonPath = "C:\Python311\python.exe"  # Reemplazar con ruta correcta
$scriptPath = "$PSScriptRoot\superagent_2.py"
$workDir = "$PSScriptRoot"
$serviceName = "SuperAgent_2"

# Instalar servicio
nssm install $serviceName $pythonPath $scriptPath
nssm set $serviceName AppDirectory $workDir
nssm set $serviceName AppRotateFiles 1
nssm set $serviceName AppRotateOnlineFiles 1
nssm set $serviceName AppRotateSize 10485760

# Iniciar servicio
nssm start $serviceName

Write-Host "Servicio $serviceName instalado e iniciado"
Write-Host "Para detener:   nssm stop $serviceName"
Write-Host "Para desinstalar: nssm remove $serviceName confirm"
