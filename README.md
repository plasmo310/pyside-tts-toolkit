# TTS Toolkit

ローカルで動く 3 つの音声合成モデルを、**同じ呼び方**で使うためのツールです。
GUI と CLI の 2 つの入口があり、どちらからも同じことができます。

| モデル | 得意なこと |
|---|---|
| [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) 1.7B | 日英とも高品質。3 秒の参照音声から声を複製できる |
| [Chatterbox](https://github.com/resemble-ai/chatterbox) Multilingual V3 | 0.5B と軽く、23 言語に対応 |
| [Irodori-TTS](https://github.com/Aratako/Irodori-TTS) v4.1 Small | 日本語専用・48kHz。文章で声を作り込める |

![Synthesis](docs/readme/01_gui_synthesis.png)

## できること

- テキストから音声を作る（1 件 / JSON でまとめて / キャラクター台本から）
- 参照音声から声を複製する（ゼロショットクローン）
- **文章で声を設計する**（「落ち着いた低めの女性の声」）
- 台詞ごとの wav と、尺・並び順を記録した `manifest.json` を書き出す

## 使い始める

### 1. セットアップ

前提は **mise / uv / git**、それと NVIDIA GPU（CUDA 12.8 対応ドライバ）。
GPU が無くても動きますが、量産に使える速度ではありません。

```powershell
git clone <このリポジトリ>
cd python-tts-sample
pwsh scripts\win\setup_engines.ps1
```

これで Python 3.12 と 4 つの仮想環境（共通層 + エンジン 3 つ）ができます。
ダウンロードは 10GB を超え、初回は数十分かかります。
詳しい手順とトラブルシュートは [docs/setup/](docs/setup/) にあります。

```powershell
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli.doctor
```

3 エンジンとも `CUDA ok` と出れば準備完了です。

### 2. GUI で試す

```powershell
scripts\win\LaunchApp.bat
```

タブは 3 つ。Synthesis（テキストから合成）、Voice Design（声を作る）、
Script（台本からまとめて合成）。使い方は
[docs/gui/usage.md](docs/gui/usage.md)。

### 3. CLI で使う

```powershell
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli.synth -e irodori -t "こんにちは。"
```

毎回書くには長いので、関数を 1 つ作っておくと楽です。

```powershell
function tts {
    $exe = "$PWD\.venvs\common\Scripts\python.exe"
    & $exe -m "ttstoolkit.cli.$($args[0])" @($args | Select-Object -Skip 1)
}
```

```powershell
# 1 件合成
tts synth -e qwen -t "こんにちは。" -l ja -O hello.wav

# 参照音声から声を複製
tts synth -e qwen -t "おはようございます。" -l ja -r master.wav

# 文章で声を作る
tts synth -e irodori -t "この声でお送りします。" `
    --voice-design "落ち着いた低めの女性の声。丁寧で穏やかな話し方。"

# JSON をまとめて
tts batch -e qwen sample.ja.json -o output\batch

# キャラクター台本から
tts script ep01.ja.txt -c cast.toml -o output\ep01
```

コマンドごとの詳細は [docs/cli/](docs/cli/)。

## キャラクター台本

声の定義は一度書けば使い回せます。毎回書くのは台詞だけです。

`input/script/cast.toml`

```toml
[voices."霊夢"]
engine = "irodori"
voice_design = "落ち着いた少女の声。淡々としていて、少し呆れたような話し方。"
language = "ja"
seed = 42
```

`input/script/ep01.ja.txt`

```
霊夢: 今日はいい天気ね。
魔理沙: そうだな、絶好の弾幕日和だぜ！
霊夢[speed=0.9]: ……また変なこと言ってる。
```

```powershell
tts script ep01.ja.txt -o output\ep01
```

台詞ごとの wav と `manifest.json`（各台詞の尺と先頭からの秒数）が出ます。
書き方は [docs/guide/script.md](docs/guide/script.md)。

## オリジナルの声を作る

実在の人物に頼らずにキャラクターの声を作れます。文章で声を説明して
何本か出し、**気に入った 1 本を `input/voices/` に残して以後はそれを
複製する**のが安定した運用です。

```powershell
# 1. 文章から声を作る（何度か試す）
tts synth -e irodori -l ja --seed 42 `
    -t "こんにちは。この声でナレーションを読み上げます。" `
    --voice-design "20 代女性のはきはきした明るい声。少し早口。" `
    -o input\voices -O master.wav

# 2. 以後はそれを参照音声にする
tts synth -e irodori -l ja -r master.wav -t "今日も一日がんばりましょう。"
```

GUI の Voice Design タブが同じ流れをなぞれます。
コツは [docs/guide/original-voice.md](docs/guide/original-voice.md)。

## 何が使えるか

```powershell
tts engines
```

| | 日本語 | 英語 | 声クローン | Voice Design | 話速 | シード | レート |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---:|
| qwen | ○ | ○ | ○ | ○ | × | ○ | 24 kHz |
| chatterbox | ○ | ○ | ○ | × | × | ○ | 24 kHz |
| irodori | ○ | **×** | ○ | ○ | ○ | ○ | 48 kHz |

**対応していない指定は黙って無視されず、エラーになります。** しかもエンジンを
起動する前に判定するので、待たされません。

```powershell
tts synth -e irodori -t "Hello." -l en
# [error] Engine 'irodori' does not support language 'en' (supported: ja)
```

## 構成

```
python/ttstoolkit/   ツール本体
  cli/               コマンドラインの入口
  gui/               PySide6 の画面
  engine/            CLI / GUI 共用の処理本体
    runners/         各モデルの仮想環境で動く小さなプログラム
engine_env/          各エンジンの仮想環境を作るための定義
.venvs/              仮想環境の実体
input/               voices（参照音声）/ script（台本）/ batch（JSON）
output/              生成した wav
resources/ui/        stylesheet.qss
scripts/win/         セットアップと GUI 起動
docs/                ドキュメント
tests/               共通層のテスト（モデル不要）
```

3 つのモデルは依存ライブラリのピンが互いに排他的で、1 つの仮想環境には
同居できません。そのため共通層はモデルを直接 import せず、エンジンごとの
仮想環境にある runner をサブプロセスとして起動し、標準入出力の JSON で
やり取りしています。モデルはロードしたまま常駐するので、まとめて合成する
ときのロード時間は最初の 1 回だけです。

なぜそうなったかは
[docs/development/architecture.md](docs/development/architecture.md)。

## Python から使う

```python
from ttstoolkit.engine.registry import create_engine
from ttstoolkit.engine.types import SynthesisRequest

with create_engine("irodori") as engine:
    result = engine.synthesize(
        SynthesisRequest(
            text="こんにちは。",
            output_path="output/hello.wav",
            language="ja",
            seed=42,
        )
    )
    print(result.sample_rate, result.duration_sec)
```

`with` を抜けるまでモデルは常駐します。複数件を投げるなら 1 つの `with` の
中で回してください。

## ドキュメント

| 目的 | 場所 |
|---|---|
| 導入 | [docs/setup/](docs/setup/) |
| CLI | [docs/cli/](docs/cli/) |
| GUI | [docs/gui/usage.md](docs/gui/usage.md) |
| 台本・オリジナルボイス | [docs/guide/](docs/guide/) |
| 設計と実装 | [docs/development/](docs/development/) / [docs/instructions/](docs/instructions/) |
| 一覧 | [docs/README.md](docs/README.md) |

## ライセンス

3 モデルともローカル生成は無料・無制限で、商用利用も可能です。

| モデル | コード | 重み |
|---|---|---|
| Qwen3-TTS | Apache-2.0 | Apache-2.0 |
| Chatterbox | MIT | MIT（生成音声に PerTh 電子透かしが入る） |
| Irodori-TTS | MIT | MIT |

ただし**参照音声（声素材）の権利は別**です。実在の人物の声を複製する場合は、
本人の同意と利用範囲の確認が必要になります。
