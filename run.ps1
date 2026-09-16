# День 13. Состояние задачи (Task State Machine)
#   .\run.ps1 -Mock     -- демонстрация без API
#   .\run.ps1           -- реальный прогон (ключ берётся из .env)
param([switch]$Mock)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $Mock -and -not (Test-Path .\.env)) {
    Write-Host "Нет файла .env. Задай ключ: py -3 .\config.py --set-key" -ForegroundColor Red
    exit 1
}

$flags = @()
if ($Mock) { $flags += "--mock" }

Write-Host "== Демонстрация жизненного цикла ==" -ForegroundColor Cyan
py -3 .\demo.py @flags

Write-Host "== Отчёт ==" -ForegroundColor Cyan
py -3 .\report.py

Write-Host "Готово. Открой RESULTS.md" -ForegroundColor Green
