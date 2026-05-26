<#
.SYNOPSIS
  Idempotent setup for issue-to-pr-agent on Windows 11 + PowerShell 5.1.

.DESCRIPTION
  - Verifies prerequisites (git, gh, uv).
  - Ensures global git identity is set.
  - Ensures .env exists (copies from .env.example if missing) and warns if GROQ_API_KEY is the placeholder.
  - Runs `uv sync` to install dependencies.
  - Runs the test suite.
  - Reports next steps.

  Safe to run repeatedly: every check is idempotent.

.EXAMPLE
  powershell -File scripts\bootstrap.ps1
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
Require-Tool git "Install Git for Windows."
Require-Tool gh  "Install GitHub CLI: winget install --id GitHub.cli"
Require-Tool uv  "Install uv: winget install --id astral-sh.uv"

Write-Output "`n=== Git identity ==="
$name  = git config --global user.name
$email = git config --global user.email
if (-not $name -or -not $email) {
    Write-Error "Set git config --global user.name and user.email before running this script."
}
Write-Output "  [ok] $name <$email>"

Write-Output "`n=== gh auth ==="
gh auth status 2>&1 | Select-Object -First 4

Write-Output "`n=== .env ==="
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Output "  [created] .env from .env.example -- now edit GROQ_API_KEY before running the agent."
} else {
    Write-Output "  [ok] .env exists"
}
$envContent = Get-Content .env -Raw
if ($envContent -match 'gsk_REPLACE_ME') {
    Write-Warning "GROQ_API_KEY is still the placeholder. Get one at https://console.groq.com/keys"
}

Write-Output "`n=== uv sync ==="
uv sync

Write-Output "`n=== pytest (unit only -- integration needs GROQ_API_KEY) ==="
uv run pytest -q tests/unit

Write-Output "`n=== Next steps ==="
Write-Output "  uv run issue-to-pr version           # sanity check the CLI"
Write-Output "  uv run pytest -q                     # full suite (includes integration if GROQ_API_KEY set)"
Write-Output "  uv run issue-to-pr run --issue ...   # once Executor lands (Week 1 next block)"
Write-Output "  Postgres for Week 3+: see docs/POSTGRES.md (uses pgsql-portable, no Docker)"
Write-Output "`nDone."
