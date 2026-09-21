# コードガイド

コードを読む・直すための案内。なぜこの形なのかは
[architecture.md](architecture.md) を参照。

---

## 1. どこから読むか

目的別の入口。

| 知りたいこと | 読むファイル |
|---|---|
| どんなデータが流れるか | `python/tts_sample/types.py` |
| エンジン共通の約束 | `python/tts_sample/engine.py` |
| プロセス間のやり取り | `python/tts_sample/subprocess_engine.py` |
| モデルをどう呼んでいるか | `python/engines/<name>/runner.py` |
| コマンドの処理 | `python/tts_sample/cli.py` |
| 台本の文法 | `python/tts_sample/script.py` |

初見なら `types.py` → `engine.py` → `subprocess_engine.py` の順。
この 3 つで全体の骨格が分かる。

### 規模

```
cli.py                 449 行   5 つのサブコマンド
__main__.py              9 行   python -m tts_sample の入口
script.py              299 行   cast.toml と台本のパース
subprocess_engine.py   293 行   プロセス間通信
types.py               172 行   データ型と例外
engine.py              117 行   抽象と検証
config.py               89 行   engines.toml の読み込み
registry.py             35 行   エンジンの生成

runner_base.py         140 行   runner 側のプロトコル
qwen/runner.py         183 行
irodori/runner.py      148 行
chatterbox/runner.py    85 行

tests/                 467 行   30 件
```

---

## 2. データの流れ

### 1 件合成するとき

```
cli.cmd_synth
  └─ SynthesisRequest を組む
  └─ registry.create_engine("irodori")        engines.toml を読む
       └─ SubprocessEngine(spec)
  └─ engine.synthesize(request)
       ├─ TTSEngine.validate(request)          ← 未対応ならここで例外
       ├─ output_path.parent.mkdir()
       └─ SubprocessEngine._synthesize()
            ├─ start()                         ← 初回だけ。プロセス起動 + ready 待ち
            ├─ _write_message({"op":"synthesize", ...})
            └─ _read_message()  →  SynthesisResult
```

### runner の側

```
runner.py が起動
  └─ runner_base を import       ← sys.stdout を stderr へ退避
  └─ torch とモデルライブラリを import
  └─ serve(EngineRunner)
       ├─ EngineRunner(options)   ← モデル読み込み
       ├─ send({"op":"ready"})
       └─ stdin をループ
            ├─ synthesize → runner.synthesize(message) → wav 書き出し
            └─ shutdown  → 終了
```

### 台本のとき

```
cli.cmd_script
  └─ script.load_script(cast.toml, script.txt)
       ├─ parse_cast()    → {名前: Voice}
       └─ parse_script()  → Script(lines=[ScriptLine, ...])
  └─ エンジンごとに台詞を束ねる
  └─ エンジンごとに 1 プロセス起動して全台詞を処理
  └─ _write_script_manifest()  ← 台本順に並べ直して start_sec を積む
```

---

## 3. 主要な型

すべて `python/tts_sample/types.py`。frozen dataclass で不変。

### SynthesisRequest

全エンジン共通の入力。

```python
@dataclass(frozen=True)
class SynthesisRequest:
    text: str
    output_path: Path
    language: str | None = None        # "ja" | "en"
    reference_audio: Path | None = None
    reference_text: str | None = None  # Qwen のクローンだけが使う
    voice_design: str | None = None    # 文章による声の設計
    seed: int | None = None
    speed: float = 1.0
```

`to_payload()` が runner へ送る dict を返す。`Path` はここで文字列になる。

> `reference_text` が共通 IF にあるのは Qwen の都合。`generate_voice_clone` は
> 参照音声の書き起こしがあると ICL モードで品質が上がり、無いと
> `x_vector_only_mode` に落ちる。他の 2 エンジンは使わない。

### Capability

エンジンが何に対応しているかのフラグ。`engines.toml` の
`capabilities = [...]` が文字列でこれを指す。

```python
class Capability(Flag):
    NONE = 0
    CLONE = auto()         # 参照音声によるクローン
    SPEED = auto()         # 話速
    SEED = auto()          # シード固定
    MULTILINGUAL = auto()  # 日本語以外
    VOICE_DESIGN = auto()  # 文章による声の設計
```

