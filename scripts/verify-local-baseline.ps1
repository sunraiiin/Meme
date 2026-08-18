[CmdletBinding()]
param(
    [switch]$SkipDocker,
    [switch]$SkipFrontendBuild
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

function Invoke-BaselineStep {
    param(
        [Parameter(Mandatory)]
        [string]$Name,
        [Parameter(Mandatory)]
        [scriptblock]$Action
    )

    Write-Host "`n==> $Name"
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

foreach ($command in @('node', 'npm', 'uv')) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command not found on PATH: $command"
    }
}

Invoke-BaselineStep 'Backend Ruff' {
    Push-Location (Join-Path $repoRoot 'api')
    try {
        uv run ruff check .
    }
    finally {
        Pop-Location
    }
}

Invoke-BaselineStep 'Frontend ESLint' {
    Push-Location (Join-Path $repoRoot 'web')
    try {
        npm run lint
    }
    finally {
        Pop-Location
    }
}

if (-not $SkipFrontendBuild) {
    Invoke-BaselineStep 'Frontend production build' {
        Push-Location (Join-Path $repoRoot 'web')
        try {
            npm run build
        }
        finally {
            Pop-Location
        }
    }
}

if (-not $SkipDocker) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Required command not found on PATH: docker'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot '.env'))) {
        throw 'Missing root .env. Copy .env.example and replace the development secrets first.'
    }

    Invoke-BaselineStep 'Docker Compose configuration' {
        Push-Location $repoRoot
        try {
            docker compose config --quiet
        }
        finally {
            Pop-Location
        }
    }

    Invoke-BaselineStep 'Docker Compose service status' {
        Push-Location $repoRoot
        try {
            docker compose ps
        }
        finally {
            Pop-Location
        }
    }

    Write-Host "`n==> API hello"
    Invoke-RestMethod -Uri 'http://localhost:8000/api/hello' | Out-Host

    Write-Host "`n==> API health"
    Invoke-RestMethod -Uri 'http://localhost:8000/api/health' | Out-Host
}

Write-Host "`nLocal baseline checks completed."
