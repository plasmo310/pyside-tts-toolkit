# 00. 共通セットアップ

一からこのリポジトリを動かすまでの手順。Windows 11 + NVIDIA GPU を前提に書くが、
Linux でもパスの書き方以外はほぼ同じ。

## 1. 前提の確認

### 必要なもの

| 項目 | 条件 | 確認方法 |
|---|---|---|
| mise | 任意のバージョン | `mise --version` |
| uv | 0.5 以降 | `uv --version` |
| git | 任意 | `git --version` |
| NVIDIA ドライバ | CUDA 12.8 以降を報告すること | `nvidia-smi` |
| VRAM | 8GB 以上を推奨 | `nvidia-smi` |
| 空きディスク | 30GB 以上（venv 3 つ + 重み） | |

`nvidia-smi` の出力右上に `CUDA Version: 12.8` 以上が出ていればよい。
これはドライバが対応する CUDA の上限であって、CUDA Toolkit を別途入れる必要はない。
PyTorch の cu128 ビルドが必要なランタイムを同梱する。

GPU が無い場合も動作はするが、日本語の量産に使える速度ではない。

### mise と uv が未導入の場合

```powershell
# mise (https://mise.jdx.dev/installing-mise.html)
winget install jdx.mise

# uv (https://docs.astral.sh/uv/getting-started/installation/)
winget install astral-sh.uv
```

## 2. Python 3.12 を入れる

Python 本体には**ライブラリを一切入れない**。すべて uv が作る venv に入れる。

```powershell
git clone <このリポジトリ>
cd python-tts-sample
mise install
mise exec -- python --version   # Python 3.12.x
```

`mise.toml` が Python 3.12 を指定している。3.12 を選んでいる理由:

- Qwen3-TTS の公式推奨が 3.12
- Chatterbox は 3.10 以上（開発は 3.11）
- Irodori-TTS は 3.10 以上

さらに `mise.toml` では uv 向けに次の環境変数を設定している。

| 変数 | 値 | 理由 |
|---|---|---|
| `UV_PYTHON_DOWNLOADS` | `never` | uv が自前の CPython を落とすのを防ぐ |
| `UV_PYTHON_PREFERENCE` | `only-system` | mise が PATH に出す Python だけを使わせる |
| `UV_LINK_MODE` | `copy` | キャッシュと成果物が別ドライブのときの警告を避ける |
| `TTS_REPO_ROOT` | リポジトリのルート | 各プロジェクトの `mise.toml` から参照する |

これが無いと、uv が mise とは別の Python を勝手に選んで仮想環境を作ってしまう。

### 仮想環境の置き場

仮想環境は**リポジトリ直下の `.venvs/` にまとめる**。各プロジェクトの中には作らない。

```
.venvs/
  common             共通層・CLI・GUI。torch なし
  engine-qwen        Qwen3-TTS       transformers 4.57.3
  engine-chatterbox  Chatterbox      transformers 5.2.0
  engine-irodori     Irodori-TTS     transformers 5.12.x
```

置き場は各プロジェクトの `mise.toml` が `UV_PROJECT_ENVIRONMENT` で指定している。

```toml
# engine_env/qwen/mise.toml
[env]
UV_PROJECT_ENVIRONMENT = "{{env.TTS_REPO_ROOT}}/.venvs/engine-qwen"
```

そのため手で `uv sync` しても同じ場所に作られる。ただし
**`mise exec --` を付けて実行すること**。付けないとこの設定が効かず、
プロジェクトの中に `.venv` が作られてしまう。

## 3. 一括セットアップ

```powershell
pwsh scripts\win\SetupEngines.ps1
```

これが行うこと:

1. mise で Python 3.12 を用意
2. `.venvs/common` に共通層を入れる（torch は入らない。数秒で終わる）
3. `.venvs/engine-qwen` を作る
4. `.venvs/engine-chatterbox` を作る
5. Irodori-TTS を `engine_env/irodori/vendor/Irodori-TTS` へ clone し、venv を作る

エンジンを選んで実行することもできる。

```powershell
pwsh scripts\win\SetupEngines.ps1 -Targets common,chatterbox
```

手作業で進めたい場合や、どこかで失敗した場合は各エンジンの手順書を参照。

> [!note] 所要時間
> venv 3 つで CUDA 版 PyTorch を個別に持つため、ダウンロードは 10GB を超える。
> さらに初回の合成時にモデル重み（合計 10GB 前後）を Hugging Face から取得する。
> 回線によっては全体で 1 時間以上かかる。

## 4. 動作確認

コマンドは**リポジトリのルート**で実行する。

```powershell
# 環境の健全性チェック
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli doctor

# エンジン一覧と対応機能
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli engines

# 1 件合成（最も軽い chatterbox から試すとよい）
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli synth -e chatterbox -t "こんにちは。" -l ja -O hello.wav
```

`doctor` は各エンジンの venv の中で torch を読み込み、CUDA が使えるか、
GPU のアーキテクチャに対応したビルドかまで確認する。

### ディレクトリの役割

| パス | 内容 |
|---|---|
| `python/ttstoolkit/` | ツール本体。cli / gui / core / engine |
| `engine_env/` | 各エンジンの仮想環境を作るための定義 |
| `.venvs/` | 仮想環境の実体（git 管理外） |
| `input/voices/` | 参照音声の置き場（git 管理外） |
| `input/script/` | キャスト定義と台本 |
| `input/batch/` | バッチ入力 JSON の例 |
| `output/` | 生成した wav の置き場（git 管理外） |
| `resources/ui/` | GUI の stylesheet とアイコン素材 |
| `scripts/win/` | セットアップ・GUI 起動・CLI 各コマンドのスクリプト |
| `tests/` | 共通層のテスト（モデル不要） |
| `docs/` | ドキュメント一式 |

