param(
  [Parameter(Mandatory = $true)]
  [string]$HostName,

  [string[]]$Users = @("root", "ubuntu"),
  [string]$KeyDir = "$env:USERPROFILE\.ssh"
)

$ErrorActionPreference = "Stop"

Write-Host "Testing SSH host: $HostName"
Write-Host ""

foreach ($user in $Users) {
  Write-Host "Testing passwordless/default key login: ${user}@${HostName}"
  ssh -o BatchMode=yes -o ConnectTimeout=8 "${user}@${HostName}" "whoami && hostname"
  if ($LASTEXITCODE -eq 0) {
    Write-Host "SUCCESS: ${user}@${HostName}"
    exit 0
  }
}

$keyCandidates = Get-ChildItem -Path $KeyDir -File -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -notlike "*.pub" -and
    $_.Name -notmatch "known_hosts|config|authorized_keys"
  }

foreach ($key in $keyCandidates) {
  foreach ($user in $Users) {
    Write-Host "Testing key $($key.FullName) as ${user}@${HostName}"
    ssh -i $key.FullName -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=8 "${user}@${HostName}" "whoami && hostname"
    if ($LASTEXITCODE -eq 0) {
      Write-Host "SUCCESS"
      Write-Host "User: $user"
      Write-Host "IdentityFile: $($key.FullName)"
      exit 0
    }
  }
}

Write-Host ""
Write-Host "No working SSH key was found in $KeyDir."
Write-Host "If you know the server password, test it manually:"
Write-Host "  ssh root@$HostName `"whoami && hostname`""
Write-Host "  ssh ubuntu@$HostName `"whoami && hostname`""
exit 1
