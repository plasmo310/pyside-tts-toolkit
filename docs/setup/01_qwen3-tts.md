# 01. Qwen3-TTS

日英どちらも品質が高く、ゼロショットクローンと Voice Design の両方を持つ総合第一候補。

| 項目 | 内容 |
|---|---|
| 公式リポジトリ | https://github.com/QwenLM/Qwen3-TTS |
| PyPI | https://pypi.org/project/qwen-tts/ |
| モデル | https://huggingface.co/collections/Qwen/qwen3-tts |
| ライセンス | コード・重みともに Apache-2.0（商用利用可） |
| 対応言語 | 中・英・日・韓・独・仏・露・葡・西・伊 |
| サンプリングレート | 24 kHz |
| このリポジトリでの venv | `.venvs/engine-qwen` |

## 一からの導入手順

### 1. 前提

[00_common.md](00_common.md) の手順 1〜2（mise / uv / Python 3.12）を済ませておく。

### 2. venv を作る

```powershell
cd engine_env\qwen
mise exec -- uv sync
```

`engine_env/qwen/pyproject.toml` が次を行っている。

- `qwen-tts` を入れる（`transformers==4.57.3` をピンする）
- `torch` / `torchaudio` を **cu128 索引から** 入れる

torch を明示している理由は 2 つある。`qwen-tts` 自身は `torchaudio` しか依存に
持たないこと、そして PyPI の `torch` は Windows では CPU 版になることである。
`[tool.uv.sources]` で `https://download.pytorch.org/whl/cu128` を指定して
CUDA 版を取りに行かせている。

### 3. 動作確認

```powershell
cd ..\..\..
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli.synth -e qwen -t "こんにちは。" -l ja -O qwen.wav
```

初回はモデル重み（1.7B で 4GB 前後）のダウンロードが入るため時間がかかる。

## モデルの選び方

Qwen3-TTS はチェックポイントが用途別に分かれている。

| チェックポイント | 用途 | このリポジトリでの使われ方 |
|---|---|---|
| `Qwen/Qwen3-TTS-12Hz-1.7B-Base` | 参照音声からのゼロショットクローン | `-r/--reference` を付けたとき |
| `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` | プリセット話者 | 声の指定が無いとき |
| `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` | 文章から架空の声を設計 | `--voice-design` を付けたとき |
| `Qwen/Qwen3-TTS-12Hz-0.6B-Base` | 上記の軽量版 | VRAM 不足時の代替 |
| `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` | 同上 | 同上 |

runner はリクエストの内容で 3 つを切り替え、**必要になった時点で初めて
ロードする**。全部を常駐させると 12GB 級の VRAM を圧迫するためである。
どれが使われたかは合成結果の `model` 行に出る。

## 参照音声の書き起こし（`--reference-text`）

Qwen のクローンには 2 つのモードがある。

| モード | 必要なもの | 品質 |
|---|---|---|
| ICL モード | 参照音声 **+ その書き起こしテキスト** | 高い |
| x_vector_only モード | 参照音声のみ | 落ちる |

`--reference-text` を渡すと ICL モード、省略すると自動的に x_vector_only モードになる
（stderr に警告が出る）。Chatterbox や Irodori は書き起こし不要なので、
この引数は Qwen 専用である。

```powershell
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli.synth -e qwen `
    -t "おはようございます。" -l ja `
    -r alice.wav `
    --reference-text "こんにちは。音声合成のテストです。" `
    -O clone.wav
```

参照音声は 3 秒程度から機能する。WAV のほか URL や base64 も受け付ける。

## 設定 (`python/ttstoolkit/tool_config.py`)

`ENGINE_DEFINITIONS["qwen"].options` にある。

```python
options={
    "base_model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "custom_voice_model": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "voice_design_model": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "default_speaker": "ono_anna",
    "speakers": {"ja": "ono_anna", "en": "ryan"},
    "dtype": "bfloat16",
    "device": "cuda:0",
    "attn_implementation": "sdpa",
    "max_new_tokens": 2048,
}
```

| キー | 説明 |
|---|---|
| `base_model` / `custom_voice_model` | VRAM が足りなければ `0.6B` 版に変える |
| `speakers` | 言語ごとのプリセット話者。Qwen の話者は言語色が強いので分けている |
| `default_speaker` | `speakers` に無い言語のときの既定 |
| `dtype` | `bfloat16` / `float16` / `float32` |
| `attn_implementation` | 既定は `sdpa`。理由は下記 |
| `max_new_tokens` | 長文で途中で切れる場合に増やす |

使えるプリセット話者は `aiden, dylan, eric, ono_anna, ryan, serena, sohee,
uncle_fu, vivian`。存在しない話者を設定すると、エラーメッセージに一覧が出る。

## VRAM の目安

| GPU | 推奨 |
|---|---|
| 8GB 未満 | 0.6B モデルに変更する |
| 8〜12GB | 1.7B + `bfloat16` が動く（実測: RTX 5070 12GB で 1.7B Base / CustomVoice とも動作） |
| 16GB 以上 | 余裕。長文や複数モデルの常駐も可 |

OOM が出たら `tool_config.py` の 2 つのモデル ID を `0.6B` に書き換えて再実行する。
venv の作り直しは不要。

## トラブルシュート

### `flash-attn is not installed` という警告が出る

無視してよい。flash-attn は Windows でビルドが通らないため、`tool_config.py` では
`attn_implementation = "sdpa"` を既定にしている。sdpa は PyTorch 標準の
高速アテンションで、実用上の問題はない。

### `SoX could not be found!` と出る

無視してよい。`qwen-tts` が依存する Python の `sox` パッケージが、起動時に
sox バイナリを探して警告を出しているだけ。このリポジトリの経路では使われない。
警告は stderr に出るので JSON プロトコルには影響しない。

### 話者が見つからないと言われる

```
Speaker 'Ryan' is not in this model; choose one of:
aiden, dylan, eric, ono_anna, ryan, ...
```

話者 ID は小文字。大文字始まりで書いても解決されるが、一覧に無い名前はエラーになる。

### 生成が途中で切れる

`max_new_tokens` を増やす。それでも切れる長文は、文単位に分割して
`batch` で処理したほうが安定する。

## Voice Design（文章で声を作る）

`--voice-design` を渡すと `Qwen3-TTS-12Hz-1.7B-VoiceDesign` に切り替わり、
「落ち着いた低めの女性の声」のような文章から架空の声を作る。

```powershell
tts synth -e qwen -l ja `
    -t "こんにちは。この声でナレーションを読み上げます。" `
    --voice-design "落ち着いた低めの女性の声。丁寧で穏やかな話し方。" `
    -o input\voices -O narrator_master.wav
```

参照音声（`-r/--reference`）との併用はできない。声の出どころがどちらか 1 つに
決まらないため、runner がエラーにする。

作った声は毎回わずかに揺れるので、**気に入った 1 本を `input/voices/` に残し、
以後はそれを `-r` でクローンする**のが安定した運用になる。こうすると日英で
同じ声を保てるうえ、他のエンジン（Chatterbox など）にも同じマスター音声を
渡せる。手順は [../guide/original-voice.md](../guide/original-voice.md)。

## ライセンス

コード・重みともに **Apache-2.0**。商用利用に制限はない。
ただし参照音声に実在の人物の声を使う場合は、その声素材の権利と本人の同意が別途必要。
