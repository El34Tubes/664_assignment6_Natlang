# start_server.ps1
# Stops any process on port 8000, activates .venv if present, starts uvicorn, and checks /healthz
Set-Location -Path "$PSScriptRoot\.."
# Stop processes bound to port 8000
$connections = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($connections) {
    $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
        try {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            Write-Output ("Stopped PID {0}" -f $procId)
        } catch {
            Write-Output ("Could not stop PID {0}" -f $procId)
            Write-Output $_.Exception.Message
        }
    }
} else { Write-Output 'No process on port 8000' }

# Activate venv if present
$venvActivate = Join-Path (Get-Location) '.venv\Scripts\Activate.ps1'
if (Test-Path $venvActivate) { . $venvActivate; Write-Output 'Activated venv' } else { Write-Output 'No venv activate found' }

if (-not $env:GEMINI_API_KEY) { Write-Output 'Warning: GEMINI_API_KEY not set in this session' }

# Start uvicorn in background
Start-Process -FilePath python -ArgumentList '-m','uvicorn','natlang.server:app','--host','127.0.0.1','--port','8000' -WindowStyle Hidden -PassThru | Out-Null
Start-Sleep -Seconds 2
try {
    $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/healthz' -Method GET -TimeoutSec 5
    Write-Output ("HEALTH:" + ($r | ConvertTo-Json -Compress))
} catch {
    Write-Output ("ERROR:" + $_.Exception.Message)
}
