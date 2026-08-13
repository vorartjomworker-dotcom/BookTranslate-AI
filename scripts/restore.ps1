param([Parameter(Mandatory=$true)][string]$BackupDirectory)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Backup = (Resolve-Path $BackupDirectory).Path
Set-Location $Root

foreach ($Required in @("postgres.dump", "redis.rdb", "uploads")) {
  if (-not (Test-Path (Join-Path $Backup $Required))) { throw "Missing backup component: $Required" }
}

$PostgresUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "booktranslate" }
$PostgresDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "booktranslate" }

docker compose stop frontend backend worker vision-worker | Out-Null
Write-Host "Restoring PostgreSQL..."
cmd /c "type `"$Backup\postgres.dump`" | docker compose exec -T postgres pg_restore -U $PostgresUser -d $PostgresDb --clean --if-exists --no-owner"
if ($LASTEXITCODE -ne 0) { throw "pg_restore failed" }

Write-Host "Restoring uploads/assets/exports..."
docker compose cp (Join-Path $Backup "uploads\.") backend:/data/uploads | Out-Null

Write-Host "Restoring Redis snapshot..."
docker compose stop redis | Out-Null
docker compose cp (Join-Path $Backup "redis.rdb") redis:/data/dump.rdb | Out-Null
docker compose start redis | Out-Null

docker compose up -d backend worker vision-worker frontend | Out-Null
Write-Host "Restore completed from: $Backup"
