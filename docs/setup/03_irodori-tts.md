# 03. Irodori-TTS v4.1 Small

日本語専用。48kHz で出力し、文章による声の設計（Voice Design）と絵文字による
感情表現に対応する。日本語キャラクターの声を作り込むならこれが第一候補。

| 項目 | 内容 |
|---|---|
| 公式リポジトリ | https://github.com/Aratako/Irodori-TTS |
| モデルカード | https://huggingface.co/Aratako/Irodori-TTS-v4.1-Small |
| OpenAI 互換サーバ | https://github.com/Aratako/Irodori-TTS-Server |
| ライセンス | コード・公式重みともに MIT（商用利用可） |
| 対応言語 | **日本語のみ** |
| サンプリングレート | 48 kHz |
| このリポジトリでの venv | `.venvs/engine-irodori` |

## なぜ他の 2 つと構築方法が違うのか

Irodori-TTS は **PyPI に公開されていない**。さらに依存の `dacvae` も PyPI に無い
（404）。加えて、uv の `[tool.uv.sources]`（CUDA 索引の指定）は依存先プロジェクトに
継承されないため、git 依存として取り込むと PyTorch が CPU 版になってしまう。

そのため**上流リポジトリを clone し、そのリポジトリの依存解決をそのまま使う**のが
唯一確実な経路になる。clone は非パッケージ扱いで仮想環境には入らないので、
`tool_config.py` が clone の場所を runner の検索パス (`python_path`) に足し、
runner はそれを前提に `irodori_tts` を import する。

仮想環境の置き場だけは他のエンジンと揃えて `.venvs/engine-irodori` にしてあり、
clone の中には作られない。

## 一からの導入手順

### 1. 前提

[00_common.md](00_common.md) の手順 1〜2（mise / uv / Python 3.12）と `git`。

### 2. clone する

```powershell
New-Item -ItemType Directory -Force engine_env\irodori\vendor | Out-Null
git clone --depth 1 https://github.com/Aratako/Irodori-TTS.git `
    engine_env\irodori\vendor\Irodori-TTS
```

### 3. Windows + Python 3.12 向けのパッチを当てる

```powershell
.\.venvs\common\Scripts\python.exe engine_env\irodori\patch_vendor.py
```

このスクリプトは clone したリポジトリに次の 3 点を加える（冪等）。

| 変更 | 理由 |
|---|---|
| `.python-version` を `3.10` → `3.12` | プロジェクト全体で 3.12 に統一するため |
| `[tool.uv] override-dependencies = ["sentencepiece>=0.2.0"]` | 下記 |
| `mise.toml` を新規作成 | 仮想環境を clone の中ではなく `.venvs/engine-irodori` に作らせる |

**sentencepiece を上書きする理由**: 上流は `sentencepiece>=0.1.99,<0.2` をピンして
いるが、0.1.99 には Python 3.12 用の Windows wheel が存在しない
（cp36〜cp311 まで）。ソースからビルドするには Visual Studio が必要で、
無いと次のエラーになる。

```
error: Unable to find a compatible Visual Studio installation.
```

一方、Irodori 自身は sentencepiece を直接 import していない。
`irodori_tts/tokenizer.py` は `transformers.AutoTokenizer(use_fast=True)` を使い、
これは Rust 実装の `tokenizers` を通る。sentencepiece は transitive な
フォールバック依存にすぎないため、wheel のある 0.2 系へ上げても動作に影響しない。

> [!note] Python 3.10 を使う選択肢
> パッチを当てず、上流の `.python-version`（3.10）のまま `uv sync` する方法もある。
> 上流が lock したバージョンをそのまま使えるが、このリポジトリの
> 「全体を 3.12 に統一する」方針から外れる。エンジンはサブプロセスで完全に
> 隔離されているので、どちらでも共通層への影響は無い。

### 4. venv を作る

```powershell
cd engine_env\irodori\vendor\Irodori-TTS
mise exec -- uv sync --extra cu128
cd ..\..\..\..
```

`--extra` で PyTorch のバックエンドを選ぶ。排他なのでどれか 1 つだけ。

| extra | 用途 |
|---|---|
| `cu128` | NVIDIA CUDA 12.8（Windows / Linux） |
| `rocm` | AMD ROCm（Linux） |
| `xpu` | Intel |
| `cpu` | GPU なし |

### 5. 動作確認

```powershell
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli synth -e irodori -t "こんにちは。" -l ja -O ir.wav
```

初回はチェックポイント（v4.1 Small、約 0.8B）とコーデック
（`Aratako/Semantic-DACVAE-Japanese-32dim`）のダウンロードが入る。

## 声のクローン

参照音声を渡すだけ。書き起こしは不要。

```powershell
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli synth -e irodori `
    -t "参照音声からクローンした声で話しています。" -l ja `
    -r alice.wav -O ir_clone.wav
