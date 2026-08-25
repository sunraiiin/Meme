[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Title,

    [Parameter(Mandatory = $true)]
    [string]$BodyFile
)

$ErrorActionPreference = "Stop"

$bodyPath = (Resolve-Path -LiteralPath $BodyFile).Path
$body = [System.IO.File]::ReadAllText($bodyPath)
if ([string]::IsNullOrWhiteSpace($body)) {
    throw "Issue body must not be empty."
}
if ($body.Contains('\n') -or $body.Contains('`n') -or $body.Contains('\r')) {
    throw "Issue body contains literal escape sequences. Use real Markdown line breaks."
}

& gh issue create `
    --repo "sunraiiin/Meme" `
    --title $Title `
    --body-file $bodyPath

if ($LASTEXITCODE -ne 0) {
    throw "gh issue create failed with exit code $LASTEXITCODE."
}
