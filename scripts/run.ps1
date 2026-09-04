param(
    [ValidateSet("start", "stop", "status")]
    [string]$Action = "start",
    [switch]$NoBrowser
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Missing .venv. Run uv sync --frozen --extra dev --extra report first."
}
$launchArgs = @((Join-Path $PSScriptRoot "launch.py"), $Action)
if ($NoBrowser) { $launchArgs += "--no-browser" }
& $pythonPath @launchArgs
exit $LASTEXITCODE

