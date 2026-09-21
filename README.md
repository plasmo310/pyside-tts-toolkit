# python-tts-sample

ローカルで動く 3 つの TTS モデルを、**同じコマンド・同じ引数**で呼べるようにしたサンプル。

| エンジン名 | モデル | 特徴 |
|---|---|---|
| `qwen` | Qwen3-TTS 1.7B | 日英とも高品質。総合第一候補 |
| `chatterbox` | Chatterbox Multilingual V3 | 0.5B と軽い。導入が最も簡単 |
| `irodori` | Irodori-TTS v4.1 Small | 日本語専用・48kHz。キャラクター声に強い |

3 つとも商用利用可（Apache-2.0 / MIT）、ローカル生成なので従量課金なし。

---

## 目次

- [セットアップ](#セットアップ)
- [使い方](#使い方)
  - [1 件だけ合成する](#1-件だけ合成する)
  - [オリジナルの声を作る](#オリジナルの声を作る)
  - [声をクローンする](#声をクローンする)
  - [キャラクター台本から作る](#キャラクター台本から作る)
  - [まとめて合成する（バッチ）](#まとめて合成するバッチ)
  - [Python から呼ぶ](#python-から呼ぶ)
- [エンジンの選び方](#エンジンの選び方)
- [設定を変える](#設定を変える)
- [仕組み](#仕組み)
- [困ったときは](#困ったときは)

---

## セットアップ

必要なもの: **mise** / **uv** / **git** / NVIDIA GPU（CUDA 12.8 以降のドライバ、VRAM 8GB 以上推奨）。

```powershell
git clone <このリポジトリ>
cd python-tts-sample
pwsh scripts\setup_engines.ps1
```

これで Python 3.12 の用意から 3 エンジン分の仮想環境構築までが終わる。

> [!important] 所要時間とディスク
> 仮想環境 3 つが CUDA 版 PyTorch を個別に持つため、ダウンロードは 10GB を超える。
> さらに初回の合成時にモデル重み（合計 10GB 前後）を取得する。
> 全体で 1 時間以上かかることがある。空きディスクは 30GB 以上見ておく。

うまくいったか確認する。以降のコマンドはすべて**リポジトリのルート**で実行する。

```powershell
.\.venvs\common\Scripts\python.exe -m tts_sample doctor
```

```
== エンジン ==

[chatterbox] ResembleAI/chatterbox (multilingual v3)
  torch 2.7.1+cu128 / CUDA OK / NVIDIA GeForce RTX 5070

[irodori] Aratako/Irodori-TTS-v4.1-Small
  torch 2.10.0+cu128 / CUDA OK / NVIDIA GeForce RTX 5070

[qwen] Qwen/Qwen3-TTS-12Hz-1.7B-Base
  torch 2.11.0+cu128 / CUDA OK / NVIDIA GeForce RTX 5070
```

`CUDA OK` が 3 つ出れば準備完了。詳しい手順・モデルごとの導入方法は
**[docs/setup/](docs/setup/)**、使い方の解説は **[docs/guide/](docs/guide/)** にある。

`.\.venvs\common\Scripts\python.exe -m tts_sample` は長いので alias を張ると楽になる。
以降の例では `tts` と書く。

```powershell
# 例: このシェルだけの短縮（リポジトリのルートで）
function tts { & "$PWD\.venvs\common\Scripts\python.exe" -m tts_sample @args }
```

### ディレクトリの役割

| パス | 内容 |
|---|---|
| `python/` | Python のコードだけ。共通層・各エンジンの runner・テスト |
| `.venvs/` | 仮想環境をまとめた場所（git 管理外）。`common` と `engine-*` |
| `docs/setup/` | 導入手順（共通 + モデル別） |
| `docs/guide/` | 台本とオリジナルボイスの解説 |
| `docs/html/` | ブラウザで読む早見表・概要（そのまま開ける） |
| `docs/implements/` | 実装の解説（設計の根拠・コードの読み方） |
| `scripts/` | セットアップ用の PowerShell スクリプト |
| `samples/` | バッチ入力と台本の例（`samples/script/` にキャスト定義と台本） |
| `voices/` | マスター音声の置き場（git 管理外） |
| `outputs/` | 生成した wav の置き場（git 管理外） |

仮想環境は各プロジェクトの中ではなく `.venvs/` に集約している。

```
.venvs/
  common             共通層。tts コマンド。torch なし
  engine-qwen        Qwen3-TTS       transformers 4.57.3
  engine-chatterbox  Chatterbox      transformers 5.2.0
  engine-irodori     Irodori-TTS     transformers 5.12.x
```

---

## 使い方

### 1 件だけ合成する

```powershell
tts synth --engine chatterbox --text "こんにちは。" --lang ja --out outputs\hello.wav
```

```
[chatterbox] D:\...\outputs\hello.wav
  model=ResembleAI/chatterbox multilingual v3
  24000 Hz / 2.52 秒 / 生成 4.22 秒
```

長い台本はファイルから読ませる。

```powershell
tts synth --engine irodori --text-file script.txt --lang ja --out outputs\narration.wav
```

同じ結果を再現したいときはシードを固定する。

```powershell
tts synth --engine qwen --text "こんにちは。" --lang ja --seed 42 --out outputs\a.wav
```

Irodori だけ話速を変えられる（`1.0` が等速、小さいほどゆっくり）。

```powershell
tts synth --engine irodori --text "ゆっくり話します。" --lang ja --speed 0.8 --out outputs\slow.wav
```

#### `synth` の引数

| 引数 | 必須 | 説明 |
|---|:---:|---|
| `--engine` | ○ | `qwen` / `chatterbox` / `irodori` |
| `--text` または `--text-file` | ○ | 合成するテキスト。ファイルは UTF-8 |
| `--out` | ○ | 出力 wav のパス |
| `--lang` | | `ja` / `en`。省略するとエンジンの既定 |
| `--ref` | | 参照音声 wav（声のクローン） |
| `--ref-text` | | 参照音声の書き起こし。**Qwen のみ使う** |
| `--seed` | | 乱数シード |
| `--speed` | | 話速。**Irodori のみ対応** |
| `--verbose` | | エンジンのログをそのまま表示する |

### オリジナルの声を作る

`--voice-design` に日本語で声の特徴を書くと、実在の人物に依存しない
キャラクターの声を作れる（`irodori` と `qwen` が対応）。

```powershell
tts synth --engine irodori --seed 42 `
    --voice-design "落ち着いた低めの女性の声。丁寧で穏やかな話し方。" `
    --text "この声でどうでしょうか。" --lang ja --out voices\try01.wav
```

Voice Design は生成のたびに声が揺れるので、気に入ったら**長めの台詞で
1 本だけ作ってマスター音声として固定し、以後はそれをクローンする**。

```powershell
# ② マスター音声を作る（30 秒以上あると安定する）
tts synth --engine irodori --seed 42 `
    --voice-design "落ち着いた低めの女性の声。丁寧で穏やかな話し方。" `
    --text-file voices\master_script.txt --lang ja --out voices\reimu_master.wav

# ③ 以後はクローンして使う
tts synth --engine irodori --ref voices\reimu_master.wav `
    --text "マスター音声から再現した声です。" --lang ja --out outputs\a.wav
```

指示文の書き方、英語版への持ち込み方、キャラクターを増やす流れは
**[docs/guide/original-voice.md](docs/guide/original-voice.md)** に詳しく書いてある。

### 声をクローンする

参照音声を `--ref` で渡すだけ。3 エンジンとも対応している。

```powershell
tts synth --engine chatterbox `
    --text "参照音声からクローンした声で話しています。" --lang ja `
    --ref samples\ref\alice.wav `
    --out outputs\clone.wav
```

**Qwen を使うときだけ `--ref-text` も渡す。** Qwen のクローンは参照音声の
書き起こしがあると品質が上がる（ICL モード）。省略すると話者埋め込みだけを使う
モードに自動で落ちるが、そのぶん似なくなる。

```powershell
tts synth --engine qwen `
    --text "おはようございます。" --lang ja `
    --ref samples\ref\alice.wav `
    --ref-text "こんにちは。音声合成のテストです。" `
    --out outputs\clone.wav
```

参照音声の目安:

| エンジン | 長さ | 書き起こし |
|---|---|---|
| qwen | 3 秒〜 | あると品質が上がる |
| chatterbox | 10 秒前後 | 不要 |
| irodori | 30 秒以上を推奨（上限 120 秒） | 不要 |

いずれもノイズ・BGM の無いきれいな音声を使う。

### キャラクター台本から作る

複数のキャラクターが会話する台本を書いて、台詞ごとの wav をまとめて生成する。
**キャラクターの声の定義（`cast.toml`）と台詞（`script.txt`）を分ける**ので、
台本側には「誰が」「何を」しか書かない。

`samples/script/cast.toml`:

```toml
[voices."霊夢"]
engine = "irodori"
voice_design = "落ち着いた少女の声。淡々としていて、少し呆れたような話し方。"
language = "ja"
seed = 42

[voices."魔理沙"]
engine = "irodori"
reference_audio = "../../voices/marisa_master.wav"
language = "ja"
```

`samples/script/ep01.ja.txt`:

```
# ■ オープニング

霊夢: 今日はいい天気ね。
魔理沙: そうだな、絶好の弾幕日和だぜ！

霊夢[speed=0.9]: ……また変なこと言ってる。
魔理沙[id=punchline]: やった、ごちそうさま！

霊夢: 長い台詞は
  インデントした行で続けられる。
```

```powershell
tts script --cast samples\script\cast.toml --script samples\script\ep01.ja.txt --outdir outputs\ep01
```

```
7 台詞 / 3 キャラクター / エンジン: qwen, irodori

--- qwen (1 台詞) ---
[001] ナレーター  1.84秒  ある晴れた日のこと。

--- irodori (6 台詞) ---
[002] 霊夢  2.64秒  今日はいい天気ね。
[003] 魔理沙  3.84秒  そうだな、絶好の弾幕日和だぜ！
...

7/7 台詞を生成。合計 23.8 秒
manifest: D:\...\outputs\ep01\manifest.json
```

出力は `001-霊夢.wav` のように台本順の連番。manifest には各台詞の
**先頭からの累積オフセット（`start_sec`）**が入るので、Remotion の
`<Sequence from={...}>` にそのまま使える。

台詞ごとにプロセスを立て直さず**エンジン単位でまとめて処理**するので、
モデルの読み込みは 1 エンジンにつき 1 回で済む。

台本の文法、行オプション、英語版の作り方は
**[docs/guide/script.md](docs/guide/script.md)** を参照。

### まとめて合成する（バッチ）

台本を使わず、機械的に生成した JSON から流したいときはこちら。
モデルを 1 回だけ読み込んで全件を処理する。

```powershell
tts batch --engine qwen --input samples\input.ja.json --outdir outputs\batch
```

```
[1/3] line-001 line-001.wav (3.83 秒)
[2/3] line-002 line-002.wav (3.41 秒)
[3/3] line-003 line-003.wav (4.42 秒)

3/3 件成功。manifest: D:\...\outputs\batch\manifest.json
```

入力 JSON（`samples/input.ja.json` が例）:

```json
[
  {"id": "line-001", "text": "こんにちは。", "language": "ja"},
  {"id": "line-002", "text": "今日はいい天気ですね。", "language": "ja", "seed": 42},
  {"id": "line-003", "text": "クローンもできます。", "language": "ja",
   "reference_audio": "ref/alice.wav"}
]
```

使えるキーは `id` / `text` / `language` / `reference_audio` / `reference_text` /
`seed` / `speed`。`reference_audio` は**入力 JSON からの相対パス**で解決される。

出力は `outdir/{id}.wav` と `outdir/manifest.json`。manifest には各件の
尺・サンプリングレート・使ったモデルが入るので、Remotion など下流から
音声の長さを知りたいときに使える。

```json
{
  "engine": "irodori",
  "total_elapsed_sec": 27.406,
  "items": [
    {
      "id": "line-001",
      "text": "こんにちは。今日はいい天気ですね。",
      "output_path": "...\\line-001.wav",
      "sample_rate": 48000,
      "duration_sec": 3.68,
      "model_id": "Aratako/Irodori-TTS-v4.1-Small",
      "elapsed_sec": 3.829
    }
  ],
  "failures": []
}
```

1 件失敗しても残りを続けたいときは `--keep-going` を付ける。失敗した件は
`failures` に記録され、終了コードは 1 になる。

### Python から呼ぶ

```python
from pathlib import Path
from tts_sample import create_engine, SynthesisRequest

with create_engine("irodori") as engine:
    result = engine.synthesize(
        SynthesisRequest(
            text="こんにちは。",
            output_path=Path("outputs/hello.wav"),
            language="ja",
            seed=42,
        )
    )
    print(result.sample_rate, result.duration_sec)
```

`with` を抜けるまでモデルは常駐する。複数件を投げるなら 1 つの `with` の中で回す。

```python
with create_engine("qwen") as engine:
    for i, line in enumerate(lines):
        engine.synthesize(
            SynthesisRequest(text=line, output_path=Path(f"outputs/{i:03d}.wav"), language="ja")
        )
```

エンジン一覧と対応機能はコードからも取れる。

```python
from tts_sample import available_engines, Capability

for name, spec in available_engines().items():
    print(name, spec.languages, spec.supports(Capability.SPEED))
```

---

## エンジンの選び方

|  | 日本語 | 英語 | クローン | Voice Design | 話速 | シード | レート | 速度 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---:|---|
| `qwen` | ○ | ○ | ○ | ○ | × | ○ | 24 kHz | 遅い |
| `chatterbox` | ○ | ○ | ○ | × | × | ○ | 24 kHz | 速い |
| `irodori` | ○ | **×** | ○ | ○ | ○ | ○ | 48 kHz | 速い |

- **まず試すなら `chatterbox`** — 0.5B と軽く、生成も速い。
- **日英を同じ声で出すなら `qwen`** — 1 本で両言語をまかなえる。
- **日本語のキャラクター性を優先するなら `irodori`** — 48kHz で表現力が高い。ただし英語は出せない。

対応していないパラメータを渡すと、**黙って無視されずエラーになる**。
判定はモデルを読み込む前に行われるので、待たされずに失敗する。

```powershell
tts synth --engine irodori --text "Hello." --lang en --out outputs\x.wav
# エラー: エンジン 'irodori' は言語 'en' に対応していません。 対応言語: ja

tts synth --engine chatterbox --text "テスト" --speed 1.5 --out outputs\x.wav
# エラー: エンジン 'chatterbox' は speed 指定に対応していません (speed=1.5)。

tts synth --engine chatterbox --voice-design "明るい声。" --text "テスト" --out outputs\x.wav
# エラー: エンジン 'chatterbox' は Voice Design（文章による声の設計）に対応していません。
```

### 日英の両方が要る場合

Irodori は英語を出せないので、二段構えにする。

1. Irodori で日本語のキャラクター声を作る
2. その音声を「マスター音声」として保存する
3. 英語版はマスター音声を `--ref` に渡して Qwen か Chatterbox で生成する

```powershell
# 日本語
tts synth --engine irodori --text "こんにちは。" --lang ja --out outputs\ja.wav

# 英語（同じ声でクローン）
tts synth --engine qwen --text "Hello." --lang en `
    --ref outputs\ja.wav --ref-text "こんにちは。" --out outputs\en.wav
```

日英で音響モデルが違うので、同一人物に聞こえるかは必ず耳で確認すること。

---

## 設定を変える

`python/engines.toml` にエンジンごとの設定がある。venv を作り直す必要はなく、
編集すれば次の実行から反映される。

よく触るもの:

```toml
[qwen.options]
base_model = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"   # VRAM 不足なら 0.6B に下げる
dtype = "bfloat16"

[qwen.options.speakers]
ja = "ono_anna"    # 参照音声なしのときのプリセット話者
en = "ryan"

[chatterbox.options]
cfg_weight = 0.5   # 上げると読み飛ばしが減る

[irodori.options]
num_steps = 24                          # 下げると速く、上げると高品質
caption = "落ち着いた低めの女性の声。"   # 文章で声を設計する（Voice Design）
```

`caption` は Irodori の目玉機能で、日本語の説明文から声を作れる。
本文に絵文字を入れると笑い・ため息なども表現する。

```powershell
tts synth --engine irodori `
    --text "あははっ🤭、それ本当に言ってるの？…😮‍💨まぁ、君らしいけどね。" `
    --lang ja --out outputs\emotion.wav
```

各設定の詳細は [docs/setup/](docs/setup/) のモデル別ドキュメントにある。

---

## 仕組み

3 モデルは `transformers` と `torch` のバージョン指定が**互いに排他的**で、
1 つの仮想環境に同居できない。

| モデル | transformers | torch |
|---|---|---|
| Qwen3-TTS | `==4.57.3` | 2.11 系 |
| Chatterbox | `==5.2.0` | 2.7 系 |
| Irodori-TTS | `>=5.12.1,<6` | 2.10 系 |

そこで共通層はモデルを直接読み込まず、エンジンごとの仮想環境にある `runner.py` を
サブプロセスとして起動し、標準入出力の JSON でやり取りする。

```
tts コマンド (.venvs/common ・ torch に依存しない)
  └─ SubprocessEngine ── 標準入出力 JSON ──┬─ .venvs/engine-qwen       の runner.py
                                           ├─ .venvs/engine-chatterbox の runner.py
                                           └─ .venvs/engine-irodori の runner.py
```

この境界のおかげで、

- モデルを足しても既存の環境が壊れない
- 共通層は軽いまま（GUI や Remotion 連携からそのまま使える）
- runner は常駐するので、バッチでモデル読み込みを繰り返さない

将来 HTTP サーバ方式（Irodori-TTS-Server のような OpenAI 互換 API）に
切り替えたくなった場合も、`TTSEngine` を実装したバックエンドを足すだけで
呼び出し側のコードは変わらない。

コードの構成は [python/README.md](python/README.md) を参照。

---

## 困ったときは

### `未構築` と表示される

そのエンジンの仮想環境がまだ無い。

```powershell
tts engines                                        # どれが未構築か確認
pwsh scripts\setup_engines.ps1 -Engines irodori    # 個別に作り直す
```

### 生成が遅い／CPU で動いている気がする

```powershell
tts doctor
```

`CUDA 利用不可（CPU 実行になります）` と出ていたら GPU が使えていない。
ドライバのバージョンと、`nvidia-smi` が動くかを確認する。

### VRAM が足りない（OOM）

- `engines.toml` の Qwen のモデル ID を `0.6B` 版に変える
- 複数エンジンを同時に動かさない
- `nvidia-smi` で他のプロセスが VRAM を使っていないか見る

### エラーの詳細が見たい

```powershell
tts synth --engine qwen --text "テスト" --out outputs\x.wav --verbose
```

エンジン側のログがそのまま流れる。

### 時間がかかりすぎてタイムアウトする

環境変数で延ばせる。

| 変数 | 既定（秒） | 用途 |
|---|---:|---|
| `TTS_SAMPLE_READY_TIMEOUT` | 1800 | モデル読み込み（初回は重みのダウンロード込み） |
| `TTS_SAMPLE_SYNTH_TIMEOUT` | 900 | 1 件あたりの合成 |

### 日本語が文字化けする

ターミナルのコードページを確認する（`chcp 65001`）。
コマンドと各エンジンのやり取りは UTF-8 に固定してある。

その他のトラブルは [docs/setup/00_common.md](docs/setup/00_common.md) と
各モデルのドキュメントに項目がある。

---

## 開発

pytest と ruff の設定は `python/pyproject.toml` にあるので、この 2 つだけは
`python` ディレクトリから実行する。

```powershell
cd python
.\.venvs\common\Scripts\python.exe -m pytest tests\ -q   # モデル不要のテスト
.\.venvs\common\Scripts\ruff.exe check .
.\.venvs\common\Scripts\ruff.exe format .
```

テストはモデルを読み込まずに、サブプロセスとのやり取り・UTF-8・
失敗からの復帰・未対応パラメータの拒否を検証する。

## ライセンス

| モデル | コード | 重み |
|---|---|---|
| Qwen3-TTS | Apache-2.0 | Apache-2.0 |
| Chatterbox | MIT | MIT（生成音声に PerTh 電子透かしが入る） |
| Irodori-TTS | MIT | MIT |

いずれも商用利用に制限はない。ただし**参照音声そのものの権利は別**で、
実在の人物の声をクローンする場合は本人の同意と利用範囲の確認が必要。
