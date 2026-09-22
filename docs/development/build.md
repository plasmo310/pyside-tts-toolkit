# ビルド（PyInstaller で exe にする）

`build_env/` に、アプリ本体とは別の仮想環境を作ってビルドします
（実行用の `.venvs/common` に PyInstaller を混ぜないため）。

```
build_env/
├─ requirements.txt        共通層 (GUI) の依存 + pyinstaller
├─ python/run.py           PyInstaller の入口
└─ scripts/
    └─ win/{Setup.bat, BuildApp.bat}
```

固めるのは **共通層 (GUI/CLI) だけ**。各エンジン (Qwen3-TTS /
Chatterbox / Irodori-TTS) は
[architecture.md](architecture.md) の通り重い依存が互いに排他的で、
プロセス分離が前提になっている。そのため固めた exe も
`.venvs/engine-*` を外部プロセスとして呼ぶだけで、モデルの依存は
一切同梱しない。`docs/setup/` の手順で作った `.venvs/engine-*` /
`engine_env/` はビルド後もそのまま使う。

## 1. ビルド環境を作る

```bat
REM Windows
build_env\scripts\win\Setup.bat
```

`build_env/.venv` に、共通層の依存（`pyproject.toml` を `-e ..` で
インストール）と PyInstaller が入る。

## 2. ビルドする

```bat
REM Windows
build_env\scripts\win\BuildApp.bat
```

`build_env/scripts/win/dist/TTSToolkit/` に出力される。

## 何をしているか

```
pyinstaller --noconsole --onedir --name TTSToolkit
    --paths <root>/python
    --hidden-import PySide6
    --add-data <root>/resources;./resources
    --add-data <root>/python;./python
    --icon <root>/resources/icon/tool_icon_rect.ico
    build_env/python/run.py
```

- `--paths` には `python` だけを渡す。アプリケーションコードはすべて
  `ttstoolkit` パッケージとして収集される。
- `--add-data <root>/resources;./resources` でアイコンと
  スタイルシートを同梱する。`ToolConfig` が `sys._MEIPASS` を見て、
  固めた場合は `_internal/resources/` を参照するようになっている。
- `--add-data <root>/python;./python` は他の 2 つと違い、**exe に
  コンパイルするためではなく生の `.py` を同梱するため**のもの。
  各エンジンは固めた exe とは別の仮想環境からサブプロセスとして
  起動され、そちら側から `ttstoolkit.engine.*` を import する
  （`PYTHONPATH` 越し。詳細は `core/_internal/engine_process.py`）。
  そのため exe の中に圧縮された形ではなく、ディスク上の実ファイル
  として置いておく必要がある。`core/paths.py` は `sys.frozen` の
  ときこの同梱先 (`sys._MEIPASS/python`) を `PYTHON_DIR` として使う。

入口の `build_env/python/run.py` は `-m ttstoolkit.main` の代わり。

```python
from ttstoolkit.main import main

main()
```

## 配置

固めた `TTSToolkit/` フォルダの中（`TTSToolkit.exe` や `_internal/`
と同じ階層）に、`input/` / `output/` / `.venvs/` / `engine_env/` を
置いて使う。`core/paths.py` は `sys.frozen` のとき `ROOT_DIR` を
exe のあるフォルダ（`os.path.dirname(sys.executable)`）として扱う
ため。

```
TTSToolkit/
├─ TTSToolkit.exe
├─ _internal/              ← resources/ と python/ (生の .py) を同梱
├─ input/
├─ output/
├─ .venvs/
│   ├─ engine-qwen/
│   ├─ engine-chatterbox/
│   └─ engine-irodori/
└─ engine_env/
```

`.venvs/engine-*` と `engine_env/` は `docs/setup/` の手順（または
リポジトリの `scripts/win/SetupEngines.ps1`）でこのフォルダの中に
作る。実機で確認済み（`build_env\scripts\win\dist\TTSToolkit\` に
これらをコピーして起動し、3 エンジンとも `installed` と判定される
ことを確認した）。

CLI 相当の操作をしたい場合は `.venvs/common` を別途セットアップして
そちらから `python -m ttstoolkit.cli` を使う（固めた exe は GUI 専用）。

## 注意

- `build_env/.venv` と `dist` / `build` は `.gitignore` 対象。
- エンジンの仮想環境は固めても軽くならない。`docs/setup/` の手順で
  別途構築する必要がある。
