# キャラクター台本から音声を作る

複数のキャラクターが会話する台本を書いて、台詞ごとの wav をまとめて生成する。

```powershell
tts script ep01.ja.txt -c cast.toml -o output\ep01
```

```
[info] 7 lines / 3 characters / engines: qwen, irodori
--- qwen (1 lines) ---
[001] ナレーター   1.84s  ある晴れた日のこと。
--- irodori (6 lines) ---
[002] 霊夢         2.64s  今日はいい天気ね。
[003] 魔理沙       3.84s  そうだな、絶好の弾幕日和だぜ！
[004] 霊夢         2.52s  ……また変なこと言ってる。
[005] 魔理沙       3.92s  変じゃないぜ。これが私の生き方なんだ。
[006] 霊夢         4.96s  まあいいわ。お茶でも淹れてくるから、そこで待っ…
[007] 魔理沙       2.24s  やった、ごちそうさま！
[info] wrote output\ep01\manifest.json
[info] 7/7 lines synthesized
```

## ファイルを 2 つに分ける理由

台詞は毎回書くが、声を決めるのは最初の一度きり。そこで分担を分けている。

| ファイル | 書く頻度 | 内容 |
|---|---|---|
| `cast.toml` | 最初に一度 | キャラクターの声（エンジン・参照音声・Voice Design・シード） |
| `script.txt` | 毎回 | 台詞そのもの |

台本側には「誰が」「何を」しか書かないので、話者名 + コロンだけで済む。

## キャスト定義 (`cast.toml`)

```toml
[voices."霊夢"]
engine = "irodori"
voice_design = "落ち着いた少女の声。淡々としていて、少し呆れたような話し方。"
language = "ja"
seed = 42

[voices."魔理沙"]
engine = "irodori"
reference_audio = "../voices/marisa.wav"   # この cast.toml からの相対パス
language = "ja"

[voices."ナレーター"]
engine = "qwen"
language = "ja"
seed = 100
```

> [!warning] 日本語のキャラクター名はクォートが必要
> TOML の仕様上、クォートなしのテーブル名に使えるのは半角英数字と `_` `-` だけ。
> `[voices.霊夢]` は構文エラーになるので、`[voices."霊夢"]` と書く。

### 使えるキー

| キー | 必須 | 説明 |
|---|:---:|---|
| `engine` | ○ | `qwen` / `chatterbox` / `irodori` |
| `reference_audio` | | 参照音声。**この `cast.toml` からの相対パス**で解決される |
| `reference_text` | | 参照音声の書き起こし（Qwen のクローン品質が上がる） |
| `voice_design` | | 文章による声の設計（`qwen` / `irodori` のみ） |
| `language` | | 既定の言語 |
| `seed` | | 既定の乱数シード |
| `speed` | | 既定の話速（`irodori` のみ） |
| `volume` | | 既定の音量。1.0 が等倍。エンジンを問わず効く |

未知のキーを書くとエラーになる。綴り間違いが黙って無視されないようにしてある。

> [!tip] シードは固定しておく
> `seed` を決めておくと、同じ台詞を作り直したときに声がぶれにくい。
> キャラクターごとに違う値にしておくとよい。

## 台本 (`script.txt`)

```
# ■ オープニング
# 行頭の # はコメント。セクションの見出しにも使う。

ナレーター: ある晴れた日のこと。

霊夢: 今日はいい天気ね。
魔理沙: そうだな、絶好の弾幕日和だぜ！

# ■ 本編

霊夢[speed=0.9]: ……また変なこと言ってる。
[001-001-plasmo] ナレーター: Hello everyone!
魔理沙[id=punchline]: やった、ごちそうさま！

霊夢: まあいいわ。
  お茶でも淹れてくるから、
  そこで待ってなさい。
```

### 書き方のルール

- **1 行 1 台詞**。`話者: 台詞` の形。コロンは半角 `:` でも全角 `：` でもよい。行頭に `[出力名]` を置くと、その台詞の wav 名を指定できる。
- **`#` で始まる行はコメント**。セクションの見出しに使うと読みやすい。
- **空行は無視される**。場面の区切りに自由に入れてよい。
- **インデントした行は直前の台詞の続き**。長い台詞を折り返して書ける。

### 継続行の連結には区切り文字が入らない

```
霊夢: まあいいわ。
  お茶でも淹れてくるから、
  そこで待ってなさい。
```

これは `まあいいわ。お茶でも淹れてくるから、そこで待ってなさい。` になる。
日本語に余計な空白が入らないようにこうしている。

**英語の台詞は 1 行に収めるか、行末に空白を置くこと。** そうしないと
`Hello.How are you?` のように単語がくっつく。

### 台詞ごとのオプション

角括弧でその台詞だけ設定を上書きできる。キャスト定義より優先される。

```
霊夢[speed=0.9]: ゆっくり話すわ。
魔理沙[id=punchline, seed=99]: それでもいいのか？
ナレーター[lang=en]: Meanwhile, in another world.
```

| オプション | 説明 |
|---|---|
| `id` | 出力ファイル名に使う識別子。後から特定の台詞を差し替えるときに便利 |
| `speed` | 話速（対応エンジンのみ） |
| `seed` | 乱数シード。その台詞だけ作り直したいときに変える |
| `lang` | 言語 |
| `volume` | 音量。1.0 が等倍。エンジンを問わず効く |

未知のオプションはエラーになる。

### 台詞ごとの出力名

