# CLAUDE.md

TTS Toolkit — Qwen3-TTS / Chatterbox / Irodori-TTS の 3 つをローカルで動かし、
共通のインターフェースから使うツール。GUI (PySide6) と CLI の 2 つの入口を持つ。

詳細は `docs/` にあります。**このファイルには内容を複製せず、必ずそちらを見てください。**

## まずこれを読む

| 目的 | ドキュメント |
| --- | --- |
| **コードを書く前に必ず** | [docs/instructions/code_guide.md](docs/instructions/code_guide.md) |
| 全体構成・制約・設計の根拠 | [docs/development/architecture.md](docs/development/architecture.md) |
| ドキュメントの一覧 | [docs/README.md](docs/README.md) |
| 使い方（利用者向け） | [README.md](README.md) |

## 構成のかいつまみ

```
python/ttstoolkit/  GUI・CLI・処理本体をまとめたパッケージ
  cli/              単一入口。python -m ttstoolkit.cli <command>
  gui/              PySide6 の MVC
  core/             CLI / GUI 共用の処理本体（親プロセス側）
  engine/           別の仮想環境で動く runner
    _shared/        両側が守る契約（protocol）と runner の土台
engine_env/         各エンジンの仮想環境を作るための定義
.venvs/             仮想環境の実体（common と engine-*）
resources/          stylesheet.qss（色とサイズは全部ここ）
input/ output/      入出力
references/         設計の参考（pyside-whisper-toolkit）。編集しない
```

## よく使うコマンド

```powershell
REM GUI 起動
scripts\win\LaunchApp.bat

REM Lint / Format（変更したら必ず通す）
.\.venvs\common\Scripts\python.exe -m ruff check .
.\.venvs\common\Scripts\python.exe -m ruff format .

REM テスト（モデル不要）
.\.venvs\common\Scripts\python.exe -m pytest -q

REM CLI
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli synth -e irodori -t "こんにちは。"
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli doctor
```

## 気をつけること

- `python/ttstoolkit/core` の約束（`print` しない / `sys.exit` しない / 失敗は
  `TTSToolkitError`）を壊さない
- runner は torch を**関数の中で** import する。
  `engine/_shared/runner_base.py` より先に読み込まれると stdout の退避が
  間に合わない。**core からあのファイルを import しない**（標準出力が壊れる）
- `sys.path` をコードから変更しない。runner の検索パスは
  `EngineSpec.python_path` に書く
- 色・サイズは `resources/ui/stylesheet.qss` に置く。Python 側にハードコードしない
- Python 本体にライブラリを入れない。すべて `.venvs/` の中へ
- `references/` と `engine_env/irodori/vendor/` は読むだけ。編集しない
- 1 行 79 文字、docstring とコメントは日本語、識別子と UI 文字列は英語
