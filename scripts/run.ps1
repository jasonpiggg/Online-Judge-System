$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = if ($previousPythonPath) { "$repoRoot;$previousPythonPath" } else { $repoRoot }
$backend = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "oj.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WindowStyle Hidden -PassThru
try {
    $env:OJ_API_URL = "http://127.0.0.1:8000"
    python -m streamlit run frontend/app.py --server.address 127.0.0.1 --server.port 8501
}
finally {
    Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
    $env:PYTHONPATH = $previousPythonPath
}

