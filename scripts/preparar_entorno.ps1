# =====================================================================
# ExtinPro · SPVCI — Prepara el entorno de desarrollo en Windows.
# Ejecutar desde la carpeta del proyecto (después de crear la base con crear_bd.sql):
#
#   powershell -ExecutionPolicy Bypass -File scripts\preparar_entorno.ps1
#
# Hace: entorno virtual .venv → instala dependencias → crea .env (si no existe)
#       → aplica las migraciones (tablas, restricciones y vistas del Entregable 6).
# =====================================================================
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creando el entorno virtual .venv ..." -ForegroundColor Cyan
    py -3 -m venv .venv
}
$py = ".\.venv\Scripts\python.exe"

Write-Host "Instalando dependencias ..." -ForegroundColor Cyan
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r requirements.txt --quiet

if (-not (Test-Path ".env")) {
    Write-Host "Creando el archivo .env ..." -ForegroundColor Cyan
    $segura = Read-Host "Contraseña que le diste al usuario 'extinpro' de PostgreSQL" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura)
    $clave = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    $secret = & $py -c "import secrets; print(secrets.token_urlsafe(50))"
    $lineas = foreach ($l in Get-Content ".env.example" -Encoding UTF8) {
        if ($l.StartsWith("SECRET_KEY=")) { "SECRET_KEY=" + $secret }
        elseif ($l.StartsWith("DATABASE_URL=")) { $l.Replace("CAMBIA_ESTA_CONTRASENA", [uri]::EscapeDataString($clave)) }
        else { $l }
    }
    # UTF-8 sin BOM
    [IO.File]::WriteAllLines((Join-Path (Get-Location) ".env"), [string[]]$lineas, (New-Object Text.UTF8Encoding $false))
}

Write-Host "Aplicando migraciones ..." -ForegroundColor Cyan
& $py manage.py migrate
if ($LASTEXITCODE -ne 0) {
    Write-Host "No se pudo conectar o migrar. Revisa que PostgreSQL esté encendido y la contraseña en .env." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Listo. Siguientes pasos:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\python.exe manage.py cargar_demo     (datos de ejemplo del Entregable 7)"
Write-Host "     o .\.venv\Scripts\python.exe manage.py inicializar  (base vacía: sucursal, caja y administrador)"
Write-Host "  .\.venv\Scripts\python.exe manage.py runserver       y abre http://127.0.0.1:8000/"
