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
`.venvs/engine-*` を外部プロセスとして呼ぶ。`BuildApp.bat` は構築済みの
エンジン仮想環境を成果物へコピーする。Irodori の仮想環境と上流 clone は必須で、
未構築ならビルドを失敗させる。

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
Irodori を使うには、先にリポジトリ直下でその環境を構築しておく。

```powershell
powershell scripts\win\SetupEngines.ps1 -Targets irodori
```

モデル重みは初回実行時に Hugging Face から取得される。

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
と同じ階層）に、必要に応じて `input/` / `output/` を置いて使う。
エンジン用の `.venvs/` / `engine_env/` はビルド時に配置される。
`core/paths.py` は `sys.frozen` のとき `ROOT_DIR` を
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

Irodori の `.venvs/engine-irodori` と `engine_env/irodori/vendor/Irodori-TTS`
は `BuildApp.bat` が自動でコピーする。利用者が別途配置したり、配布先で
`SetupEngines.ps1` を実行したりする必要はない。これらが無い状態では、実行不能な
成果物を作らないようビルドが失敗する。

CLI 相当の操作をしたい場合は `.venvs/common` を別途セットアップして
そちらから `python -m ttstoolkit.cli` を使う（固めた exe は GUI 専用）。

## 注意

- `build_env/.venv` と `dist` / `build` は `.gitignore` 対象。
- エンジンの仮想環境を含むため、配布物のサイズは大きくなる。