### EngineSpec

`engines.toml` の 1 エントリ。パスは読み込み時に絶対パスへ解決される。

```python
@dataclass(frozen=True)
class EngineSpec:
    name: str
    capabilities: Capability
    languages: tuple[str, ...]
    model_id: str
    python: Path       # .venvs/<name>/Scripts/python.exe
    runner: Path       # runner.py の絶対パス
    cwd: Path          # runner を起動する作業ディレクトリ
    options: dict      # runner へ素通しする設定
    ...
```

### 例外

`TTSError` を基底に、原因が分かる名前で分けてある。

```
TTSError
├─ EngineNotFoundError       engines.toml に無いエンジン名
├─ EngineNotInstalledError   仮想環境が未構築
├─ UnsupportedParameterError 未対応のパラメータ
├─ UnsupportedLanguageError  未対応の言語
├─ EngineProcessError        runner の起動・通信・合成の失敗
└─ ScriptError               台本・キャスト定義の書式（script.py で定義）
```

CLI はこれらを捕まえて `エラー: ...` の 1 行にする。
トレースバックは出さない（runner 側の traceback は `EngineProcessError` の
メッセージに含まれている）。

---

## 4. よくある変更

### 4.1 エンジンを追加する

共通層のコードは触らない。4 ファイルで完結する。

**① 依存を書く** — `python/engines/<name>/pyproject.toml`

```toml
[project]
name = "tts-engine-<name>"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = ["<the-tts-package>", "soundfile>=0.12", "torch", "torchaudio"]

# PyPI の torch は Windows では CPU 版になるので索引を明示する
[tool.uv.sources]
torch = [{ index = "pytorch-cu128" }]
torchaudio = [{ index = "pytorch-cu128" }]

[[tool.uv.index]]
name = "pytorch-cu128"
url = "https://download.pytorch.org/whl/cu128"
explicit = true
```

**② 仮想環境の場所を指定する** — `python/engines/<name>/mise.toml`

```toml
[env]
UV_PROJECT_ENVIRONMENT = "{{env.TTS_REPO_ROOT}}/.venvs/engine-<name>"
```

**③ runner を書く** — `python/engines/<name>/runner.py`

```python
import sys
import time
from pathlib import Path

# torch より前に import すること（stdout を退避するため）
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import runner_base  # noqa: E402
from runner_base import log, serve, write_wav_pcm16  # noqa: E402

runner_base.set_engine_name("<name>")

import torch  # noqa: E402
from the_tts_package import TheModel  # noqa: E402


class TheRunner:
    def __init__(self, options: dict) -> None:
        self.options = options
        self.model = TheModel.from_pretrained(...)   # engines.toml の options を使う

    @property
    def model_id(self) -> str:
        return "..."

    def synthesize(self, message: dict) -> dict:
        started = time.monotonic()
        wav, sample_rate = self.model.generate(message["text"])
        frames = write_wav_pcm16(message["output_path"], wav, sample_rate)
        return {
            "sample_rate": sample_rate,
            "duration_sec": frames / sample_rate,
            "elapsed_sec": time.monotonic() - started,
        }


if __name__ == "__main__":
    sys.exit(serve(TheRunner))
```

**④ 登録する** — `python/engines.toml`

```toml
[<name>]
description = "..."
venv = ".venvs/engine-<name>"
runner = "python/engines/<name>/runner.py"
cwd = "python/engines/<name>"
setup_doc = "04_<name>.md"
languages = ["ja", "en"]
capabilities = ["CLONE", "SEED", "MULTILINGUAL"]
model_id = "..."

[<name>.options]
device = "cuda"
```

最後に仮想環境を作る。

```powershell
cd python\engines\<name>
mise exec -- uv sync
```

### 4.2 共通インターフェースに項目を足す

Voice Design を足したときの実例。触るのは 5 か所。

| ファイル | 変更 |
|---|---|
| `types.py` | `Capability.VOICE_DESIGN` と `SynthesisRequest.voice_design` を足す。`to_payload()` にも入れる |
| `engine.py` | `validate()` に「未対応なら例外」を足す |
| `cli.py` | `--voice-design` を追加。`_CAP_ORDER` に足すと `tts engines` の表に出る |
| `engines.toml` | 対応するエンジンの `capabilities` に足す |
| 各 `runner.py` | `message.get("voice_design")` を読む |

