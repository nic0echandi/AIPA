# install_service.ps1
# Instala el agente de phishing como Windows Service usando NSSM
# Requiere: NSSM (Non-Sucking Service Manager) - https://nssm.cc/
# Ejecutar como Administrador

param(
    [string]$AgentDir     = "C:\PhishingAgent",
    [string]$ServiceName  = "PhishingAnalyzerAgent",
    [string]$PythonPath   = "",          # Si está vacío, se autodetecta
    [string]$NssmPath     = "C:\tools\nssm\nssm.exe",
    [switch]$Uninstall    = $false,
    [switch]$Reinstall    = $false
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------

function Write-Step([string]$msg) {
    Write-Host "`n[*] $msg" -ForegroundColor Cyan
}

function Write-OK([string]$msg) {
    Write-Host "  [OK] $msg" -ForegroundColor Green
}

function Write-Warn([string]$msg) {
    Write-Host "  [!] $msg" -ForegroundColor Yellow
}

function Write-Err([string]$msg) {
    Write-Host "  [ERROR] $msg" -ForegroundColor Red
}

function Test-Administrator {
    $identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$identity
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# ---------------------------------------------------------------------------
# Validaciones
# ---------------------------------------------------------------------------

if (-not (Test-Administrator)) {
    Write-Err "Este script debe ejecutarse como Administrador."
    Write-Host "  Clic derecho en PowerShell → 'Ejecutar como administrador'" -ForegroundColor Gray
    exit 1
}

# Detectar Python si no fue especificado
if (-not $PythonPath) {
    $candidates = @(
        (Get-Command python  -ErrorAction SilentlyContinue)?.Source,
        (Get-Command python3 -ErrorAction SilentlyContinue)?.Source,
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }

    if ($candidates.Count -eq 0) {
        Write-Err "Python no encontrado. Instalar Python 3.11+ o especificar -PythonPath"
        exit 1
    }
    $PythonPath = $candidates[0]
}

Write-Step "Configuración"
Write-Host "  Directorio agente : $AgentDir"
Write-Host "  Nombre servicio   : $ServiceName"
Write-Host "  Python            : $PythonPath"
Write-Host "  NSSM              : $NssmPath"

# ---------------------------------------------------------------------------
# Desinstalar
# ---------------------------------------------------------------------------

if ($Uninstall -or $Reinstall) {
    Write-Step "Desinstalando servicio existente..."
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc) {
        if ($svc.Status -eq "Running") {
            Stop-Service -Name $ServiceName -Force
            Write-OK "Servicio detenido"
        }
        & $NssmPath remove $ServiceName confirm 2>&1 | Out-Null
        Write-OK "Servicio '$ServiceName' eliminado"
    } else {
        Write-Warn "El servicio '$ServiceName' no existe, nada que eliminar."
    }

    if ($Uninstall -and -not $Reinstall) {
        Write-Host "`nDesinstalación completada." -ForegroundColor Green
        exit 0
    }
}

# ---------------------------------------------------------------------------
# Verificar NSSM
# ---------------------------------------------------------------------------

Write-Step "Verificando NSSM..."
if (-not (Test-Path $NssmPath)) {
    Write-Warn "NSSM no encontrado en $NssmPath"
    Write-Host "  Descargando NSSM desde https://nssm.cc/ci/nssm-2.24-101-g897c7ad.zip ..."

    $nssmZip = "$env:TEMP\nssm.zip"
    $nssmDir = Split-Path $NssmPath -Parent

    try {
        Invoke-WebRequest -Uri "https://nssm.cc/ci/nssm-2.24-101-g897c7ad.zip" `
                          -OutFile $nssmZip -UseBasicParsing
        Expand-Archive -Path $nssmZip -DestinationPath "$env:TEMP\nssm_extract" -Force

        $arch = if ([Environment]::Is64BitOperatingSystem) { "win64" } else { "win32" }
        $nssmBin = "$env:TEMP\nssm_extract\nssm-2.24-101-g897c7ad\$arch\nssm.exe"

        New-Item -ItemType Directory -Path $nssmDir -Force | Out-Null
        Copy-Item $nssmBin $NssmPath
        Write-OK "NSSM instalado en $NssmPath"
    } catch {
        Write-Err "No se pudo descargar NSSM: $_"
        Write-Host "  Descargarlo manualmente desde https://nssm.cc/download y colocarlo en $NssmPath" -ForegroundColor Gray
        exit 1
    }
} else {
    Write-OK "NSSM encontrado: $NssmPath"
}

# ---------------------------------------------------------------------------
# Crear directorio del agente
# ---------------------------------------------------------------------------

Write-Step "Preparando directorio del agente..."
$subDirs = @("ingress", "processed\legitimo", "processed\spam", "processed\sospechoso",
             "analysis_results", "logs")

New-Item -ItemType Directory -Path $AgentDir -Force | Out-Null
foreach ($sub in $subDirs) {
    New-Item -ItemType Directory -Path "$AgentDir\$sub" -Force | Out-Null
}
Write-OK "Estructura de carpetas creada en $AgentDir"

# ---------------------------------------------------------------------------
# Copiar archivos del agente (desde el directorio actual)
# ---------------------------------------------------------------------------

Write-Step "Copiando archivos del agente..."
$agentFiles = @(
    "agent.py",
    "sharepoint_client.py",
    "knn_classifier.py",
    "phishingAnalizer.py",
    "whitelist.txt"
)

$sourceDir = $PSScriptRoot
foreach ($file in $agentFiles) {
    $src = Join-Path $sourceDir $file
    $dst = Join-Path $AgentDir  $file
    if (Test-Path $src) {
        Copy-Item $src $dst -Force
        Write-OK "Copiado: $file"
    } else {
        Write-Warn "No encontrado (copiar manualmente): $file"
    }
}

# Copiar config si existe
$configSrc = Join-Path $sourceDir "config.json"
$configDst = Join-Path $AgentDir  "config.json"
if (Test-Path $configSrc) {
    Copy-Item $configSrc $configDst -Force
    Write-OK "Copiado: config.json"
} else {
    Write-Warn "config.json no encontrado. El agente creará un template al iniciar."
}

# ---------------------------------------------------------------------------
# Instalar dependencias Python
# ---------------------------------------------------------------------------

Write-Step "Instalando dependencias Python..."
$requirementsPath = "$AgentDir\requirements.txt"

@"
requests>=2.31.0
jsonschema>=4.21.0
"@ | Set-Content $requirementsPath -Encoding UTF8

try {
    & $PythonPath -m pip install -r $requirementsPath --quiet --upgrade
    Write-OK "Dependencias instaladas"
} catch {
    Write-Warn "Error instalando dependencias: $_"
    Write-Host "  Ejecutar manualmente: $PythonPath -m pip install -r $requirementsPath" -ForegroundColor Gray
}

# ---------------------------------------------------------------------------
# Instalar servicio Windows con NSSM
# ---------------------------------------------------------------------------

Write-Step "Instalando Windows Service '$ServiceName'..."

$agentScript = "$AgentDir\agent.py"
$logFile     = "$AgentDir\logs\service_stdout.log"
$errFile     = "$AgentDir\logs\service_stderr.log"

# Instalar
& $NssmPath install $ServiceName $PythonPath $agentScript "--config" "$AgentDir\config.json"

# Configurar directorio de trabajo
& $NssmPath set $ServiceName AppDirectory $AgentDir

# Logs stdout/stderr del proceso
& $NssmPath set $ServiceName AppStdout     $logFile
& $NssmPath set $ServiceName AppStderr     $errFile
& $NssmPath set $ServiceName AppStdoutCreationDisposition 4  # append
& $NssmPath set $ServiceName AppStderrCreationDisposition 4  # append

# Rotación de logs (10MB)
& $NssmPath set $ServiceName AppRotateFiles      1
& $NssmPath set $ServiceName AppRotateBytes      10485760
& $NssmPath set $ServiceName AppRotateOnline     1

# Restart automático si el proceso muere
& $NssmPath set $ServiceName AppExit Default Restart
& $NssmPath set $ServiceName AppRestartDelay 5000  # 5 segundos

# Descripción
& $NssmPath set $ServiceName Description "Agente de análisis de phishing - Movistar Security"
& $NssmPath set $ServiceName DisplayName  "Phishing Analyzer Agent"

Write-OK "Servicio '$ServiceName' instalado"

# ---------------------------------------------------------------------------
# Iniciar servicio
# ---------------------------------------------------------------------------

Write-Step "Iniciando servicio..."
try {
    Start-Service -Name $ServiceName
    Start-Sleep -Seconds 3
    $svc = Get-Service -Name $ServiceName
    if ($svc.Status -eq "Running") {
        Write-OK "Servicio iniciado correctamente (Estado: $($svc.Status))"
    } else {
        Write-Warn "El servicio no está en estado Running (Estado: $($svc.Status))"
        Write-Host "  Revisar logs en: $AgentDir\logs\" -ForegroundColor Gray
    }
} catch {
    Write-Err "Error iniciando el servicio: $_"
}

# ---------------------------------------------------------------------------
# Configurar inicio automático (ya es el default con NSSM)
# ---------------------------------------------------------------------------

Set-Service -Name $ServiceName -StartupType Automatic
Write-OK "Inicio automático configurado (arranca con Windows)"

# ---------------------------------------------------------------------------
# Resumen final
# ---------------------------------------------------------------------------

Write-Host "`n" + ("=" * 60) -ForegroundColor Green
Write-Host "  Instalación completada" -ForegroundColor Green
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host @"

  Servicio  : $ServiceName
  Directorio: $AgentDir
  Python    : $PythonPath

  Comandos útiles:
    Iniciar  : Start-Service $ServiceName
    Detener  : Stop-Service $ServiceName
    Reiniciar: Restart-Service $ServiceName
    Estado   : Get-Service $ServiceName
    Logs     : Get-Content "$AgentDir\logs\agent.log" -Tail 50 -Wait

  PRÓXIMO PASO: Editar $AgentDir\config.json
  con las credenciales de Azure, SharePoint, IRIS y Power Automate.

"@ -ForegroundColor White
