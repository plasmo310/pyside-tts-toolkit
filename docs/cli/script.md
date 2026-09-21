# script — キャラクター台本からまとめて合成する

```powershell
tts script ep01.ja.txt -c cast.toml -o output\ep01
```

声の定義（`cast.toml`）は一度書けば使い回せるので、毎回書くのは台詞だけです。
台本の書き方は [../guide/script.md](../guide/script.md) に詳しくあります。
共通のことは [common_options.md](common_options.md) を参照。

## 引数

| 引数 | 内容 |
|---|---|
| `script` | **必須。** 台本テキスト。`input/script/` からも探す |
| `-c` / `--cast` | キャスト定義 TOML。省略すると台本の隣の `cast.toml` |
| `-o` / `--output-dir` | 書き出し先（既定 `output/`） |
| `--gap` | manifest の `start_sec` を出すときの台詞間の間（秒、既定 0.3） |
| `--keep-going` | 1 台詞失敗しても残りを続ける |
| `-v` / `--verbose` | エンジン自身の出力も見る |

## 2 つのファイル

### cast.toml — 声の定義

```toml
[voices."霊夢"]
engine = "irodori"
voice_design = "落ち着いた少女の声。淡々としていて、少し呆れたような話し方。"
language = "ja"
seed = 42

[voices."ナレーター"]
engine = "qwen"
language = "ja"
seed = 100
```

キャラクター名が日本語のときは TOML の仕様上クォートが要ります
（`[voices."霊夢"]`）。`reference_audio` は **cast.toml からの相対パス**で
解決されるので、`input/script/cast.toml` からは `"../voices/master.wav"`。

### 台本 — 台詞そのもの

```
# ある晴れた日

霊夢: 今日はいい天気ね。
魔理沙: そうだな、絶好の弾幕日和だぜ！

霊夢[speed=0.9]: ……また変なこと言ってる。
魔理沙[id=punchline]: やった、ごちそうさま！
```

角括弧で `id` / `speed` / `seed` / `lang` を台詞ごとに上書きできます。

## 話者ごとにエンジンが違ってよい

同じエンジンの台詞はまとめて処理し、モデルのロードはエンジンごとに 1 回だけ。
台本順は `manifest.json` で組み直します。

```
[info] 7 lines / 3 characters / engines: qwen, irodori
--- qwen (1 lines) ---
[001] ナレーター   1.84s  ある晴れた日のこと。
--- irodori (6 lines) ---
[002] 霊夢         2.64s  今日はいい天気ね。
[003] 魔理沙       3.84s  そうだな、絶好の弾幕日和だぜ！
...
[info] 7/7 lines synthesized
```

## 出力

```
output/ep01/
  001-ナレーター.wav
  002-霊夢.wav
  ...
  007-punchline.wav
  manifest.json
```

ファイル名は `連番-話者名.wav`。`id` を指定した台詞は `連番-id.wav` に
なります。連番が前にあるので、並び順がファイラーで一目で分かります。

### manifest.json

```json
{
  "script": "D:\\...\\input\\script\\ep01.ja.txt",
  "gap_sec": 0.3,
  "total_duration_sec": 23.76,
  "items": [
    {
      "index": 1,
      "id": null,
      "voice": "ナレーター",
      "text": "ある晴れた日のこと。",
      "start_sec": 0.0,
      "output_path": "D:\\...\\output\\ep01\\001-ナレーター.wav",
      "sample_rate": 24000,
      "duration_sec": 1.84,
      "engine": "qwen",
      "model_id": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
      "elapsed_sec": 18.7
    }
  ],
  "failures": []
}
```

`start_sec` は先頭からの累積オフセットです（前の台詞の長さ + `--gap`）。
動画側で「この秒から流す」の計算にそのまま使えます。

`--gap` は manifest の計算に使うだけで、**wav そのものには無音を足しません**。

## 日英 2 本を作る

キャスト定義を言語ごとに用意し、台本を差し替えます。

```powershell
tts script ep01.ja.txt -c cast.toml    -o output\ep01-ja
tts script ep01.en.txt -c cast.en.toml -o output\ep01-en
```

Irodori は英語を出せないので、英語版では同じキャラクターを qwen や
chatterbox に割り当てます。声を揃えるには、日本語版で作ったマスター音声を
`reference_audio` に指定します
（[../guide/original-voice.md](../guide/original-voice.md)）。