`BatchItem` と `script.py` の `Voice` にも同名のフィールドを足せば、
バッチと台本からも使えるようになる。

### 4.3 生成パラメータを調整する

`engines.toml` の `[<engine>.options]` を編集するだけ。
仮想環境の作り直しは要らず、次の実行から反映される。

```toml
[chatterbox.options]
cfg_weight = 0.7      # 上げると読み飛ばしが減る
temperature = 0.6     # 下げると安定する
```

`options` は共通層が解釈せず JSON にして runner へ渡る。
runner 側で `self.options.get("cfg_weight", 0.5)` のように読む。

### 4.4 台本の文法を拡張する

行オプションを足すなら `script.py` の 2 か所。

```python
LINE_OPTION_KEYS = {"id", "speed", "seed", "lang"}   # ここに足す
```

```python
ScriptLine(
    ...
    新しい項目=opts.get("新しいキー"),                # ここで拾う
)
```

`Script.to_request()` で `SynthesisRequest` に渡す。
未知のキーは自動で弾かれる（綴り間違いが黙って無視されないようにするため）。

---

## 5. 書くときの約束

### 5.1 runner の stdout を汚さない

**最重要。** stdout は JSON 専用のチャネル。`print()` を足すとプロトコルが壊れる。

```python
log("進捗メッセージ")     # ○ stderr へ出る
print("進捗メッセージ")   # △ runner_base が stderr に差し替えているので実害はないが log() を使う
```

`runner_base` を import する前に torch などを import すると、
そのライブラリの import 時ログが本物の stdout に出てしまう。
**import の順序は変えないこと。** `# noqa: E402` はそのための印。

### 5.2 未対応を黙って無視しない

エンジンが対応していないパラメータが来たら、必ず例外にする。
無視すると「指定したのに効いていない」という最も気づきにくい不具合になる。

判定は `engine.validate()`（共通層、プロセス起動前）に書く。
runner 側でしか判定できないものだけ runner に書く。

### 5.3 エンコーディングを明示する

Windows の既定は cp932。省略すると日本語が壊れる。

```python
path.read_text(encoding="utf-8")            # ○
path.write_text(s, encoding="utf-8", newline="\n")
subprocess.Popen(..., encoding="utf-8")     # ○
```

`newline="\n"` は改行コードを LF に保つため。付けないと CRLF に変換され、
diff が全行になる。

### 5.4 失敗を握り潰さない

runner は 1 件失敗しても止まらないが、**失敗は必ず親へ返す**。

```python
except Exception as exc:  # noqa: BLE001 - 1 件の失敗で常駐を止めない
    log(traceback.format_exc())
    send({"id": ..., "ok": False, "error": str(exc), "traceback": traceback.format_exc()})
```

親は `EngineProcessError` に traceback と stderr 末尾を載せる。

### 5.5 コメントは「なぜ」を書く

「何をしているか」はコードが語る。コメントには判断の理由を書く。

```python
# ○ なぜそうしたかが書いてある
# 台詞ごとにプロセスを立て直すとモデルの読み込みを何度も払うことになる。
# エンジン単位でまとめて処理し、台本順は後で組み直す。

# × コードを読めば分かる
# エンジンごとに辞書へ追加する
```

---

## 6. テスト

```powershell
cd python
..\.venvs\common\Scripts\python.exe -m pytest tests\ -q
```

30 件。すべて**モデルを読み込まずに**動く。

| ファイル | 対象 |
|---|---|
| `tests/fake_runner.py` | 本物と同じ規約でふるまうダミー runner |
| `tests/test_protocol.py` | プロセス間通信（12 件） |
| `tests/test_script.py` | キャスト定義と台本のパース（18 件） |

### fake_runner の役割

本物の runner と同じ規約（stdout は JSON だけ、ログは stderr、常駐ループ）で
動くダミー。これを使うことで、10GB のモデルを落とさずに次を検証できる。

