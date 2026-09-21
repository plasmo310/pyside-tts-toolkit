<#
.SYNOPSIS
  3 つの TTS エンジンの隔離環境をまとめて構築する。

.DESCRIPTION
  Qwen3-TTS / Chatterbox / Irodori-TTS は transformers と torch のピンが
  互いに排他的で、1 つの仮想環境には同居できない。このスクリプトは
  用途ごとに独立した仮想環境を作る。Python 本体には何も入れない。

  仮想環境はリポジトリ直下の .venvs/ にまとめる（各プロジェクトの中には作らない）。

    .venvs/common             共通層。python -m tts_sample。torch なし
    .venvs/engine-qwen        Qwen3-TTS       transformers 4.57.3
    .venvs/engine-chatterbox  Chatterbox      transformers 5.2.0
    .venvs/engine-irodori     Irodori-TTS     transformers 5.12.x

  置き場は各プロジェクトの mise.toml が UV_PROJECT_ENVIRONMENT で指定している。
  そのため手で uv sync しても同じ場所に作られる（mise exec 経由で実行すること）。

  前提: mise, uv, git。NVIDIA GPU を使う場合は CUDA 12.8 対応ドライバ。
  重みのダウンロードを含めると合計 10GB 以上、初回は数十分かかる。

.PARAMETER Engines
  構築するエンジン。既定は全部。例: -Engines qwen,chatterbox

.EXAMPLE
  pwsh scripts/setup_engines.ps1
  pwsh scripts/setup_engines.ps1 -Engines irodori
#>
[CmdletBinding()]
param(
    [ValidateSet('common', 'qwen', 'chatterbox', 'irodori')]
    [string[]]$Engines = @('common', 'qwen', 'chatterbox', 'irodori')
)

$ErrorActionPreference = 'Stop'

# scripts/ はリポジトリ直下。Python のコードは python/ 配下にまとまっている。
$RepoRoot = Split-Path -Parent $PSScriptRoot
$PythonRoot = Join-Path $RepoRoot 'python'

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "=== $Message ===" -ForegroundColor Cyan
}

function Assert-Command([string]$Name, [string]$Hint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name が見つかりません。$Hint"
    }
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

if ($Engines -contains 'common') {
    Write-Step "共通層 (.venvs/common)"
    Push-Location $PythonRoot
    try {
        mise exec -- uv sync --extra dev
        if ($LASTEXITCODE -ne 0) { throw "共通層の uv sync に失敗しました。" }
    }
    finally { Pop-Location }
}

if ($Engines -contains 'qwen') {
    Write-Step "Qwen3-TTS (.venvs/engine-qwen)"
    Push-Location (Join-Path $PythonRoot 'engines/qwen')
    try {
        mise exec -- uv sync
        if ($LASTEXITCODE -ne 0) { throw "qwen の uv sync に失敗しました。" }
    }
    finally { Pop-Location }
}

if ($Engines -contains 'chatterbox') {
    Write-Step "Chatterbox (.venvs/engine-chatterbox)"
    Push-Location (Join-Path $PythonRoot 'engines/chatterbox')
    try {
        mise exec -- uv sync
        if ($LASTEXITCODE -ne 0) { throw "chatterbox の uv sync に失敗しました。" }
    }
    finally { Pop-Location }
}

if ($Engines -contains 'irodori') {
    Write-Step "Irodori-TTS (上流リポジトリを clone して .venvs/engine-irodori を作る)"
    $IrodoriDir = Join-Path $PythonRoot 'engines/irodori'
    $Vendor = Join-Path $IrodoriDir 'vendor/Irodori-TTS'

    if (-not (Test-Path (Join-Path $Vendor '.git'))) {
        # Irodori は PyPI 未公開で、依存の dacvae も PyPI に無いため clone が唯一の経路。
        New-Item -ItemType Directory -Force (Join-Path $IrodoriDir 'vendor') | Out-Null
        git clone --depth 1 https://github.com/Aratako/Irodori-TTS.git $Vendor
        if ($LASTEXITCODE -ne 0) { throw "Irodori-TTS の clone に失敗しました。" }
    }
    else {
        Write-Host "clone 済みをそのまま使います: $Vendor"
    }

    # Windows + Python 3.12 で必要な調整（詳細は patch_vendor.py の docstring）。
    & (Join-Path $RepoRoot '.venvs/common/Scripts/python.exe') (Join-Path $IrodoriDir 'patch_vendor.py')
    if ($LASTEXITCODE -ne 0) { throw "patch_vendor.py に失敗しました。" }

    Push-Location $Vendor
    try {
        # cu128 = NVIDIA CUDA 12.8。AMD は rocm、GPU 無しは cpu に読み替える。
        mise exec -- uv sync --extra cu128
        if ($LASTEXITCODE -ne 0) { throw "irodori の uv sync に失敗しました。" }
    }
    finally { Pop-Location }
}

Write-Step "構築結果"
& (Join-Path $RepoRoot '.venvs/common/Scripts/python.exe') -m tts_sample engines

Write-Host ""
Write-Host "次の一歩:" -ForegroundColor Green
Write-Host "  .\.venvs\common\Scripts\python.exe -m tts_sample doctor"
Write-Host "  .\.venvs\common\Scripts\python.exe -m tts_sample synth --engine chatterbox --text `"こんにちは。`" --lang ja --out outputs\hello.wav"
Write-Host ""
Write-Host "初回の合成はモデル重みのダウンロードを伴うため時間がかかります。" -ForegroundColor Yellow
