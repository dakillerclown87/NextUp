# Publisher setup using the installed NextUp runtime; no separate Python needed.
$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path $PSScriptRoot -Parent
$installRoot = Join-Path $env:LOCALAPPDATA 'NextUp'
$marker = Join-Path $installRoot 'current.json'
if (!(Test-Path -LiteralPath $marker)) {
    throw 'Install NextUp first. Developer alternative: python tools/release.py --generate-key --repository dakillerclown87/NextUp'
}
$version = (Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json).version
if ($version -notmatch '^\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?$') {
    throw 'The installed NextUp version marker is invalid.'
}
$python = Join-Path $installRoot "versions\$version\runtime\python.exe"
if (!(Test-Path -LiteralPath $python)) { throw 'The installed NextUp runtime is missing.' }
$publisher = Get-Content -LiteralPath (Join-Path $sourceRoot 'publisher.json') -Raw | ConvertFrom-Json
if ($publisher.public_key) {
    Write-Host 'A public signing key is already configured. Restore/use its matching private key; do not replace it.'
    return
}
& $python (Join-Path $PSScriptRoot 'release.py') --generate-key --repository dakillerclown87/NextUp
if ($LASTEXITCODE -ne 0) { throw 'Signing-key setup failed. Read the error above.' }
Write-Host 'Public configuration updated: publisher.json in this source folder.'
Write-Host 'Private key stays in your user profile: .nextup-signing\private-key.txt'
Write-Host 'Back it up securely. Do not upload the private file to your repository or send it in chat.'
Write-Host 'Add its contents as the NEXTUP_SIGNING_KEY Actions secret here:'
Write-Host 'https://github.com/dakillerclown87/NextUp/settings/secrets/actions/new'
Write-Host 'Upload ONLY the updated publisher.json to the repository. Continue with docs/PUBLISHING.md.'
