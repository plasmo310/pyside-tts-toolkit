# synth — テキストを 1 件合成する

```powershell
tts synth -e irodori -t "こんにちは。音声合成のテストです。" -l ja
```

書き出し先を省略すると `output/` にテキストから決まる名前で置かれます。
共通のことは [common_options.md](common_options.md) を参照。

## 引数

| 引数 | 内容 |
|---|---|
| `-e` / `--engine` | **必須。** `qwen` / `chatterbox` / `irodori` |
| `-t` / `--text` | 読み上げるテキスト |
| `-f` / `--text-file` | テキストを UTF-8 のファイルから読む |
| `-O` / `--output` | 出力ファイル名。省略するとテキストから決まる |
| `-o` / `--output-dir` | 書き出し先ディレクトリ（既定 `output/`） |
| `-l` / `--language` | `ja` / `en`。省略するとエンジンに任せる |
| `-r` / `--reference` | 参照音声。声を真似る |
| `--reference-text` | 参照音声の書き起こし（Qwen のみ使う） |
| `--voice-design` | 文章で声を指定する（qwen / irodori） |
| `--seed` | 乱数シード。固定すると声がぶれにくい |
| `--speed` | 話速（irodori のみ） |
| `-v` / `--verbose` | エンジン自身の出力も見る |

`-t` と `-f` はどちらか一方が必須です。

## 声の決め方は 3 通り

### 1. そのまま（プリセットの声）

```powershell
tts synth -e chatterbox -t "こんにちは。" -l ja
```

Qwen は言語ごとのプリセット話者（日本語は `ono_anna`、英語は `ryan`）を使います。
話者は `tool_config.py` で変えられます。

### 2. 参照音声から複製する

```powershell
tts synth -e qwen -t "おはようございます。" -l ja `
    -r master.wav --reference-text "参照音声で話している内容" `
    -O clone.wav
```

`--reference-text` は Qwen だけが使います。書き起こしがあると ICL モードに
なり品質が上がり、無いと話者埋め込みのみのモードに落ちます（警告が出ます）。
Chatterbox と Irodori は書き起こし不要です。

参照音声の長さの目安は、Qwen / Chatterbox が 3 秒程度から、Irodori は 30 秒
以上を推奨（上限 120 秒）。

### 3. 文章で声を作る

```powershell
tts synth -e irodori -l ja `
    -t "こんにちは。この声でナレーションを読み上げます。" `
    --voice-design "落ち着いた低めの女性の声。丁寧で穏やかな話し方。"
```

qwen と irodori が対応しています。irodori は `-r` と併用でき、その場合は
声質が参照音声・話し方が `--voice-design` になります。qwen は併用できません
（声の出どころが 1 つに決まらないため）。

作った声を使い回す手順は
[../guide/original-voice.md](../guide/original-voice.md) を参照。

## 出力

```
[info] Engine irodori is ready (Aratako/Irodori-TTS-v4.1-Small)
wrote D:\...\output\irodori-8f3c1a2b9d04.wav
  model    Aratako/Irodori-TTS-v4.1-Small
  audio    48000 Hz / 3.96s
  took     4.89s
```

`model` は**実際に使われた**モデルです。Qwen はリクエストの内容で
Base / CustomVoice / VoiceDesign を切り替えるので、ここで確認できます。

## 同じ声をもう一度出す

`--seed` を固定します。テキストが同じなら、ほぼ同じ音声になります。

```powershell
tts synth -e chatterbox -t "テスト" -l ja --seed 42
```

ただし完全な決定性は保証されません。何度使う声かが決まっているなら、
シードで粘るより**良い 1 本を `input/voices/` に残してクローンする**ほうが
確実です。

## 長文

長文は 1 件で投げるより、文単位に分けて [batch.md](batch.md) で流すほうが
安定します。Qwen は `max_new_tokens` の上限に達すると途中で切れます。
