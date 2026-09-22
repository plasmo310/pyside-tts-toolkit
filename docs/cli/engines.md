# engines — エンジン一覧と対応機能

```powershell
tts engines
```

どのエンジンが使えて、何に対応しているかを表示します。引数はありません。

```
engine       state       lang     clone         voice_design  speed         seed          multilingual
------------------------------------------------------------------------------------------------------
qwen         ready       ja,en    yes           yes           -             yes           yes
chatterbox   ready       ja,en    yes           -             -             yes           yes
irodori      ready       ja       yes           yes           yes           yes           -

qwen: Qwen3-TTS 1.7B - high quality in both Japanese and English; 3-second cloning and voice design
  model  Qwen/Qwen3-TTS-12Hz-1.7B-Base
  python D:\...\.venvs\engine-qwen\Scripts\python.exe
...
```

## 列の意味

| 列 | 内容 |
|---|---|
| `state` | `ready` なら仮想環境が構築済み。`not set up` なら未構築 |
| `lang` | 対応している言語コード |
| `clone` | 参照音声から声を複製できる |
| `voice_design` | 文章で声を指定できる |
| `speed` | 話速を指定できる |
| `seed` | 乱数シードを固定できる |
| `multilingual` | 日本語以外も出せる |

`-` が付いた機能を指定すると、黙って無視されずエラーになります。
しかもエンジンを起動する前に判定するので待たされません。

## 未構築のエンジンがあるとき

```
irodori      not set up  ja       ...
  -> not set up; see docs/setup/03_irodori-tts.md
```

案内されたセットアップ手順を実行します。まとめて作るなら
`pwsh scripts\win\SetupEngines.ps1`、1 つだけなら
`-Targets irodori` を付けます。

## 定義はどこにあるか

`python/ttstoolkit/tool_config.py` の `ENGINE_DEFINITIONS` です。
`capabilities` に書いたものがこの表になり、同時に
`TTSEngine.validate()` の判定にも使われます。実際には効かない機能を
書くと「指定したのに効いていない」不具合になるので、増やすときは
runner が本当に読んでいるかを確かめてください。
