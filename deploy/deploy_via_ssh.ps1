param(
  [Parameter(Mandatory = $true)]
  [string]$HostName,

  [string]$User = "root",
  [string]$RemoteDir = "/tmp/regulation-assistant-deploy",
  [string]$Port = "8083",
  [string]$IdentityFile = "",
  [switch]$LoginOnly
)

$ErrorActionPreference = "Stop"
$archive = Join-Path (Get-Location) "dist\regulation-assistant-deploy.tar.gz"

function Invoke-Native {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Command,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
  )

  Write-Host ">> $Command $($Arguments -join ' ')"
  & $Command @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code ${LASTEXITCODE}: $Command $($Arguments -join ' ')"
  }
}

New-Item -ItemType Directory -Force -Path "dist" | Out-Null
Invoke-Native tar --exclude ".git" --exclude "__pycache__" --exclude ".env" --exclude ".tools" --exclude "server*.log" --exclude "dist" --exclude "data/uploads" --exclude "data/regulations/_cache" -czf $archive .

$sshArgs = @()
if ($IdentityFile) {
  $sshArgs += @("-i", $IdentityFile)
}

$target = "${User}@${HostName}"
Invoke-Native ssh @sshArgs $target "echo SSH login ok && whoami && hostname"
if ($LoginOnly) {
  Write-Host "Login test succeeded. Re-run without -LoginOnly to deploy."
  exit 0
}

Invoke-Native ssh @sshArgs $target "rm -rf '$RemoteDir' && mkdir -p '$RemoteDir'"
Invoke-Native scp @sshArgs $archive "${target}:$RemoteDir/app.tar.gz"
Invoke-Native ssh @sshArgs $target "cd '$RemoteDir' && tar -xzf app.tar.gz && REG_ASSISTANT_HOST=0.0.0.0 REG_ASSISTANT_PORT=$Port sudo -E bash deploy/install_on_ubuntu.sh"
