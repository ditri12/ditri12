# Installs the authorized security-assessment team onto this Windows machine.
# Default: user level (~/.claude). Or: .\install.ps1 -Project "C:\path\to\app"
# Authorized testing only — use on apps you own or may test.
param([string]$Project = "")

$SrcDir    = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$AgentsSrc = Join-Path $SrcDir ".claude\agents"
$CmdsSrc   = Join-Path $SrcDir ".claude\commands"

if (-not (Test-Path $AgentsSrc)) {
  Write-Error "Run this from inside the ditri12 repo (cannot find .claude\agents)."; exit 1
}

$DestRoot = Join-Path $HOME ".claude"
if ($Project -ne "") { $DestRoot = Join-Path $Project ".claude" }

New-Item -ItemType Directory -Force -Path (Join-Path $DestRoot "agents")   | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DestRoot "commands") | Out-Null
Copy-Item -Force (Join-Path $AgentsSrc "*.md") (Join-Path $DestRoot "agents")
Copy-Item -Force (Join-Path $CmdsSrc "security-assessment.md") (Join-Path $DestRoot "commands")

Write-Host "Installed security-assessment team to: $DestRoot"
Write-Host "Next: open a session in your project and run /security-assessment"