`.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli <command>` は長いので、
サブコマンド名を受け取る関数を 1 つ作っておくと楽になる
（`Set-Alias` は引数を渡せないため関数にする）。
以降の例では `tts` と書く。

```powershell
function tts { & "$PWD\.venvs\common\Scripts\python.exe" -m ttstoolkit.cli @args }
```

## 5. 使い方

### GUI

最低限の操作は画面からできる。

```powershell
scripts\win\LaunchApp.bat
```

タブは 3 つ。

| タブ | すること |
|---|---|
| Synthesis | テキストを 1 件合成する |
| Voice Design | 文章から声を作り、`input/voices/` に残す |
| Script | キャスト定義と台本からまとめて合成する |

合成は別スレッドで走り、進捗は下のログ欄に流れる。入力値とウィンドウの
位置は終了時に保存され、次の起動で戻る（File > Clear Saved Settings で
既定値に戻せる）。詳しくは [../gui/usage.md](../gui/usage.md)。

### 1 件合成（CLI）

```powershell
tts synth -e qwen -t "こんにちは。" -l ja -O a.wav

# 長文はファイルから
tts synth -e irodori -f script.txt -l ja -O b.wav

# 参照音声から声をクローン
tts synth -e qwen -t "おはようございます。" -l ja `
    -r alice.wav --reference-text "参照音声で話している内容の書き起こし" `
    -O c.wav

# 再現性のためにシードを固定
tts synth -e chatterbox -t "テスト" -l ja --seed 42 -O d.wav
```

`--reference-text` は Qwen3-TTS でのみ使われる。Qwen のクローンは参照音声の書き起こしがある
ときに最も品質が高い（ICL モード）。省略すると話者埋め込みのみのモードに落ちる。
Chatterbox と Irodori は書き起こし不要。

### バッチ合成

モデルを 1 回だけロードして複数件をまとめて処理する。

```powershell
tts batch -e qwen sample.ja.json -o output\batch
```

入力 JSON:

```json
[
  {"id": "line-001", "text": "こんにちは。", "language": "ja"},
  {"id": "line-002", "text": "今日はいい天気ですね。", "language": "ja", "seed": 42}
]
```

各要素で使えるキー: `id`, `text`, `language`, `reference_audio`, `reference_text`,
`seed`, `speed`。`reference_audio` は入力 JSON からの相対パスで解決される。

出力は `outdir/{id}.wav` と `outdir/manifest.json`。manifest には各件の
サンプリングレート、長さ、使用モデル、生成時間が記録される。Remotion など
下流のツールから音声の尺を知りたいときに使える。

1 件失敗しても続行したい場合は `--keep-going` を付ける。

### Python から使う

```python
from ttstoolkit.core.tts_service import TTSService
from ttstoolkit.engine._shared.protocol import SynthesisRequest

result = TTSService().synthesize(
    "irodori",
    SynthesisRequest(
        text="こんにちは。",
        output_path="output/hello.wav",
        language="ja",
        seed=42,
    ),
)
    print(result.sample_rate, result.duration_sec)
```

`with` を抜けるまでモデルは常駐する。複数件を投げるなら 1 つの `with` の中で回す。

## 6. 設定

`python/ttstoolkit/tool_config.py` の `ENGINE_DEFINITIONS` にエンジンの定義が
ある。よく触るのは各エンジンの `options`。

```python
options={
    # VRAM が足りなければ 0.6B に
    "base_model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "dtype": "bfloat16",
    "device": "cuda:0",
    ...
},
```

VRAM 不足、話者の変更、生成パラメータの調整はここで行う。
詳細は各エンジンの手順書を参照。

## 7. トラブルシュート

### `uv sync` が別の Python を使ってしまう

`mise exec --` を付けて実行しているか確認する。`mise.toml` の `[env]` は
mise 経由で実行したときにだけ効く。

### `runner が JSON 以外を stdout に出力しました`

エンジン側のライブラリが標準出力にログを出している。runner は
`ttstoolkit/engine/_shared/runner_base.py` を import した時点で `sys.stdout` を
`stderr` へ退避しているので通常は起きない。自分で runner に `print()` を
足した場合はそれが原因なので、`log()` を使う。

### 日本語が文字化けする

共通層は自分の標準出力を UTF-8 に固定し、エンジンへのパイプも UTF-8 で開いている。
それでも化ける場合はターミナル側のコードページを確認する（`chcp 65001`）。

### 合成がタイムアウトする

環境変数で延ばせる。

| 変数 | 既定 | 用途 |
|---|---:|---|
| `TTS_READY_TIMEOUT` | 1800 | モデルのロード待ち（初回は重みの DL を含む） |
| `TTS_SYNTH_TIMEOUT` | 900 | 1 件あたりの合成 |

### エンジンの詳細ログを見たい

```powershell
tts synth -e qwen -t "テスト" -O x.wav --verbose
```

`--verbose` でエンジンの stderr がそのまま流れる。

### VRAM が足りない（OOM）

- Qwen3-TTS: `tool_config.py` の `base_model` / `custom_voice_model` を 0.6B に変える
- 複数エンジンを同時に動かさない（`with` を抜ければ解放される）
- `nvidia-smi` で他のプロセスが VRAM を使っていないか確認する

## 8. テスト

共通層のプロトコルはモデル無しで検証できる。

```powershell
.\.venvs\common\Scripts\python.exe -m pytest -q
```

`tests/fake_runner.py` が本物のエンジンと同じ規約でふるまうダミーになっていて、
JSONL のやり取り、UTF-8、失敗時の復帰、未対応パラメータの拒否を確認している。
