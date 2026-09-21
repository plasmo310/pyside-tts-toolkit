# コーディングルール

このリポジトリに手を入れるときの決まりごとです。全体構成は
[../development/architecture.md](../development/architecture.md) を参照してください。

## 言語

- **識別子・UI の文字列・ログ・エラーメッセージ・ファイル名は英語**
- **docstring とコメントは日本語**
- docstring は Google スタイル。`Args:` / `Returns:` / `Raises:` を使う。
  クラスには必要に応じて `Attributes:` を書く

```python
def resolve_input(path: str, default_dir: str | None = None) -> str:
    """入力ファイルのパスを解決する。

    Args:
        path: 利用者が指定したパス。絶対パスならそのまま扱う。
        default_dir: 3 番目に探す既定の置き場。None なら探さない。

    Returns:
        str: 実在が確認できた最初のパス。
    """
```

## 書式

- **Ruff** で `check` と `format` の両方を通す。設定は `pyproject.toml`
  ```powershell
  .\.venvs\common\Scripts\python.exe -m ruff check .
  .\.venvs\common\Scripts\python.exe -m ruff format .
  ```
- **1 行 79 文字**、インデント 4 スペース、ダブルクォート
- `from __future__ import annotations` をファイル先頭に置く
- 型ヒントは引数・戻り値に必ず付ける（`-> None` も省略しない）。
  `str | None` の記法を使う

## 命名

- ファイルは `snake_case.py`。1 ファイル 1 クラスを基本とし、ファイル名は
  クラス名の snake_case（`main_view.py` → `MainView`）
- private な状態は `self.__foo`（ダブルアンダースコア）。公開は `@property`
- モジュール内だけで使うクラス・定数は先頭 1 つのアンダースコア
  （`_LogPane`, `_PREVIEW_CHARS`）
- 接尾辞: `*_tab`（タブ）、`*_row`（入力行）、`*_runner`（エンジンの runner）、
  `*_config`

### Qt のシグナルとスロット

- シグナルは `on_<動詞>_<名詞>_signal`（例: `on_click_run_signal`,
  `on_close_window_signal`）
- 受け側のスロットは `__on_<...>`（例: `__on_click_run_synthesis_button`）

## MVC

- **View** は Qt のウィジェットだけ。Model / Controller を import しない。
  外への通知はクラス変数の `Signal`、外からの反映は公開メソッド
- **Model** は処理と永続化。Qt のウィジェットに触らない（`QSettings` は可）
- **Controller** が両方を生成し、`__setup_connections()` でシグナルを繋ぐ
- ダイアログは View 側に置き、Controller には `bool` などの結果だけ返す

### レイアウト

- レイアウトは `__build_<section>() -> QtWidgets.QWidget` を返す private
  ビルダーに分ける
- Qt の enum はフル修飾で書く
  （`QtCore.Qt.AlignmentFlag.AlignVCenter`。`Qt.AlignVCenter` とは書かない）
- 色・サイズは `resources/ui/stylesheet.qss` に置き、Python 側は
  `setProperty("class", "...")` でタグを付けるだけにする

## python/ttstoolkit/engine の約束

GUI からも CLI からも呼ぶので、次を守ります。

- `print()` しない。進捗は `logging`（`settings.get_logger(__name__)`）
- `sys.exit()` しない。失敗は `TTSToolkitError` を投げる
- 長い処理は `on_progress` / `is_canceled` を受け取れるようにする
- 既定値は dataclass に持たせ、CLI と GUI の両方がそれを唯一の出どころにする
- パスは `str` で扱い、runner へ渡す前に絶対パスへ直す

## import

- `__init__.py` は置かない（暗黙の名前空間パッケージ）。再エクスポートは
  無いので、常に定義元のモジュールから import する
- `sys.path` をコードから変更しない。runner に渡す検索パスは
  `EngineSpec.python_path` として定義に書き、`SubprocessEngine` が
  `PYTHONPATH` として渡す
- サブパッケージをまたぐ import は `ttstoolkit` から始まる絶対 import にする

### runner だけの例外

