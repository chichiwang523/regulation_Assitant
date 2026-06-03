param(
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$pythonCandidates = @(
  (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"),
  "python",
  "py"
)

$python = $null
foreach ($candidate in $pythonCandidates) {
  if (Test-Path -LiteralPath $candidate) {
    $python = $candidate
    break
  }
  $command = Get-Command $candidate -ErrorAction SilentlyContinue
  if ($command) {
    $python = $command.Source
    break
  }
}

if (-not $python) {
  throw "Python was not found. Install Python, or open this project in Codex so the bundled runtime is available."
}

function Test-LocalPort {
  param([int]$TargetPort)
  $client = [System.Net.Sockets.TcpClient]::new()
  try {
    $async = $client.BeginConnect("127.0.0.1", $TargetPort, $null, $null)
    if (-not $async.AsyncWaitHandle.WaitOne(500)) {
      return $false
    }
    $client.EndConnect($async)
    return $true
  } catch {
    return $false
  } finally {
    $client.Close()
  }
}

if (Test-LocalPort -TargetPort $Port) {
  Write-Host "Server is already running: http://127.0.0.1:$Port"
  return
}

Write-Host "Using Python: $python"
Write-Host "Starting regulation assistant: http://127.0.0.1:$Port"
& $python -W ignore::DeprecationWarning app.py
