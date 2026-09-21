# 02. Chatterbox Multilingual V3

0.5B と小さく、導入が最も簡単。最初に動作確認するならこれが一番早い。

| 項目 | 内容 |
|---|---|
| 公式リポジトリ | https://github.com/resemble-ai/chatterbox |
| PyPI | https://pypi.org/project/chatterbox-tts/ |
| モデル | https://huggingface.co/ResembleAI/chatterbox |
| ライセンス | MIT（商用利用可） |
| 対応言語 | 23 言語（日本語・英語を含む） |
| サンプリングレート | 24 kHz |
| このリポジトリでの venv | `.venvs/engine-chatterbox` |

## 一からの導入手順

### 1. 前提

[00_common.md](00_common.md) の手順 1〜2（mise / uv / Python 3.12）を済ませておく。
`git` も必要（後述の理由で GitHub からインストールするため）。

### 2. venv を作る

```powershell
cd python\engines\chatterbox
mise exec -- uv sync
```

### 3. 動作確認

```powershell
cd ..\..\..
.\.venvs\common\Scripts\python.exe -m tts_sample synth --engine chatterbox --text "こんにちは。" --lang ja --out outputs\cb.wav
```

初回はモデル重みのダウンロードが入る。

## この環境で入れている調整

`engines/chatterbox/pyproject.toml` は公式の指示（`pip install chatterbox-tts`）
そのままではなく、2 点の調整を入れている。どちらも理由がある。

### 調整 1: PyPI ではなく GitHub から入れる

PyPI の `chatterbox-tts` 0.1.7 は **多言語 V2** のチェックポイント
（`t3_mtl23ls_v2.safetensors`）しか読み込まず、`from_pretrained` に
`t3_model` 引数が無い。

```python
# PyPI 版 0.1.7
from_pretrained(device) -> ChatterboxMultilingualTTS

# GitHub master
from_pretrained(device, t3_model=None) -> ChatterboxMultilingualTTS
```

V3（話者類似性の向上、幻覚・反復の低減）は GitHub の master にしか入っていない。
そのため commit を固定して git から入れている。

```toml
dependencies = [
    "chatterbox-tts @ git+https://github.com/resemble-ai/chatterbox.git@5de7a54aa4e5e2baadb0182dde554908b48b85c2",
    "soundfile>=0.12",
]
```

V2 で構わない場合は `"chatterbox-tts==0.1.7"` に戻し、`engines.toml` の
`t3_model` を `"v2"` にすればよい（git が不要になる）。

### 調整 2: torch のピンを上書きする

`chatterbox-tts` は `torch==2.6.0` / `torchaudio==2.6.0` をピンしている。
しかし **torch 2.6.0 のビルドは cu124 / cu126 までで、`sm_120` カーネルを含まない**。
Blackwell 世代（RTX 50 系）では実行時に次のエラーになる。

```
CUDA error: no kernel image is available for execution on the device
```

`sm_120` を含む最初の系列は `2.7.0+cu128` なので、そこまで引き上げている。

```toml
[tool.uv]
override-dependencies = [
    "torch==2.7.1",
    "torchaudio==2.7.1",
]

[tool.uv.sources]
torch = [{ index = "pytorch-cu128" }]
torchaudio = [{ index = "pytorch-cu128" }]

[[tool.uv.index]]
name = "pytorch-cu128"
url = "https://download.pytorch.org/whl/cu128"
explicit = true
```

`transformers==5.2.0` / `diffusers==0.29.0` / `safetensors==0.5.3` のピンは
モデルコードが依存しているため触っていない。

> [!note] RTX 40 系以前を使う場合
> `sm_120` を必要としないので、この上書きは不要。ただし上書きしたままでも
> 2.7.1+cu128 は sm_50〜sm_120 をすべて含むため問題なく動く。

### 検証結果（RTX 5070 / 12GB）

```
torch 2.7.1+cu128
arch_list ['sm_50','sm_60','sm_61','sm_70','sm_75','sm_80','sm_86','sm_90','sm_100','sm_120']
CUDA available: True
```

合成も正常に動作することを確認済み。`tts doctor` で同じ内容を確認できる。

## 設定 (`python/engines.toml`)

```toml
[chatterbox.options]
t3_model = "v3"
device = "cuda"
```

runner 側では次も読む（`engines.toml` に書けば有効になる）。

| キー | 既定 | 説明 |
|---|---:|---|
| `exaggeration` | 0.5 | 表現の強調。上げると感情的になるが不安定になりやすい |
| `cfg_weight` | 0.5 | テキストへの忠実さ。上げると読み飛ばしが減る |
| `temperature` | 0.8 | 下げると安定、上げると多様 |

## 声のクローン

参照音声を渡すだけでよい。書き起こしは不要。

```powershell
.\.venvs\common\Scripts\python.exe -m tts_sample synth --engine chatterbox `
    --text "参照音声からクローンした声で話しています。" --lang ja `
    --ref samples\ref\alice.wav --seed 7 `
    --out outputs\cb_clone.wav
```

## VRAM の目安

0.5B と小さいため、本リポジトリの 3 エンジンで最も軽い。

| GPU | 可否 |
|---|---|
| 4〜6GB | 動く可能性が高い |
| 8GB 以上 | 余裕 |
| CPU のみ | 動くが非常に遅い |

## 電子透かしについて

Chatterbox が生成した音声には **PerTh 電子透かし**が埋め込まれる。
聴感上は分からないが、出力が Chatterbox 由来であることを機械的に判定できる。
MIT ライセンスで商用利用は可能だが、この仕様は把握しておくとよい。

## トラブルシュート

### `no kernel image is available for execution on the device`

torch の上書きが効いていない。`tts doctor` で torch のバージョンを確認する。
`2.6.0` と出ていたら venv を作り直す。

```powershell
cd python\engines\chatterbox
Remove-Item -Recurse -Force .venv
mise exec -- uv sync
```

### `torch.backends.cuda.sdp_kernel() is deprecated` という警告

無視してよい。chatterbox が古い API を使っているだけで、動作に影響はない。
警告は stderr に出るので JSON プロトコルには影響しない。

### 日本語が不自然、読み飛ばしがある

`cfg_weight` を上げる（0.7 程度）と読み飛ばしが減る。
それでも安定しない場合は Irodori-TTS のほうが日本語は得意である。

### git からのインストールに失敗する

`resemble-perth` も git から入るため、プロキシ環境では両方の git アクセスが必要。
どうしても通らない場合は PyPI 版（V2）にフォールバックできる。

## ライセンス

コード・重みともに **MIT**。商用利用に制限はない。
ただし参照音声の権利は別途確認が必要。
