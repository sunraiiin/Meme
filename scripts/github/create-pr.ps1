[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Title,

    [Parameter(Mandatory = $true)]
    [string]$BodyFile,

    [Parameter(Mandatory = $true)]
    [string]$Head,

    [string]$Base = "main",

    [switch]$Draft
)

$ErrorActionPreference = "Stop"

$bodyPath = (Resolve-Path -LiteralPath $BodyFile).Path
$body = [System.IO.File]::ReadAllText($bodyPath)
if ([string]::IsNullOrWhiteSpace($body)) {
    throw "PR body must not be empty."
}
if ($body.Contains('\n') -or $body.Contains('`n') -or $body.Contains('\r')) {
    throw "PR body contains literal escape sequences. Use real Markdown line breaks."
}

$ghArgs = @(
    "pr", "create",
    "--repo", "sunraiiin/Meme",
    "--base", $Base,
    "--head", $Head,
    "--title", $Title,
    "--body-file", $bodyPath
)
if ($Draft) {
    $ghArgs += "--draft"
}

& gh @ghArgs

if ($LASTEXITCODE -ne 0) {
    throw "gh pr create failed with exit code $LASTEXITCODE."
}
