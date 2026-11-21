<#
.SYNOPSIS
    Build the Windows distribution of Seraphine.

.DESCRIPTION
    Produces a stable distribution layout:

        dist/Seraphine/Seraphine.exe
        dist/Seraphine.7z

    The version is embedded in the executable and release metadata. Build
    output paths never include the version number.

.PARAMETER NoArchive
    Build dist/Seraphine without creating dist/Seraphine.7z.

.EXAMPLE
    .\make.ps1
    .\make.ps1 -NoArchive
#>

param(
    [Switch]$NoArchive
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$distRoot = Join-Path $projectRoot 'dist'
$appDir = Join-Path $distRoot 'Seraphine'
$buildDir = Join-Path $projectRoot 'build'
$archivePath = Join-Path $distRoot 'Seraphine.7z'
$mainPath = Join-Path $projectRoot 'main.py'
$iconPath = Join-Path $projectRoot 'app\resource\images\logo.ico'
$appSource = Join-Path $projectRoot 'app'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

function Remove-ProjectPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $root = [IO.Path]::GetFullPath($projectRoot)
    $target = [IO.Path]::GetFullPath($Path)
    $prefix = $root + [IO.Path]::DirectorySeparatorChar
    if ($target -eq $root -or -not $target.StartsWith(
            $prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove path outside the project: $target"
    }
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

$runningBuild = Get-Process Seraphine -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -and [IO.Path]::GetFullPath($_.Path).StartsWith(
        [IO.Path]::GetFullPath($appDir) + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase)
}
if ($runningBuild) {
    throw 'Seraphine is running from dist\Seraphine. Close it before rebuilding.'
}

& $python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'PyInstaller is not installed. Run: .\.venv\Scripts\python.exe -m pip install pyinstaller==6.21.0'
}

$versionMatch = Select-String -LiteralPath (Join-Path $projectRoot 'app\common\config.py') `
    -Pattern '^VERSION\s*=.*or\s+"([^"]+)"' | Select-Object -Last 1
if (-not $versionMatch) {
    throw 'Unable to read VERSION from app\common\config.py'
}
$version = $versionMatch.Matches[0].Groups[1].Value

New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
Remove-ProjectPath -Path $appDir
Remove-ProjectPath -Path $buildDir

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --icon $iconPath `
    --name Seraphine `
    --distpath $distRoot `
    --workpath $buildDir `
    --specpath $buildDir `
    --collect-submodules tufup `
    --collect-submodules tuf `
    $mainPath
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path -LiteralPath (Join-Path $appDir 'Seraphine.exe'))) {
    throw 'PyInstaller did not produce dist\Seraphine\Seraphine.exe'
}

Copy-Item -LiteralPath $appSource -Destination $appDir -Recurse -Force

$sourceOnlyPaths = @(
    (Join-Path $appDir 'app\common'),
    (Join-Path $appDir 'app\components'),
    (Join-Path $appDir 'app\lol'),
    (Join-Path $appDir 'app\view'),
    (Join-Path $appDir 'app\resource\i18n\Seraphine.zh_CN.ts'),
    (Join-Path $appDir 'app\resource\bin\fix_lcu_window.c'),
    (Join-Path $appDir 'app\resource\bin\readme.md')
)
foreach ($path in $sourceOnlyPaths) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}

Get-ChildItem -LiteralPath (Join-Path $appDir 'app\resource') `
    -Directory -Filter 'game*' -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }

$basePath = $appDir + [IO.Path]::DirectorySeparatorChar
Get-ChildItem -LiteralPath $appDir -File -Recurse |
    Where-Object { $_.FullName -ne (Join-Path $appDir 'filelist.txt') } |
    ForEach-Object { $_.FullName.Replace($basePath, '') } |
    Out-File -LiteralPath (Join-Path $appDir 'filelist.txt') -Encoding UTF8

if (-not $NoArchive) {
    $sevenZip = Get-Command 7z -ErrorAction SilentlyContinue
    if (-not $sevenZip) {
        throw '7z is required to create dist\Seraphine.7z.'
    }
    if (Test-Path -LiteralPath $archivePath) {
        Remove-Item -LiteralPath $archivePath -Force
    }
    Push-Location -LiteralPath $appDir
    try {
        & $sevenZip.Source a -t7z -mx=5 $archivePath * -r
        if ($LASTEXITCODE -ne 0) {
            throw "7z failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

Remove-ProjectPath -Path $buildDir

Write-Host ''
Write-Host "Build complete: Seraphine $version"
Write-Host "Executable: $appDir\Seraphine.exe"
if (-not $NoArchive) {
    Write-Host "Archive:    $archivePath"
}
