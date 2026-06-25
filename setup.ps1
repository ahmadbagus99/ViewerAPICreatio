[CmdletBinding()]
param(
    [ValidateSet("json", "postgres")]
    [string]$StorageBackend,

    [string]$DatabaseUrl,

    [string]$HostAddress = "127.0.0.1",

    [ValidateRange(1, 65535)]
    [int]$Port = 8090,

    [string]$PublicUrl,

    [string]$AdminUsername,

    [string]$AdminPassword,

    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$RuntimeDirectory = Join-Path $Root ".runtime"
$ConfigPath = Join-Path $RuntimeDirectory "config.json"
$VenvDirectory = Join-Path $Root ".venv"

function Get-VenvPython {
    $windowsPython = Join-Path (Join-Path $VenvDirectory "Scripts") "python.exe"
    if (Test-Path $windowsPython) {
        return $windowsPython
    }

    return Join-Path (Join-Path $VenvDirectory "bin") "python"
}

function Find-Python {
    foreach ($name in @("python", "python3")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }
    throw "Python tidak ditemukan. Install Python 3.10+ lalu jalankan setup.ps1 lagi."
}

if (-not $StorageBackend) {
    Write-Host ""
    Write-Host "Pilih storage Viewer:"
    Write-Host "  1. JSON files (tanpa database)"
    Write-Host "  2. PostgreSQL"
    $choice = Read-Host "Pilihan [1]"

    if ([string]::IsNullOrWhiteSpace($choice) -or $choice -eq "1") {
        $StorageBackend = "json"
    }
    elseif ($choice -eq "2") {
        $StorageBackend = "postgres"
    }
    else {
        throw "Pilihan storage tidak valid."
    }
}

if ($StorageBackend -eq "postgres" -and [string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    $DatabaseUrl = Read-Host "PostgreSQL URL"
}
if ($StorageBackend -eq "postgres" -and [string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    throw "DatabaseUrl wajib diisi untuk backend PostgreSQL."
}
if ([string]::IsNullOrWhiteSpace($PublicUrl)) {
    $PublicUrl = "http://${HostAddress}:$Port"
}

if (-not $PSBoundParameters.ContainsKey("AdminUsername")) {
    $inputUsername = Read-Host "Viewer login username [admin]"
    $AdminUsername = if ([string]::IsNullOrWhiteSpace($inputUsername)) {
        "admin"
    }
    else {
        $inputUsername.Trim()
    }
}

if (-not $PSBoundParameters.ContainsKey("AdminPassword")) {
    $securePassword = Read-Host "Viewer login password [admin123]" -AsSecureString
    $inputPassword = [System.Net.NetworkCredential]::new("", $securePassword).Password
    $AdminPassword = if ([string]::IsNullOrWhiteSpace($inputPassword)) {
        "admin123"
    }
    else {
        $inputPassword
    }
}

if ([string]::IsNullOrWhiteSpace($AdminUsername)) {
    throw "AdminUsername tidak boleh kosong."
}
if ([string]::IsNullOrWhiteSpace($AdminPassword)) {
    throw "AdminPassword tidak boleh kosong."
}

New-Item -ItemType Directory -Path $RuntimeDirectory -Force | Out-Null
[ordered]@{
    storageBackend = $StorageBackend
    databaseUrl = if ($StorageBackend -eq "postgres") { $DatabaseUrl } else { $null }
    host = $HostAddress
    port = $Port
    publicUrl = $PublicUrl.TrimEnd("/")
    adminUsername = $AdminUsername
    adminPassword = $AdminPassword
} | ConvertTo-Json | Set-Content -Path $ConfigPath -Encoding UTF8

if ($StorageBackend -eq "postgres" -and -not $SkipInstall) {
    $Python = Find-Python
    $VenvPython = Get-VenvPython
    if (-not (Test-Path $VenvPython)) {
        Write-Host "Membuat virtual environment Viewer..."
        & $Python -m venv $VenvDirectory
        if ($LASTEXITCODE -ne 0) { throw "Gagal membuat virtual environment." }
        $VenvPython = Get-VenvPython
    }

    Write-Host "Meng-install dependency Viewer..."
    & $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Gagal meng-install dependency." }
}

Write-Host ""
Write-Host "Setup Viewer selesai."
Write-Host "Storage : $StorageBackend"
Write-Host "URL     : $PublicUrl"
Write-Host "Login   : $AdminUsername"
Write-Host "Jalankan: .\start.ps1"
