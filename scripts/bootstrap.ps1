<#
.SYNOPSIS
  Idempotent setup for issue-to-pr-agent on Windows 11 + PowerShell 5.1.

.DESCRIPTION
  - Verifies prerequisites (git, gh, uv, Docker).
  - Ensures global git identity is set.
  - Runs `uv sync` to install dependencies.
  - Starts the Postgres container.
  - Reports next steps.

  Safe to run repeatedly: every check is idempotent.

.EXAMPLE
  pwsh -File scripts\bootstrap.ps1
#>

$ErrorActionPreference = "Stop"

function Require-Tool($name, $hint) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($null -eq $cmd) {
        Write-Error "Missing tool: $name. $hint"
    }
    Write-Output "  [ok] $name -> $($cmd.Source)"
}

Write-Output "=== Prerequisites ==="
Require-Tool git    "Install Git for Windows."
Require-Tool gh     "Install GitHub CLI: winget install --id GitHub.cli"
Require-Tool uv     "Install uv: winget install --id astral-sh.uv"
Require-Tool docker "Install Docker Desktop."

Write-Output "`n=== Git identity ==="
$name  = git config --global user.name
$email = git config --global user.email
if (-not $name -or -not $email) {
    Write-Error "Set git config --global user.name and user.email before running this script."
}
Write-Output "  [ok] $name <$email>"

Write-Output "`n=== gh auth ==="
gh auth status 2>&1 | Select-Object -First 4

Write-Output "`n=== uv sync ==="
uv sync

Write-Output "`n=== docker compose up -d postgres ==="
docker compose up -d postgres

Write-Output "`n=== Smoke ==="
Write-Output "  Run: uv run pytest -q"
Write-Output "  Run: uv run issue-to-pr version"
Write-Output "`nDone."
