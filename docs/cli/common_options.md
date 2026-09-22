# CLI 共通のこと

入口は 1 つで、サブコマンドで切り替えます。

| コマンド | 内容 |
|---|---|
| [synth.md](synth.md) | テキストを 1 件合成する |
| [batch.md](batch.md) | JSON に並べたテキストをまとめて合成する |
| [script.md](script.md) | キャラクター台本からまとめて合成する |
| [engines.md](engines.md) | エンジン一覧と対応機能 |
| [doctor.md](doctor.md) | 環境の健全性チェック |

## 実行のしかた

リポジトリのルートで、共通層の Python を使って実行します。

```powershell
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli synth -e qwen -t "こんにちは。"
```

毎回書くには長いので、関数を 1 つ作っておくと楽です
（`Set-Alias` は引数を渡せないため関数にします）。

```powershell
function tts { & "$PWD\.venvs\common\Scripts\python.exe" -m ttstoolkit.cli @args }
```

以降の例では `tts synth ...` と書きます。

関数を定義したくない場合は、`scripts\win\` にサブコマンドごとの
`.bat` がある。引数はそのまま渡される。

```powershell
scripts\win\RunSynth.bat -e qwen -t "こんにちは。"
scripts\win\RunBatch.bat -e qwen sample.ja.json
scripts\win\RunScript.bat ep01.ja.txt -c cast.toml
scripts\win\RunEngines.bat
scripts\win\RunDoctor.bat
```

`--help` はサブコマンドごとにも出せます。

```powershell
tts --help          # サブコマンドの一覧
tts synth --help    # synth の引数
```

## 共通の引数

### `-v` / `--verbose`

エンジン自身の出力（モデルのロード進捗、ライブラリの警告）をログへ流します。
合成がうまくいかないときに最初に足す引数です。

### `-o` / `--output-dir`

書き出し先ディレクトリ。既定は `output/`。

## パスの解決

相対パスは次の順で探し、最初に見つかったものを使います。

1. カレントディレクトリ
2. リポジトリのルート
3. 種類ごとの既定の置き場

| 種類 | 既定の置き場 | 例 |
|---|---|---|
| 参照音声 (`-r`) | `input/voices/` | `-r master.wav` |
| バッチ入力 | `input/batch/` | `tts batch sample.ja.json` |
| 台本・キャスト | `input/script/` | `tts script ep01.ja.txt` |

おかげでリポジトリのどこから実行しても、ファイル名だけで済みます。

## 出力

すべて **モノラル 16bit PCM の WAV**。サンプリングレートはモデル本来の値
（Qwen / Chatterbox は 24kHz、Irodori は 48kHz）を保ちます。

`batch` と `script` は書き出し先に `manifest.json` も置きます。各件の
サンプリングレート・長さ・使用モデル・生成時間が入っているので、動画側で
尺を計算するのに使えます。

## ログと終了コード

進捗とエラーは **標準エラー**へ `[info] ...` の形で出ます。結果そのもの
（書き出したパスなど）は標準出力です。パイプで拾うときに混ざりません。

| 終了コード | 意味 |
|---|---|
| 0 | 成功 |
| 1 | 失敗（未対応パラメータ、ファイルが無い、合成の失敗） |
| 130 | Ctrl+C で中断 |

## 未対応パラメータはエラーになる

エンジンが対応していない指定は、黙って無視されず即座にエラーになります。
しかもエンジンを起動する前に判定するので、待たされません。

```powershell
tts synth -e irodori -t "Hello." -l en
# [error] Engine 'irodori' does not support language 'en' (supported: ja)
```

何が使えるかは [engines.md](engines.md) で確認できます。

## タイムアウト

初回はモデル重みのダウンロードを含むので長めに取ってあります。
足りなければ環境変数で延ばせます。

| 変数 | 既定（秒） | 用途 |
|---|---:|---|
| `TTS_READY_TIMEOUT` | 1800 | モデルのロード待ち |
| `TTS_SYNTH_TIMEOUT` | 900 | 1 件あたりの合成 |
