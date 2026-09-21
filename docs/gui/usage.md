# GUI の使い方

```powershell
scripts\win\LaunchApp.bat
```

合成そのものは CLI と同じ `ttstoolkit.engine` を呼ぶだけなので、
**画面からできることと CLI からできることは常に一致します**。細かい調整は
CLI のほうが速いので、画面は「試す・確かめる・1 本作る」のに使うのが
向いています。

![Synthesis](../readme/01_gui_synthesis.png)

## 画面の構成

上がタブ、下がログ。境目はドラッグで動かせます。

| タブ | すること |
|---|---|
| Synthesis | テキストを 1 件合成する |
| Voice Design | 文章から声を作り、`input/voices/` に残す |
| Script | キャスト定義と台本からまとめて合成する |

実行中は Run が無効になり、Cancel が有効になります。合成は別スレッドで
走るので画面は固まりません。

## Synthesis タブ

テキストを 1 件合成します（CLI の [synth](../cli/synth.md) と同じ）。

| 項目 | 内容 |
|---|---|
| Text | 読み上げるテキスト |
| Output Dir / Output File | 書き出し先。ファイル名を空にするとテキストから決まる |
| Engine / Language | 使うエンジンと言語。Auto はエンジンに任せる |
| Voice Source | 声の決め方。下記 |
| Seed | `random` のままだと毎回変わる。固定すると声がぶれにくい |
| Speed | Irodori のみ。他のエンジンでは 1.00 のままにする |

Voice Source を変えると、関係のない入力欄は消えます。

| Voice Source | 出る入力欄 |
|---|---|
| Preset voice | なし（エンジンの既定の声） |
| Clone from reference audio | Reference Audio / Reference Text |
| Design from a description | Voice Design |

Reference Text は Qwen だけが使います（書き起こしがあるとクローンの品質が
上がります）。

![Voice Design](../readme/02_gui_voice_design.png)

## Voice Design タブ

参照音声を持っていなくても、声を文章で説明すれば作れます。ただし作った声は
毎回わずかに揺れるので、**気に入った 1 本を残して以後はそれをクローンする**
のが安定した運用になります。このタブは書き出し先の既定が `input/voices/` に
なっていて、その流れをそのままなぞれます。

1. Voice Design に声と話し方を書く
2. Sample Text に試し読みさせる文を書く
3. Run → `input/voices/master.wav` ができる
4. 気に入らなければ Seed を変えて繰り返す
5. 決まったら Synthesis タブの Clone from reference audio でそれを指定する

エンジンは Voice Design に対応しているものだけが並びます（qwen / irodori）。
作り込みのコツは [../guide/original-voice.md](../guide/original-voice.md)。

![Script](../readme/03_gui_script.png)

## Script タブ

キャスト定義（`cast.toml`）と台本から、台詞をまとめて合成します
（CLI の [script](../cli/script.md) と同じ）。

| 項目 | 内容 |
|---|---|
| Cast File | キャラクターごとの声の定義 |
| Script File | 「話者: 台詞」を並べたテキスト |
| Output Dir | 書き出し先。台詞ごとの wav と manifest.json が置かれる |
| Gap | manifest の `start_sec` を出すときの台詞間の間（秒） |
| On Failure | チェックすると 1 台詞失敗しても残りを続ける |

台本の書き方は [../guide/script.md](../guide/script.md)。

## ログ

進捗とエラーが流れます。CLI が標準エラーへ出しているものと同じ内容で、
行頭のラベル（`[info]` / `[warn]` / `[error]`）も揃えてあります。

- File > Clear Log で消せます
- 実行を始めると自動で消えます

## 終わったあと

成功すると出力フォルダがエクスプローラーで開きます。

## 保存される設定

各タブの入力値とウィンドウの位置・サイズ・分割位置は、終了時に保存され
次の起動で戻ります。保存先は `QSettings`（Windows ではレジストリの
`HKCU\Software\TTSToolkit`）。

File > Clear Saved Settings... で消して既定値に戻せます。

## よくあること

### 初回だけ確認ダイアログが出る

モデル重みのダウンロード（数分・数 GB）が入るためです。1 回答えると、
そのセッション中はもう出ません。

### 「Engine Not Set Up」と言われる

そのエンジンの仮想環境がまだありません。案内されたセットアップ手順
（`scripts\win\setup_engines.ps1`）を実行してください。
[../cli/doctor.md](../cli/doctor.md) でも状態を確認できます。

### Cancel を押してもすぐ止まらない

生成中の 1 件を途中で止める手段がモデル側に無いので、キャンセルは
**次の台詞に入る前**に効きます。1 件だけの合成では最後まで走ります。

### 起動しない

`.venvs\common` が無い可能性があります。
`pwsh scripts\win\setup_engines.ps1 -Targets common` で作ってください。
GUI は `PySide6` を使うので、共通層の仮想環境が要ります。