runner は **torch やモデルのライブラリを関数の中で import** します。

```python
from ttstoolkit.engine.runners.interface import EngineRunner, log, serve


class QwenRunner(EngineRunner):
    def __init__(self, options: dict) -> None:
        import torch          # ← ここで import する
```

`runners/interface.py` は import された時点で `sys.stdout` を `stderr` へ
差し替えます。これが torch より先に起きないと、ライブラリのログが JSONL の
通信路を壊します。モジュール先頭に `import torch` を書くと、import の
並べ替えで順序が崩れかねないので、関数の中に置いて順序に依存させません。

## どこから読むか

| 知りたいこと | 読む順番 |
|---|---|
| 全体の流れ | `cli/synth.py` → `engine/registry.py` → `engine/subprocess_engine.py` |
| 共通の型 | `engine/types.py` |
| エンジンの抽象 | `engine/interface.py` |
| runner の書き方 | `engine/runners/interface.py` → `chatterbox_runner.py`（最短） |
| まとめて合成 | `engine/jobs.py` |
| 台本の文法 | `engine/script.py` の docstring |
| GUI | `gui/main_controller.py` → `main_view.py` → `main_model.py` |

## よくある変更

### エンジンを 1 つ足す

1. `engine_env/<name>/pyproject.toml` と `mise.toml` を作る
   （`mise.toml` は `UV_PROJECT_ENVIRONMENT` を `.venvs/engine-<name>` に向ける）
2. `engine/runners/<name>_runner.py` に `EngineRunner` の実装を書く。
   最短の例は `chatterbox_runner.py`（120 行）
3. `definitions.py` の `EngineType` に 1 行足す
4. `tool_config.py` の `ENGINE_DEFINITIONS` に定義を足す。
   `capabilities` は**実際に効くものだけ**を書く（効かないものを書くと
   黙って無視される不具合になる）
5. `scripts/win/setup_engines.ps1` に構築手順を足す
6. `docs/setup/0N_<name>.md` を書く

共通層は 1 行も触りません。

### 共通インターフェースに項目を足す

1. `engine/types.py` の `SynthesisRequest` にフィールドと `to_payload()` を足す
2. 対応状況を表すなら `Capability` に 1 つ足す
3. `engine/interface.py` の `validate()` に未対応時のエラーを足す
4. 各 runner で読む
5. `cli/common.py` の `add_voice_args()` と、GUI の該当タブに入力欄を足す

### 生成パラメータを調整する

`tool_config.py` の `ENGINE_DEFINITIONS[...].options` を変える。
runner が `options.get(...)` で読むので、コードを直す必要はありません。

### 台本の文法を広げる

`engine/script.py` の `_LINE_OPTION_KEYS` / `_CAST_KEYS` に足し、
`_parse_line_options()` と `Script.to_request()` で読む。
`tests/test_script.py` にケースを足す。

## テスト

```powershell
.\.venvs\common\Scripts\python.exe -m pytest -q
```

モデルを使わずに通ります。`tests/fake_runner.py` が
`engine/runners/interface.py` をそのまま使うダミーになっていて、
JSONL のやり取り・UTF-8・失敗からの復帰・未対応パラメータの拒否を
確認しています。エンジンを足したときも、ここが通れば共通層の側は健全です。

## デバッグ

| 症状 | 見るところ |
|---|---|
| エンジンが起動しない | `-m ttstoolkit.cli.doctor` |
| 合成が失敗する | `--verbose` を付けて runner の stderr を見る |
| JSON 以外が stdout に出たと言われる | runner に `print()` を足していないか |
| 出力が行方不明 | 相対パスを渡していないか（`SynthesisRequest` が絶対化する） |
| GUI が固まる | 重い処理を `TaskRunner` に載せているか |

## やらないこと

- `references/` は設計の参考として置いてあるだけなので**編集しない**
- `engine_env/irodori/vendor/` は上流の clone。手を入れるなら
  `patch_vendor.py` 経由にする（冪等に保つ）
- Python 本体にライブラリを入れない。すべて `.venvs/` の中へ
