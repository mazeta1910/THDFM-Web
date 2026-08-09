# Copia emblemas do pack FMG para data/clubes/emblemas-por-id/
# Somente clubes listados em data/clubes/fm24_clubes_uf.csv.
#
# Uso (PowerShell):
#   cd C:\Users\mathe\OneDrive\Documentos\GitHub\THDFM-Bolao-Copa-do-Brasil
#   .\scripts\copiar_emblemas_fm_pack.ps1
#
# Ou com caminhos customizados:
#   .\scripts\copiar_emblemas_fm_pack.ps1 `
#     -SourceDir "C:\caminho\Normal" `
#     -DestDir "data\clubes\emblemas-por-id"

param(
    [string]$SourceDir = "C:\Users\mathe\OneDrive\Documentos\Sports Interactive\Football Manager 26\graphics\logos\FMG Standard Logos\Clubs\Normal\Normal",
    [string]$CsvPath = "data\clubes\fm24_clubes_uf.csv",
    [string]$DestDir = "data\clubes\emblemas-por-id",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    if (Test-Path (Join-Path $PSScriptRoot "..\data\clubes")) {
        return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    }
    return (Get-Location).Path
}

$root = Get-RepoRoot
Set-Location $root

$csvFull = Join-Path $root $CsvPath
$destFull = Join-Path $root $DestDir

if (-not (Test-Path $SourceDir)) {
    throw "Pasta do pack nao encontrada: $SourceDir"
}
if (-not (Test-Path $csvFull)) {
    throw "CSV nao encontrado: $csvFull"
}

New-Item -ItemType Directory -Force -Path $destFull | Out-Null

# Unique IDs do catalogo BR (sem pontos)
$ids = New-Object 'System.Collections.Generic.HashSet[string]'
$csvLines = Get-Content -Path $csvFull -Encoding UTF8
$header = $csvLines[0]
$delim = ";"
if (($header -split ",").Count -gt ($header -split ";").Count) { $delim = "," }

foreach ($line in $csvLines | Select-Object -Skip 1) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $cols = $line.Split($delim)
    $uid = $cols[0].Trim().Trim('"')
    $digits = ($uid -replace '\D', '')
    if ($digits.Length -gt 0) { [void]$ids.Add($digits) }
}

Write-Host "Clubes no CSV: $($ids.Count)"
Write-Host "Origem: $SourceDir"
Write-Host "Destino: $destFull"

$copied = 0
$skippedExisting = 0
$missing = New-Object System.Collections.Generic.List[string]
$extOrder = @(".png", ".jpg", ".jpeg", ".webp", ".svg")

foreach ($id in ($ids | Sort-Object)) {
    $destPng = Join-Path $destFull "$id.png"
    if ((Test-Path $destPng) -and -not $Force) {
        $skippedExisting++
        continue
    }

    $src = $null
    foreach ($ext in $extOrder) {
        $candidate = Join-Path $SourceDir ($id + $ext)
        if (Test-Path $candidate) {
            $src = $candidate
            break
        }
    }

    if (-not $src) {
        $missing.Add($id)
        continue
    }

    if ([IO.Path]::GetExtension($src).ToLowerInvariant() -eq ".png") {
        Copy-Item -LiteralPath $src -Destination $destPng -Force
    }
    else {
        # Copia com extensao original; conversao PNG fica para o agente/processamento
        $destOther = Join-Path $destFull ($id + [IO.Path]::GetExtension($src).ToLowerInvariant())
        Copy-Item -LiteralPath $src -Destination $destOther -Force
    }
    $copied++
    if (($copied % 100) -eq 0) {
        Write-Host "  ... $copied copiados"
    }
}

Write-Host ""
Write-Host "=== Resumo ==="
Write-Host "Copiados agora:     $copied"
Write-Host "Ja existiam:        $skippedExisting"
Write-Host "Sem arquivo no pack:$($missing.Count)"
Write-Host "Total PNG no dest:  $((Get-ChildItem -LiteralPath $destFull -Filter *.png -File).Count)"

$missingPath = Join-Path $root "data\clubes\emblemas_pack_missing.txt"
$missing | Set-Content -Path $missingPath -Encoding UTF8
Write-Host "Lista sem match:    $missingPath"

if ($copied -gt 0) {
    Write-Host ""
    Write-Host "Proximo:"
    Write-Host "  git add data/clubes/emblemas-por-id"
    Write-Host "  git commit -m `"Copia emblemas do pack FMG para clubes BR.`""
    Write-Host "  git push origin cursor/emblemas-fm-ids-6409"
}
