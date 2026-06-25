$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

$requiredVariables = @(
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "VIEWER_ADMIN_USERNAME",
    "VIEWER_ADMIN_PASSWORD",
    "VIEWER_SESSION_SECRET"
)

foreach ($name in $requiredVariables) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Environment variable $name wajib diisi."
    }
}

$databaseUser = [Uri]::EscapeDataString($env:POSTGRES_USER)
$databasePassword = [Uri]::EscapeDataString($env:POSTGRES_PASSWORD)
$databaseName = [Uri]::EscapeDataString($env:POSTGRES_DB)
$databaseUrl = "postgresql://${databaseUser}:${databasePassword}@database:5432/$databaseName"

$port = if ($env:PORT) { [int]$env:PORT } else { 8090 }
$publicUrl = if ($env:VIEWER_PUBLIC_URL) {
    $env:VIEWER_PUBLIC_URL
}
else {
    "http://localhost:$port"
}

Write-Host "Menyiapkan Viewer..."
& (Join-Path $Root "setup.ps1") `
    -StorageBackend postgres `
    -DatabaseUrl $databaseUrl `
    -HostAddress "0.0.0.0" `
    -Port $port `
    -PublicUrl $publicUrl `
    -AdminUsername $env:VIEWER_ADMIN_USERNAME `
    -AdminPassword $env:VIEWER_ADMIN_PASSWORD `
    -SkipInstall

Write-Host "Menjalankan Viewer..."
& (Join-Path $Root "start.ps1")
exit $LASTEXITCODE
