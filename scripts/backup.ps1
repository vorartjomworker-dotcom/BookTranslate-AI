$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BackupRoot = if ($env:BACKUP_ROOT) { $env:BACKUP_ROOT } else { Join-Path $Root "backups" }
$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$Dest = Join-Path $BackupRoot $Stamp
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Set-Location $Root

$PostgresUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "booktranslate" }
$PostgresDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "booktranslate" }

Write-Host "Creating PostgreSQL backup..."
cmd /c "docker compose exec -T postgres pg_dump -U $PostgresUser -d $PostgresDb -Fc > `"$Dest\postgres.dump`""
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed" }

Write-Host "Creating Redis snapshot..."
docker compose exec -T redis redis-cli --rdb /data/booktranslate-backup.rdb | Out-Null
docker compose cp redis:/data/booktranslate-backup.rdb (Join-Path $Dest "redis.rdb") | Out-Null
docker compose exec -T redis rm -f /data/booktranslate-backup.rdb | Out-Null

Write-Host "Copying uploads/assets/exports..."
$Uploads = Join-Path $Dest "uploads"
New-Item -ItemType Directory -Force -Path $Uploads | Out-Null
docker compose cp backend:/data/uploads/. $Uploads | Out-Null

$GitSha = try { (git rev-parse HEAD).Trim() } catch { "unknown" }
@("created_utc=$Stamp", "git_sha=$GitSha", "postgres_db=$PostgresDb") | Set-Content (Join-Path $Dest "manifest.txt")
Write-Host "Backup created: $Dest"
