# 全体構成

```
python/
└─ ttstoolkit/   CLI・GUI・エンジンをまとめたパッケージ
```

## 出発点になった 3 つの制約

構成の大半は、次の 3 つから逆算して決まっている。

### 1. 3 モデルの依存は排他的で、1 つの仮想環境に同居できない

| モデル | 入手方法 | transformers | torch |
|---|---|---|---|
| Qwen3-TTS | `qwen-tts` (PyPI) | `==4.57.3` | cu128 系 |
| Chatterbox | GitHub 固定コミット | `==5.2.0` | `==2.6.0` |
| Irodori-TTS | GitHub clone のみ | `>=5.12.1,<6` | `>=2.10.0,<2.11.0` |

extras で切り替える単一環境は成立しない。**プロセス分離が必須**で、
それが `engine/subprocess_engine.py` の存在理由になっている。

### 2. Irodori-TTS は pip install できない

PyPI 未公開で、依存の `dacvae` も PyPI に無い。さらに uv の
`[tool.uv.sources]`（CUDA 索引の指定）は依存先プロジェクトに継承されないため、
git 依存として取り込むと PyTorch が CPU 版になる。

そのため上流リポジトリを `engine_env/irodori/vendor/` へ clone し、
**そのリポジトリ自身の `uv sync` で環境を作る**。clone は非パッケージ扱いで
仮想環境には入らないので、`tool_config.py` が clone の場所を runner の
検索パス（`EngineSpec.python_path`）に足している。

### 3. Blackwell (RTX 50 系 / sm_120) で動く必要がある

Chatterbox がピンする torch 2.6.0 には sm_120 カーネルが無い。
`engine_env/chatterbox/pyproject.toml` の `override-dependencies` で
2.7.1+cu128 に引き上げている。

## python/ttstoolkit — アプリケーションパッケージ

合成も台本の解釈もここにあります。**画面出力もプロセス終了もしない**のが
約束で、そのおかげで CLI からも GUI からも同じ API を呼べます。

| 決まりごと | 理由 |
| --- | --- |
| `print()` しない。進捗は `logging` の `ttstoolkit` 名前空間へ | 呼ぶ側が Handler を差し替えるだけで出力先を変えられる |
| `sys.exit()` しない。失敗は `TTSToolkitError` | GUI から呼んだときにプロセスが落ちない |
| 長い処理は `on_progress` / `is_canceled` を受け取る | 進捗表示と協調キャンセルに使える |
| 既定値は dataclass (`EngineSpec` など) が持つ | CLI と GUI で既定がずれない |

```
ttstoolkit/
├─ main.py             ← GUI の起点。QApplication を作って Controller を起動
├─ tool_config.py      ツールの設定と ENGINE_DEFINITIONS
├─ definitions.py      画面に並べる選択肢の Enum
├─ logger.py           logging を Qt のシグナルへ中継
├─ cli/                コマンドラインの入口（1 コマンド 1 ファイル）
│   ├─ common.py           共通の引数・ログ処理
│   ├─ synth.py            ① 1 件合成
│   ├─ batch.py            ② JSON をまとめて合成
│   ├─ script.py           ③ 台本をまとめて合成
│   ├─ engines.py          エンジン一覧
│   └─ doctor.py           環境チェック
├─ gui/                Model / View / Controller と画面部品
└─ engine/             CLI / GUI 共用の処理本体
    ├─ interface.py        ← TTSEngine (ABC)。共通インターフェース
    ├─ types.py            受け渡すデータクラスと例外
    ├─ subprocess_engine.py runner をサブプロセスで駆動する実装
    ├─ registry.py         名前 → TTSEngine
    ├─ jobs.py             まとめて合成する処理と manifest
    ├─ script.py           キャスト定義と台本の解釈
    ├─ runners/            各モデルの仮想環境で動く小さなプログラム
    │   ├─ interface.py        ← EngineRunner (ABC) と JSONL の通信
    │   ├─ qwen_runner.py
    │   ├─ chatterbox_runner.py
    │   └─ irodori_runner.py
    ├─ paths.py            入出力フォルダとエンジン環境の解決
    └─ settings.py         OS 差分 / 例外 / ロガー
```

## 2 つのインターフェース

名前が似ているが役割が違う。