```

参照音声の条件:

- **30 秒以上を推奨。** 短い 1 クリップより長いほうが安定する
- v4 Small の上限は合計 120 秒
- ノイズ・BGM の無いきれいな音声を使う

参照音声を渡さない場合は `no_ref` モードになり、モデルが任意の声で読み上げる。

## 話速の指定

3 エンジンのうち Irodori だけが `--speed` に対応している。

```powershell
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli synth -e irodori -t "テスト" -l ja --speed 0.8 -O slow.wav
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli synth -e irodori -t "テスト" -l ja --speed 1.3 -O fast.wav
```

内部では Irodori の `duration_scale` に逆数を渡している（`duration_scale` は
大きいほど長くなるため）。実測では `--speed 0.8` で 4.28 秒、`--speed 1.3` で
2.64 秒と期待どおりに効いた。

Qwen と Chatterbox に `--speed` を渡すと、黙殺されずにエラーになる。

## 設定 (`python/ttstoolkit/tool_config.py`)

`ENGINE_DEFINITIONS["irodori"].options` にある。

```python
options={
    "hf_checkpoint": "Aratako/Irodori-TTS-v4.1-Small",
    "codec_repo": "Aratako/Semantic-DACVAE-Japanese-32dim",
    "model_precision": "fp32",
    "num_steps": 24,
    "cfg_guidance_mode": "independent",
    "cfg_scale_text": 3.0,
    "cfg_scale_caption": 3.0,
    "cfg_scale_speaker": 5.0,
}
```

| キー | 説明 |
|---|---|
| `hf_checkpoint` | 低メモリ向けに INT8 / INT4 / FP8 版もある（モデルカード参照） |
| `model_precision` | `fp32` / `bf16` など。VRAM を減らしたいときに変える |
| `num_steps` | Flow Matching のステップ数。下げると速く、上げると高品質 |
| `cfg_scale_text` | テキストへの忠実さ |
| `cfg_scale_speaker` | 参照音声への忠実さ |
| `cfg_scale_caption` | Voice Design の指示への忠実さ |

## Voice Design（文章で声を作る）

`--voice-design` に日本語で声と話し方を書くと、その通りの声を作る。
Irodori の最大の特徴で、実在の人物に依存しないオリジナルキャラクターを作れる。

```powershell
tts synth -e irodori -l ja `
    -t "こんにちは。この声でナレーションを読み上げます。" `
    --voice-design "落ち着いた低めの女性の声。丁寧で穏やかな話し方。" `
    -o input\voices -O narrator_master.wav
```

Qwen と違い、Irodori は**参照音声と併用できる**。その場合は声質が参照音声、
話し方が `--voice-design` になる。

内部では Irodori の `caption` に渡している。作り込みの手順は
[../guide/original-voice.md](../guide/original-voice.md) を参照。

### 絵文字による感情・非言語表現

本文に絵文字を入れると、笑い・ため息・咳などを表現する。

```powershell
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli synth -e irodori `
    -t "あははっ🤭、それ本当に言ってるの？…😮‍💨まぁ、君らしいけどね。" `
    -l ja -O emotion.wav
```

## VRAM の目安

約 0.8B。`model_precision = "fp32"` が既定なので、Qwen 1.7B の bfloat16 と
同程度のメモリを使う。

| GPU | 推奨 |
|---|---|
| 8GB 未満 | INT8 / INT4 量子化版のチェックポイントを使う |
| 8〜12GB | fp32 のまま動く（実測: RTX 5070 12GB で動作） |
| 16GB 以上 | 余裕 |

## 英語版を作りたい場合

Irodori は**英語を生成できない**。`-l en` を渡すと共通層で
即座にエラーになる（モデルはロードされない）。

日英両方が要るなら二段構成にする。

1. Irodori の Voice Design で日本語のキャラクター声を作る
2. 30〜60 秒の良質な音声を「マスター音声」として保存する
3. 日本語版は Irodori で生成
4. 英語版はそのマスター音声を `-r/--reference` に渡して Qwen または Chatterbox で生成

```powershell
# 日本語（Irodori）
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli synth -e irodori -t "こんにちは。" -l ja -O ja.wav

# 英語（マスター音声をクローンして Qwen で）
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli synth -e qwen -t "Hello." -l en `
    -r master.wav --reference-text "マスター音声の書き起こし" -O en.wav
```

日英で音響モデルが違うため、同一人物に聞こえるかは必ず聴感で確認すること。

## トラブルシュート

### `Unable to find a compatible Visual Studio installation.`

`patch_vendor.py` を当てていない。手順 3 を実行してから `uv sync` し直す。

### `No module named 'irodori_tts'`

clone が無いか、場所が違う。`engine_env/irodori/vendor/Irodori-TTS/irodori_tts`
が存在するか確認する。`tool_config.py` がこのパスを runner の検索パスに
足している。

### `No interpreter found for Python 3.10`

`patch_vendor.py` が `.python-version` を 3.12 に書き換える前に `uv` を
実行している。手順 3 を先に済ませる。

### `speaker-conditioned checkpoints require one reference option`

参照音声が必要なチェックポイントに `no_ref` で投げている。runner は参照音声が
無いとき自動で `no_ref=True` を立てるので通常は起きないが、別の
チェックポイントに差し替えた場合に出ることがある。`-r/--reference` を渡す。

## OpenAI 互換サーバという選択肢

公式に [Irodori-TTS-Server](https://github.com/Aratako/Irodori-TTS-Server) があり、
`POST /v1/audio/speech` の OpenAI 互換 API、長文分割、複数の音声形式に対応している。

```bash
curl http://localhost:8088/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model":"irodori-tts","input":"こんにちは。","voice":"sample","response_format":"wav"}' \
  --output speech.wav
```

このリポジトリはサブプロセス方式を採っているため使っていないが、
常駐サーバが欲しくなったときの有力な選択肢になる。`TTSEngine`
（`python/ttstoolkit/core/_internal/engine_process.py`）を実装した
HTTP バックエンドを足し、
`tool_config.py` に分岐を 1 つ増やせば、呼び出し側のコードを変えずに
差し替えられる設計にしてある。

## ライセンス

コード・公式重みともに **MIT**。商用利用に制限はない。
ただし参照音声の権利は別途確認が必要。