- 日本語と絵文字が UTF-8 のまま往復すること
- 1 プロセスで複数件を処理できること
- runner の `print()` が stdout を汚してもプロトコルが壊れないこと
- 未対応パラメータがプロセス起動前に弾かれること
- 1 件失敗しても次の件を処理できること
- `close()` が多重呼び出しでも安全なこと

`options` に `fail_on_text` を渡すと、その台詞で意図的に失敗する。
失敗系のテストはこれを使う。

### 実モデルを含む確認

テストの対象外。手で通す。

```powershell
# function tts { & "$PWD\.venvs\common\Scripts\python.exe" -m tts_sample @args } を定義した前提
tts doctor                                    # 3 エンジンが CUDA OK か
tts synth --engine <name> --text "..." ...    # 3 エンジンで実合成
tts script --cast ... --script ...            # 台本
```

---

## 7. lint と format

```powershell
cd python
..\.venvs\common\Scripts\ruff.exe check .
..\.venvs\common\Scripts\ruff.exe format .
```

設定は `python/pyproject.toml`。

```toml
[tool.ruff.lint]
# E402 を有効にしているのは、runner.py が「torch より前に stdout を退避する」ために
# わざと import を遅らせており、その意図を noqa で明示したいため。
extend-select = ["E", "I", "SIM", "PL", "RUF", "C4"]
ignore = ["RUF001", "RUF002", "RUF003"]   # 日本語の全角記号の警告は不要
```

`vendor/` は上流の clone なので対象外にしてある。

---

## 8. デバッグ

### エンジンのログを見る

```powershell
tts synth --engine qwen --text "テスト" --out outputs\x.wav --verbose
```

runner の stderr がそのまま流れる。モデルの読み込み、生成の進捗、
ライブラリの警告がここに出る。

### runner を単体で動かす

共通層を通さず、直接プロトコルを喋らせる。

```powershell
echo '{"op":"synthesize","id":1,"text":"テスト","output_path":"outputs/x.wav","language":"ja","speed":1.0}' | `
  .\.venvs\engine-irodori\Scripts\python.exe python\engines\irodori\runner.py --options '{}'
```

`ready` の行が出ればモデルの読み込みまでは成功している。

### タイムアウトを延ばす

| 環境変数 | 既定（秒） | 用途 |
|---|---:|---|
| `TTS_SAMPLE_READY_TIMEOUT` | 1800 | モデル読み込み（初回は重みの DL 込み） |
| `TTS_SAMPLE_SYNTH_TIMEOUT` | 900 | 1 件の合成 |

### よくある失敗の読み方

| メッセージ | 意味 |
|---|---|
| `runner が JSON 以外を stdout に出力しました` | エンジン側が stdout にログを出した。`runner_base` の import 順を確認 |
| `runner が起動中に終了しました (exit=...)` | モデルの読み込みで落ちた。stderr 末尾が例外に載っている |
| `runner は成功を報告しましたが出力がありません` | runner が `output_path` に書いていない |
| `応答の id が一致しません` | プロトコルがずれた。runner が余計な行を出している |

---

## 9. 触るときの注意

### 上流の clone（`python/engines/irodori/vendor/`）

git 管理外で、`patch_vendor.py` が 3 点だけ変更している。

| 変更 | 理由 |
|---|---|
| `.python-version` を 3.12 に | プロジェクト全体で揃えるため |
| `sentencepiece>=0.2.0` の上書き | 0.1.99 に cp312 の Windows wheel が無い |
| `mise.toml` の作成 | 仮想環境を `.venvs/engine-irodori` に作らせる |

`patch_vendor.py` は冪等で、clone し直したら再実行する。
手で編集した内容は clone し直すと消えるので、必要な変更は
`patch_vendor.py` 側に書くこと。

### `engines.toml` のパス

**リポジトリのルートからの相対パス**で書く。
仮想環境は `.venvs/` に、runner は `python/engines/` にと別の枝へ散るので、
両方を素直に書ける位置を基準にしてある。

解決は `config.repo_root()` が行う。

### torch を共通層に持ち込まない

`python/pyproject.toml` の `dependencies` は空のまま保つ。
ここに torch が入ると、GUI や Remotion 連携から使うときに
巨大な依存を引きずることになる。

音声を触る処理は runner 側（`runner_base.py` か各 `runner.py`）に書く。
