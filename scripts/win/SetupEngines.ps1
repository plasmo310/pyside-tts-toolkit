<#
.SYNOPSIS
  TTS Toolkit の仮想環境をまとめて構築する。

.DESCRIPTION
  Qwen3-TTS / Chatterbox / Irodori-TTS は transformers と torch のピンが
  互いに排他的で、1 つの仮想環境には同居できない。このスクリプトは
  用途ごとに独立した仮想環境を作る。Python 本体には何も入れない。

  仮想環境はリポジトリ直下の .venvs/ にまとめる（定義の隣には作らない）。

    .venvs/common             共通層と GUI。torch なし
    .venvs/engine-qwen        Qwen3-TTS       transformers 4.57.3
    .venvs/engine-chatterbox  Chatterbox      transformers 5.2.0
    .venvs/engine-irodori     Irodori-TTS     transformers 5.12.x

  置き場は各 mise.toml が UV_PROJECT_ENVIRONMENT で指定している。そのため
  手で uv sync しても同じ場所に作られる（mise exec 経由で実行すること）。

  前提: mise, uv, git。NVIDIA GPU を使う場合は CUDA 12.8 対応ドライバ。
  重みのダウンロードを含めると合計 10GB 以上、初回は数十分かかる。

.PARAMETER Targets
  構築する対象。既定は全部。例: -Targets qwen,chatterbox

.EXAMPLE
  powershell scripts/win/SetupEngines.ps1
  pwsh scripts/win/SetupEngines.ps1
  pwsh scripts/win/SetupEngines.ps1 -Targets irodori
#>
[CmdletBinding()]
param(
    [ValidateSet('common', 'qwen', 'chatterbox', 'irodori')]
    [string[]]$Targets = @('common', 'qwen', 'chatterbox', 'irodori')
)

$ErrorActionPreference = 'Stop'

# scripts\win\ から見て 2 階層上がリポジトリルート
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$EngineEnvRoot = Join-Path $RepoRoot 'engine_env'
$CommonPython = Join-Path $RepoRoot '.venvs\common\Scripts\python.exe'

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "=== $Message ===" -ForegroundColor Cyan
}

function Assert-Command([string]$Name, [string]$Hint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name が見つかりません。$Hint"
    }
}

function Invoke-UvSync([string]$WorkDir, [string]$Label, [string[]]$ExtraArgs) {
    Push-Location $WorkDir
    try {
        mise exec -- uv sync @ExtraArgs
        if ($LASTEXITCODE -ne 0) { throw "$Label の uv sync に失敗しました。" }
    }
    finally { Pop-Location }
}

Write-Step "前提コマンドの確認"
Assert-Command 'mise' 'https://mise.jdx.dev/installing-mise.html を参照してください。'
Assert-Command 'uv'   'https://docs.astral.sh/uv/getting-started/installation/ を参照してください。'
Assert-Command 'git'  'Git for Windows を入れてください。'
Write-Host "OK"

Write-Step "Python 3.12 の用意 (mise)"
Push-Location $RepoRoot
try {
    mise install
    if ($LASTEXITCODE -ne 0) { throw "mise install に失敗しました。" }
    mise exec -- python --version
}
finally { Pop-Location }

if ($Targets -contains 'common') {
    Write-Step "共通層と GUI (.venvs/common)"
    Invoke-UvSync $RepoRoot '共通層' @('--extra', 'dev')
}

if ($Targets -contains 'qwen') {
    Write-Step "Qwen3-TTS (.venvs/engine-qwen)"
    Invoke-UvSync (Join-Path $EngineEnvRoot 'qwen') 'qwen' @()
}

if ($Targets -contains 'chatterbox') {
    Write-Step "Chatterbox (.venvs/engine-chatterbox)"
    Invoke-UvSync (Join-Path $EngineEnvRoot 'chatterbox') 'chatterbox' @()
}

if ($Targets -contains 'irodori') {
    Write-Step "Irodori-TTS (上流を clone して .venvs/engine-irodori を作る)"
    $IrodoriDir = Join-Path $EngineEnvRoot 'irodori'
    $Vendor = Join-Path $IrodoriDir 'vendor\Irodori-TTS'

    if (-not (Test-Path (Join-Path $Vendor '.git'))) {
        # Irodori は PyPI 未公開で、依存の dacvae も PyPI に無いため
        # clone が唯一の経路。
        New-Item -ItemType Directory -Force (Join-Path $IrodoriDir 'vendor') | Out-Null
        git clone --depth 1 https://github.com/Aratako/Irodori-TTS.git $Vendor
        if ($LASTEXITCODE -ne 0) { throw "Irodori-TTS の clone に失敗しました。" }
    }
    else {
        Write-Host "clone 済みをそのまま使います: $Vendor"
    }

    # Windows + Python 3.12 で必要な調整（詳細は patch_vendor.py の docstring）
    & $CommonPython (Join-Path $IrodoriDir 'patch_vendor.py')
    if ($LASTEXITCODE -ne 0) { throw "patch_vendor.py に失敗しました。" }

    # cu128 = NVIDIA CUDA 12.8。AMD は rocm、GPU 無しは cpu に読み替える。
    Invoke-UvSync $Vendor 'irodori' @('--extra', 'cu128')
}

Write-Step "構築結果"
& $CommonPython -m ttstoolkit.cli engines

Write-Host ""
Write-Host "次の一歩:" -ForegroundColor Green
Write-Host "  .\.venvs\common\Scripts\python.exe -m ttstoolkit.cli doctor"
Write-Host "  .\scripts\win\LaunchApp.bat"
Write-Host ""
Write-Host "初回の合成はモデル重みのダウンロードを伴うため時間がかかります。" -ForegroundColor Yellow