| | `engine/interface.py` | `engine/runners/interface.py` |
|---|---|---|
| 抽象 | `TTSEngine` | `EngineRunner` |
| 動く場所 | 共通層（`.venvs/common`） | 各エンジンの仮想環境 |
| 実装 | `SubprocessEngine` | `QwenRunner` / `ChatterboxRunner` / `IrodoriRunner` |
| 見ているもの | プロセスの起動と JSONL | モデルの API |

`TTSEngine` は「どのモデルでも同じ呼び方ができる」ための抽象で、
`EngineRunner` は「どのモデルでも同じ書き方で足せる」ための抽象。
エンジンを 1 つ増やすときに書くのは後者だけで、共通層は触らない。

```python
from ttstoolkit.engine.registry import create_engine
from ttstoolkit.engine.types import SynthesisRequest

with create_engine("irodori") as engine:
    result = engine.synthesize(
        SynthesisRequest(text="こんにちは。", output_path="output/a.wav")
    )
```

## サブプロセスのプロトコル

1 行 1 JSON（JSONL）、UTF-8。

```
runner -> 親  {"op": "ready", "model_id": "..."}
親 -> runner  {"op": "synthesize", "id": 1, "text": ..., ...}
runner -> 親  {"id": 1, "ok": true, "sample_rate": 48000, ...}
runner -> 親  {"id": 1, "ok": false, "error": "...", "traceback": "..."}
親 -> runner  {"op": "shutdown"}
```

壊れやすい箇所と、その対策。

| 壊れ方 | 対策 |
|---|---|
| ライブラリが stdout にログを出して JSON が混ざる | `runners/interface.py` が import 時に `sys.stdout` を `stderr` へ差し替え、退避した本物のハンドルだけで JSON を書く |
| Windows の cp932 で日本語が壊れる | 子プロセスの環境に `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1` を入れ、パイプも `encoding="utf-8"` で開く |
| stderr を読まずにパイプが詰まって子が固まる | 専用スレッドで読み続け、末尾 60 行だけ保持する |
| Windows のパイプ読み取りにタイムアウトを掛けられない | 読み取りをスレッドへ逃がし、`join(timeout)` で打ち切る |
| runner が死んでも親が待ち続ける | `readline()` が空を返したら終了として扱い、stderr の末尾を添えて報告する |

## 設計判断

### モデルは常駐させる

1 件ごとにプロセスを立て直すとロード（10〜60 秒）を毎回払う。runner は
`shutdown` を受けるまで常駐し、`with` の中なら何件でも同じプロセスが処理する。
台本合成では**エンジン単位でまとめて**流し、台本順は manifest で組み直している。

### `__enter__` では `start()` しない

未対応の言語やパラメータは `TTSEngine.validate()` が弾く。これを起動より前に
効かせたいので、プロセスの起動は最初の `synthesize()` まで遅延する。おかげで
「Irodori に英語」は 0.14 秒でエラーになる（起動していたら 18 秒かかる）。

### 未対応パラメータは黙殺せずエラーにする

指定したのに効いていない、が最も気づきにくい不具合になるため。対応状況は
`Capability` フラグで宣言し、`validate()` が `UnsupportedParameterError` を投げる。

### パスは `SynthesisRequest` が絶対パスに直す

runner は別のカレントディレクトリで動く（Irodori は clone の中）。相対パスの
まま渡すと書き出し先が runner 側の基準になって行方不明になるので、
`__post_init__` で絶対パスに正規化している。

### 出力は PCM16 に統一する

エンジンによって float32 WAV だったり 24/48kHz だったりすると、下流での
扱いが揃わない。`write_wav_pcm16()` を全 runner が使い、サンプリングレート
だけモデル本来の値を保つ。

### 仮想環境はリポジトリ直下の `.venvs/` に集める

置き場は各 `mise.toml` の `UV_PROJECT_ENVIRONMENT` が指定している。定義
（`engine_env/<name>/pyproject.toml`）と実体（`.venvs/engine-<name>`）を
分けることで、どこで `uv sync` しても同じ場所に作られる。

## GUI

手書き MVC です。

```
gui/
├─ main_model.py       engine の呼び出しと QSettings への保存
├─ main_view.py        タブとログの組み立て
├─ main_controller.py  View と Model の接続
├─ task_runner.py      時間のかかる処理を回す QThread
└─ widgets/
    ├─ option_rows.py        入力行と共通のエンジン選択
    ├─ tab_buttons.py        Run / Cancel の行
    ├─ synthesis_tab.py      ① テキストから合成
    ├─ voice_design_tab.py   ② オリジナルの声を作る
    └─ script_tab.py         ③ 台本からまとめて合成
```