行頭の `[出力名]` で、その行の wav のベース名を直接指定できる。`.wav` は自動で付く。
外部ツールで管理しているカット番号に合わせたり、必要な台詞だけを再出力したりするときに使える。

```
[001-001-plasmo] ナレーター: Hello everyone!
霊夢: 指定しない行は従来どおり。
```

この例の出力は `001-001-plasmo.wav` と `002-霊夢.wav`。指定名は台本内で重複できず、`\` や `/` などのファイル名に使えない文字はエラーになる。

## 出力

```
output/ep01/
  001-ナレーター.wav
  002-霊夢.wav
  003-魔理沙.wav
  ...
  001-001-plasmo.wav    ← 行頭の [001-001-plasmo] を付けた台詞
  007-punchline.wav      ← [id=punchline] を付けた台詞
  manifest.json
```

指定がないファイル名の先頭は台本の並び順。`id` を付けた台詞は `連番-id.wav` になる。行頭の `[出力名]` を指定した台詞だけは、連番を追加せず `出力名.wav` になる。

### manifest.json

```json
{
  "gap_sec": 0.3,
  "total_duration_sec": 23.76,
  "items": [
    {
      "index": 1,
      "id": null,
      "voice": "ナレーター",
      "text": "ある晴れた日のこと。",
      "start_sec": 0.0,
      "output_path": "...\\001-ナレーター.wav",
      "sample_rate": 24000,
      "duration_sec": 1.84,
      "engine": "qwen",
      "model_id": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
      "elapsed_sec": 1.62
    },
    {
      "index": 2,
      "voice": "霊夢",
      "text": "今日はいい天気ね。",
      "start_sec": 2.14,
      "sample_rate": 48000,
      "duration_sec": 2.64
    }
  ],
  "failures": []
}
```

`start_sec` は先頭からの累積オフセットで、`--gap`（既定 0.3 秒）を台詞の間に
挟んで計算している。Remotion の `<Sequence from={...}>` にそのまま使える。

```ts
const fps = 30;
manifest.items.map((item) => (
  <Sequence from={Math.round(item.start_sec * fps)}
            durationInFrames={Math.round(item.duration_sec * fps)}>
    <Audio src={staticFile(`ep01/${item.index.toString().padStart(3, '0')}-${item.voice}.wav`)} />
    <Subtitle text={item.text} speaker={item.voice} />
  </Sequence>
));
```

> [!note] サンプリングレートは混ざる
> エンジンごとにレートが違う（Irodori は 48 kHz、Qwen と Chatterbox は 24 kHz）。
> manifest の `sample_rate` に各ファイルの実際の値が入るので、ffmpeg や
> Remotion 側でリサンプルさせればよい。揃えたい場合は全キャラクターを
> 同じエンジンにする。

## モデルの読み込みは 1 エンジンにつき 1 回

台詞ごとにプロセスを立て直すとモデルの読み込み（10〜60 秒）を毎回払うことになる。
そこで**エンジン単位で台詞をまとめて処理**し、manifest では台本順に並べ直している。

上の例では qwen を 1 回・irodori を 1 回起動するだけで 7 台詞を処理している。
そのため進捗表示はエンジンごとにまとまって出て、台本順とは一致しない。

キャラクターを増やしてもエンジンが同じなら追加コストはない。
逆に 3 エンジンを混ぜると読み込みが 3 回発生する。

## 失敗したとき

既定では最初の失敗で止まり、そこまでの結果で manifest を書く。
残りを続けたい場合は `--keep-going` を付ける。失敗した台詞は
`failures` に**台本の行番号つき**で記録される。

```json
"failures": [
  {"index": 5, "voice": "霊夢", "line_no": 14, "error": "エンジン 'irodori' は言語 'en' に..."}
]
```

## 英語版を作る

Irodori は英語を出せないので、英語版は別のキャスト定義を用意して
同じキャラクターを `qwen` か `chatterbox` に割り当てる。
声を揃えるには、日本語版で作ったマスター音声を参照音声に指定する。

`cast.en.toml`:

```toml
[voices."Reimu"]
engine = "qwen"
reference_audio = "../voices/reimu_master.wav"
reference_text = "こんにちは。私はこのキャラクターの声です。"
language = "en"
seed = 42
```

```powershell
tts script ep01.ja.txt -c cast.toml -o output\ep01-ja
tts script ep01.en.txt -c cast.en.toml -o output\ep01-en
```

マスター音声の作り方は [original-voice.md](original-voice.md) を参照。

## トラブルシュート

### `Invalid initial character for a key part`

`cast.toml` の日本語のテーブル名をクォートしていない。
`[voices.霊夢]` ではなく `[voices."霊夢"]` と書く。

### `N 行目: キャスト定義に '...' がありません`

台本の話者名と `cast.toml` の名前が一致していない。
表記ゆれ（全角・半角、スペースの有無）を確認する。

### `N 行目を解釈できません`

コロンが無いか、話者名に `:` `[` `]` が含まれている。
これらの文字は話者名には使えない。

### 台詞がくっついて読まれる

英語の台詞をインデント継続で書いている。継続行は区切り文字なしで連結されるので、
英語は 1 行に収めるか行末に空白を置く。

### 特定の台詞だけ作り直したい

その台詞に `[seed=...]` を付けて値を変え、同じコマンドを実行する。
外部で管理する出力名がある場合は、行頭の `[出力名]` を付けておくと該当 wav を固定名で上書きできる。
