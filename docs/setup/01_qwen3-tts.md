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
cd python\engines\qwen
mise exec -- uv sync
```

`engines/qwen/pyproject.toml` が次を行っている。

- `qwen-tts` を入れる（`transformers==4.57.3` をピンする）
- `torch` / `torchaudio` を **cu128 索引から** 入れる

torch を明示している理由は 2 つある。`qwen-tts` 自身は `torchaudio` しか依存に
持たないこと、そして PyPI の `torch` は Windows では CPU 版になることである。
`[tool.uv.sources]` で `https://download.pytorch.org/whl/cu128` を指定して
CUDA 版を取りに行かせている。

### 3. 動作確認

```powershell
cd ..\..\..
.\.venvs\common\Scripts\python.exe -m tts_sample synth --engine qwen --text "こんにちは。" --lang ja --out outputs\qwen.wav
```

初回はモデル重み（1.7B で 4GB 前後）のダウンロードが入るため時間がかかる。

## モデルの選び方

Qwen3-TTS はチェックポイントが用途別に分かれている。

| チェックポイント | 用途 | このリポジトリでの使われ方 |
|---|---|---|
| `Qwen/Qwen3-TTS-12Hz-1.7B-Base` | 参照音声からのゼロショットクローン | `--ref` を付けたとき |
| `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` | プリセット話者 + 自然言語の演技指示 | `--ref` が無いとき |
| `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` | 文章から架空の声を設計 | 既定では未使用（後述） |
| `Qwen/Qwen3-TTS-12Hz-0.6B-Base` | 上記の軽量版 | VRAM 不足時の代替 |
| `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` | 同上 | 同上 |

runner はリクエストに参照音声があるかどうかで Base と CustomVoice を切り替え、
**必要になった時点で初めてロードする**。両方を常駐させると 12GB 級の VRAM を
圧迫するためである。どちらが使われたかは合成結果の `model=` 行に出る。

## 参照音声の書き起こし（`--ref-text`）

Qwen のクローンには 2 つのモードがある。

| モード | 必要なもの | 品質 |
|---|---|---|
| ICL モード | 参照音声 **+ その書き起こしテキスト** | 高い |
| x_vector_only モード | 参照音声のみ | 落ちる |

`--ref-text` を渡すと ICL モード、省略すると自動的に x_vector_only モードになる
（stderr に警告が出る）。Chatterbox や Irodori は書き起こし不要なので、
この引数は Qwen 専用である。

```powershell
.\.venvs\common\Scripts\python.exe -m tts_sample synth --engine qwen `
    --text "おはようございます。" --lang ja `
    --ref samples\ref\alice.wav `
    --ref-text "こんにちは。音声合成のテストです。" `
    --out outputs\clone.wav
```

参照音声は 3 秒程度から機能する。WAV のほか URL や base64 も受け付ける。

## 設定 (`python/engines.toml`)

```toml
[qwen.options]
base_model = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
custom_voice_model = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
default_speaker = "ono_anna"
dtype = "bfloat16"
device = "cuda:0"
attn_implementation = "sdpa"
max_new_tokens = 2048

[qwen.options.speakers]
ja = "ono_anna"
en = "ryan"
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

OOM が出たら `engines.toml` の 2 つのモデル ID を `0.6B` に書き換えて再実行する。
venv の作り直しは不要。

## トラブルシュート

### `flash-attn is not installed` という警告が出る

無視してよい。flash-attn は Windows でビルドが通らないため、`engines.toml` では
`attn_implementation = "sdpa"` を既定にしている。sdpa は PyTorch 標準の
高速アテンションで、実用上の問題はない。

### `SoX could not be found!` と出る

無視してよい。`qwen-tts` が依存する Python の `sox` パッケージが、起動時に
sox バイナリを探して警告を出しているだけ。このリポジトリの経路では使われない。
警告は stderr に出るので JSON プロトコルには影響しない。

### 話者が見つからないと言われる

```
話者 'Ryan' はこのモデルにありません。engines.toml の [qwen.options.speakers] を
次から選んでください: aiden, dylan, eric, ono_anna, ryan, ...
```

話者 ID は小文字。大文字始まりで書いても解決されるが、一覧に無い名前はエラーになる。

### 生成が途中で切れる

`max_new_tokens` を増やす。それでも切れる長文は、文単位に分割して
`batch` で処理したほうが安定する。

## Voice Design を使いたい場合

`Qwen3-TTS-12Hz-1.7B-VoiceDesign` は「落ち着いた低めの女性の声」のような
文章から架空の声を作れる。現在の共通インターフェース（text / language /
reference_audio / seed / speed）には声の設計を指示する項目が無いため、
既定では使っていない。

使うなら次の流れが実用的である。

1. VoiceDesign モデルで理想の声のサンプルを 1 本作る
2. その wav を「キャラクターのマスター音声」として保存する
3. 以後は `--ref` にそれを渡して Base モデルでクローンする

こうすると日英で同じ声を保てるうえ、他のエンジン（Chatterbox など）にも
同じマスター音声を渡せる。

## ライセンス

コード・重みともに **Apache-2.0**。商用利用に制限はない。
ただし参照音声に実在の人物の声を使う場合は、その声素材の権利と本人の同意が別途必要。
