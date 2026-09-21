# batch — JSON をまとめて合成する

```powershell
tts batch -e qwen sample.ja.json -o output\batch
```

モデルは 1 回だけロードされ、そのまま全件を流します。2 件目以降は
ロード時間（10〜60 秒）を払いません。共通のことは
[common_options.md](common_options.md) を参照。

## 引数

| 引数 | 内容 |
|---|---|
| `input` | **必須。** 入力 JSON。`input/batch/` からも探す |
| `-e` / `--engine` | **必須。** 使うエンジン |
| `-o` / `--output-dir` | 書き出し先（既定 `output/`） |
| `--keep-going` | 1 件失敗しても残りを続ける |
| `-v` / `--verbose` | エンジン自身の出力も見る |

## 入力 JSON

オブジェクトの配列で、`text` だけが必須です。

```json
[
  {"id": "line-001", "text": "こんにちは。", "language": "ja"},
  {"id": "line-002", "text": "今日はいい天気ですね。", "language": "ja", "seed": 42},
  {"id": "line-003", "text": "参照音声つき。", "reference_audio": "../voices/master.wav"}
]
```

| キー | 内容 |
|---|---|
| `id` | 出力ファイル名になる。省略すると `item-0000` 形式 |
| `text` | **必須。** 読み上げるテキスト |
| `language` | `ja` / `en` |
| `reference_audio` | **入力 JSON からの相対パス**で解決される |
| `reference_text` | 参照音声の書き起こし（Qwen のみ） |
| `voice_design` | 文章による声の指定 |
| `seed` | 乱数シード |
| `speed` | 話速 |

`id` が重複しているとファイルが上書きされるので、読み込みの時点でエラーに
なります。

## 出力

```
output/batch/
  line-001.wav
  line-002.wav
  line-003.wav
  manifest.json
```

`manifest.json` には各件のサンプリングレート・長さ・使用モデル・生成時間と、
失敗した件の記録が入ります。

```json
{
  "engine": "qwen",
  "total_elapsed_sec": 31.2,
  "items": [
    {
      "id": "line-001",
      "text": "こんにちは。",
      "output_path": "D:\\...\\output\\batch\\line-001.wav",
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

## 途中で失敗したとき

既定ではそこで止まります。`--keep-going` を付けると、失敗した件を
`failures` に記録して残りを続けます。

```powershell
tts batch -e qwen sample.ja.json --keep-going
```

失敗が 1 件でもあれば終了コードは 1 になるので、スクリプトから成否を
判定できます。

## 台詞に話者を割り当てたい場合

キャラクターごとに声を変えたいなら、JSON に毎回 `reference_audio` を
書くより [script.md](script.md) のほうが短く書けます。声の定義を
`cast.toml` に 1 回書けば、台本には「話者: 台詞」だけを書けば済みます。