### 役割分担

- **View** は Qt のウィジェットだけを持ちます。Model を知らず、Controller への
  通知はクラス変数の `Signal` (`on_*_signal`)。ダイアログは View 側
  (`show_confirm_dialog()` は bool を返すだけ)。
- **Model** は `engine` パッケージの呼び出しと `QSettings` への保存を持ちます。
  Qt のウィジェットには触りません。
- **Controller** が両方を作り、`__setup_connections()` で View の Signal を
  `__on_*` ハンドラに繋ぎます。Controller の存在は他のどこも知りません。

### 実行の流れ

```
Run 押下
  → View が Request dataclass を emit
  → Controller: エンジンが未構築なら案内ダイアログ、初回なら DL の確認
  → Controller: View.set_running(True) → TaskRunner を起動
  → 進捗: TaskRunner.on_progress_signal → View.append_log()
          ttstoolkit ロガー → logger.LogBridge → 同じログ欄
  → 完了 / 失敗: on_finished_signal / on_error_signal
```

### スレッドとキャンセル

合成は `TaskRunner` (QThread) で回します。生成中の 1 件を途中で止める手段は
どのモデルにも無いので、キャンセルは**次の 1 件に入る前**に効く協調式です
(`engine/jobs.py` が `is_canceled()` をループの先頭で見ている)。

## import のルール

`ttstoolkit` は `.venvs/common` に editable で入るので、共通層と GUI は
そのまま import できます。runner だけは別の仮想環境で動くため、
`SubprocessEngine` が `PYTHONPATH` に `python/` を渡しています。
**コードから `sys.path` は変更しません。**

| 場所 | 書き方 |
| --- | --- |
| `gui/` の中で兄弟を参照 | 絶対 (`from ttstoolkit.gui.main_model import ...`) |
| サブパッケージをまたぐ参照 | 絶対 (`from ttstoolkit.engine.registry import ...`) |
| `cli/` から共通処理 | 絶対 (`from ttstoolkit.cli.common import ...`) |

`__init__.py` は置きません（暗黙の名前空間パッケージ）。そのため
`from ttstoolkit import create_engine` のような再エクスポートは無く、
常に定義元のモジュールから import します。

## 見た目

配色とサイズは `resources/ui/stylesheet.qss` にまとめ、Python 側は
`setProperty("class", ...)` でタグを付けるだけにしています。

- 背景 `#090a0d` / パネル `#0f1216` / グループ `#14171c` / 入力欄 `#0b0d11`
- 文字 `#ecedf0`、補助 `#9ea6b2`、無効 `#5b626d`
- アクセント青 `#1f6be5`、ボタン青 `#1a3d85`

`{RESOURCES_DIR}` プレースホルダは `ToolConfig.load_stylesheet()` が
`resources/` の絶対パスへ置換します（QSS の `url()` はカレントディレクトリ基準で
解決されてしまうため）。

## 意図的にやっていないこと

| やっていないこと | 理由 |
|---|---|
| 3 モデルを 1 つの仮想環境に入れる | 依存が排他的で不可能 |
| 共通層が torch に依存する | CLI / GUI の起動が重くなり、GUI だけ使いたい場合にも 3GB 入る |
| 未対応パラメータの暗黙のフォールバック | 効いていないことに気づけない |
| 生成中の 1 件を途中で止める | モデル側にフックが無い |
| 常駐 HTTP サーバ | 今の用途ではサブプロセスで足りる。必要になったら `TTSEngine` の実装を足す |

## 増やすときの入口

| したいこと | 触る場所 |
|---|---|
| エンジンを 1 つ足す | `engine_env/<name>/`、`engine/runners/<name>_runner.py`、`tool_config.ENGINE_DEFINITIONS` |
| 共通 IF に項目を足す | `engine/types.py` → `engine/interface.py` の `validate()` → 各 runner |
| HTTP バックエンドを足す | `engine/interface.py` を実装し、`engine/registry.py` に分岐を 1 つ |
| GUI にタブを足す | `gui/widgets/<name>_tab.py` → `main_view` / `main_model` / `main_controller` |

手順は [../instructions/code_guide.md](../instructions/code_guide.md) にあります。
