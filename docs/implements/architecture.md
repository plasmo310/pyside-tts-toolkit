# アーキテクチャ

このリポジトリがなぜこの形になっているか。設計の判断と、その根拠になった制約。

コードの読み方・書き方は [code_guide.md](code_guide.md) を参照。

---

## 1. 出発点にあった制約

### 1.1 3 モデルの依存は互いに排他的

最初に調べて分かったのが、これが**回避できない**制約だということ。

| モデル | 入手方法 | transformers | torch |
|---|---|---|---|
| Qwen3-TTS | `pip install qwen-tts` | `==4.57.3` | 未ピン → 2.11.0+cu128 |
| Chatterbox | git（V3 は master のみ） | `==5.2.0` | `==2.6.0` → 2.7.1+cu128 に上書き |
| Irodori-TTS | git clone（PyPI 未公開） | `>=5.12.1,<6` | `>=2.10.0,<2.11.0` |

`transformers` の 3 つのピンに共通解はない。extras で切り替える単一環境も、
同じインタプリタに入る以上は成立しない。

**→ プロセスを分けるしかない。** これが全体の構造を決めた。

### 1.2 Irodori は pip install できない

PyPI 未公開で、依存の `dacvae` も PyPI に無い（404）。さらに uv の
`[tool.uv.sources]`（CUDA 索引の指定）は依存先プロジェクトに継承されないため、
git 依存として取り込むと PyTorch が CPU 版になる。

**→ 上流リポジトリを clone して、その依存解決をそのまま使う。**

### 1.3 GPU は Blackwell（RTX 50 系 / sm_120）

Chatterbox がピンする torch 2.6.0 のビルドは cu124 / cu126 までで `sm_120` を含まない。
実行時に `no kernel image is available for execution on the device` になる。

**→ Chatterbox だけ torch を 2.7.1+cu128 に上書きする。**
`sm_120` を含む最初の系列がここ。

### 1.4 将来 GUI と Remotion から使う

当初の要件（`docs/plan/plan_base.md`）に「将来的には GUI を用意することも考慮する」とある。
調査結果（`docs/references/`）では Remotion 連携が主目的。

**→ 共通層を torch から切り離しておく。** GUI や Node 側から呼ぶときに、
巨大な依存を引きずらない形にする。

---

## 2. 全体の構造

```
  ┌─────────────────────────────────────────────────────┐
  │  python -m tts_sample / Python API   .venvs/common    │
  │  torch に依存しない。標準ライブラリのみ              │
  │                                                     │
  │   __main__.py ── cli.py ── script.py                │
  │      │                                              │
  │   registry.py ── config.py ── engines.toml          │
  │      │                                              │
  │   TTSEngine（抽象）                                  │
  │      └─ SubprocessEngine                            │
  └──────────────────┬──────────────────────────────────┘
                     │  標準入出力 / 1 行 1 JSON / UTF-8
     ┌───────────────┼───────────────┐
     ▼               ▼               ▼
 .venvs/         .venvs/         .venvs/
 engine-qwen     engine-         engine-irodori
                 chatterbox
 runner.py       runner.py       runner.py
 qwen-tts        chatterbox-tts  irodori_tts
 transformers    transformers    transformers
 4.57.3          5.2.0           5.12.x
 torch 2.11      torch 2.7.1     torch 2.10
```

共通層は**モデルを import しない**。エンジンごとの仮想環境にある `runner.py` を
サブプロセスとして起動し、標準入出力の JSON でやり取りする。

### この境界が生んでいるもの

| 効果 | 中身 |
|---|---|
| 依存の衝突が起きない | エンジンを足しても既存の環境に触れない |
| 共通層が軽い | `.venvs/common` には torch が入らない。GUI からそのまま使える |
| 差し替えが効く | HTTP バックエンドを足すなら `TTSEngine` の実装を 1 つ増やすだけ |
| 落ちても波及しない | runner が死んでも共通層は生きていて、次のリクエストで起動し直せる |

### 代償

| 代償 | 対処 |
|---|---|
| プロセス起動とモデル読み込みのコスト | runner を**常駐**させ、複数件を 1 プロセスで処理する |
| 構造化データを直接渡せない | JSON に落とす。音声はファイル経由でやり取りする |
| デバッグが 2 段になる | 失敗時に runner の stderr 末尾を例外に含める |

---

## 3. 主要な設計判断

### 3.1 サブプロセス方式を選んだ理由

プロセスを分ける方法は 2 つあった。

| 方式 | 内容 | 判断 |
|---|---|---|
| **サブプロセス** | runner を子プロセスとして起動し標準入出力で話す | **採用** |
| HTTP サーバ | 各モデルを常駐サーバにして REST で呼ぶ | 見送り |

HTTP は Remotion 連携には自然で、Irodori には公式の OpenAI 互換サーバもある。
それでもサブプロセスにしたのは、

- サーバの起動・終了・ポート管理を利用者に押し付けない
- Qwen と Chatterbox 用のサーバは自作が必要（Irodori だけ公式がある）
- サンプルとして読む量が少ない

後から HTTP に移れるよう、`TTSEngine` を抽象に置いて
`SubprocessEngine` はその実装のひとつにしてある。

### 3.2 runner を常駐させる

モデルの読み込みは 10〜60 秒かかる（初回は重みのダウンロードでさらに長い）。
台詞ごとにプロセスを立て直すとこれを毎回払うことになる。

そこでプロトコルを**1 リクエスト 1 往復ではなく、常駐ループ**にした。

```
親 → 子   起動
子 → 親   {"op":"ready", "model_id":"..."}     ← ここまででモデル読み込み完了
親 → 子   {"op":"synthesize", "id":1, ...}
子 → 親   {"id":1, "ok":true, ...}
親 → 子   {"op":"synthesize", "id":2, ...}     ← 読み込みは繰り返さない
子 → 親   {"id":2, "ok":true, ...}
親 → 子   {"op":"shutdown"}
```

実測（RTX 5070）では、台本 7 台詞・2 エンジンで読み込みは 2 回だけ発生した。

### 3.3 台本はエンジン単位でまとめて処理する

3.2 の帰結。台本が `qwen → irodori → qwen → irodori` と交互でも、
台本順に処理すると読み込みが 4 回走ってしまう。

そこで `cmd_script` は**エンジンごとに台詞を束ねて**処理し、
manifest を書くときに台本順へ並べ直す。

```python
by_engine = {}
for line in script.lines:
    by_engine.setdefault(script.cast[line.voice].engine, []).append(line)
```

このため進捗表示は台本順ではなくエンジンごとにまとまって出る。
直感には反するが、待ち時間のほうが体験を支配するのでこちらを取った。

### 3.4 未対応パラメータは共通層で弾く

3 エンジンは対応機能が揃っていない。

|  | 日本語 | 英語 | クローン | Voice Design | 話速 |
|---|:---:|:---:|:---:|:---:|:---:|
| qwen | ○ | ○ | ○ | ○ | × |
| chatterbox | ○ | ○ | ○ | × | × |
| irodori | ○ | **×** | ○ | ○ | ○ |

未対応を**黙って無視するのが最悪**という判断をした。「指定したのに効いていない」は
最も気づきにくい種類の不具合で、生成物を全部聴き直すまで分からない。

そこで `Capability` フラグを `engines.toml` に持たせ、`TTSEngine.validate()` が
リクエストを検査して例外を投げる。

```python
if request.voice_design is not None and not spec.supports(Capability.VOICE_DESIGN):
    raise UnsupportedParameterError(...)
```

検査は**共通層で、プロセスを起動する前に**行う。実測で、Irodori に英語を渡したときの
応答は 0.16 秒（モデルを読み込んでいたら 17.9 秒かかっていた）。

> このために `TTSEngine.__enter__` は `start()` を呼ばない。起動は最初の
> `synthesize()` まで遅延する。実装中、`with` に入った時点で起動していたため
> 検証が効かず 17.9 秒かかっていたのを直した経緯がある。

### 3.5 出力は PCM16 モノラルに統一する

当初は各ライブラリの保存関数に任せていたが、`torchaudio.save` が float32 WAV
（format tag 3）を書き、Python の `wave` モジュールで開けなかった。

エンジンごとに形式が違うと下流（Remotion、音声編集、検証スクリプト）で扱いが揃わない。
そこで `runner_base.write_wav_pcm16()` を共有し、**全エンジンが PCM16 モノラルで書く**。

サンプリングレートだけはモデル本来の値を保つ（Irodori 48 kHz / 他 24 kHz）。
リサンプルは情報を落とすので、下流の判断に委ねるほうが素直だと考えた。

### 3.6 声の定義と台詞を分ける

台本の入力形式を決めるとき、キャラクター定義を台詞と同じファイルに置くと、
**毎回書くもの（台詞）と一度だけ書くもの（声）が混ざる**。

```
cast.toml     声の定義。エンジン・参照音声・Voice Design・シード
script.txt    台詞だけ。「誰が」「何を」
```

台本側は話者名とコロンだけで書けるので、脚本をそのまま打てる。

台詞の形式に JSON や YAML ではなくプレーンテキストを選んだのは、

- 依存ゼロで済む（自前パーサ 100 行弱。共通層は標準ライブラリのみ）
- diff が読みやすい
- 台詞 1 行に対する記号の量が最小

### 3.7 仮想環境は `.venvs/` に集約する

`uv sync` の既定は各プロジェクト直下の `.venv`。それだと 4 つの環境が
リポジトリ中に散らばり、どれが何の環境か分からない。

`.venvs/common` `.venvs/engine-qwen` のように**名前で役割が分かる形**にまとめた。

置き場の指定は各プロジェクトの `mise.toml` が持つ。

```toml
# python/engines/qwen/mise.toml
[env]
UV_PROJECT_ENVIRONMENT = "{{env.TTS_REPO_ROOT}}/.venvs/engine-qwen"
```

`TTS_REPO_ROOT` はルートの `mise.toml` が `{{config_root}}` で定義している。
mise の設定はディレクトリ階層でマージされるので、サブディレクトリから
参照できる。この形にしたことで、手で `uv sync` しても同じ場所に作られる
（`mise exec --` を付けて実行する必要はある）。

---

## 4. プロトコル

`python/tts_sample/subprocess_engine.py` と
`python/engines/_shared/runner_base.py` が両端を実装している。

### 4.1 メッセージ

標準入出力を流れるのは **1 行 1 JSON、UTF-8** のみ。

```
runner → 親   {"op": "ready", "model_id": "..."}
親 → runner   {"op": "synthesize", "id": 1, "text": "...", "output_path": "...", ...}
runner → 親   {"id": 1, "ok": true, "sample_rate": 48000, "duration_sec": 2.6, ...}
runner → 親   {"id": 1, "ok": false, "error": "...", "traceback": "..."}
親 → runner   {"op": "shutdown"}
```

音声そのものは流さない。runner が `output_path` に書き、親はファイルの存在を確認する。
パイプに大きなバイナリを流す必要がなく、失敗時に途中まで書かれた wav が残って
原因を追える。

### 4.2 壊れやすい点と、その対処

この方式には壊れ方が決まっているので、先回りして潰してある。

| 壊れ方 | 対処 |
|---|---|
| ライブラリが stdout にログを出してプロトコルが壊れる | `runner_base` が import 時に `sys.stdout` を `stderr` に差し替え、本物のハンドルを退避する |
| Windows の既定が cp932 で日本語が壊れる | 親が `PYTHONIOENCODING` / `PYTHONUTF8` を設定し、パイプを `encoding="utf-8"` で開く |
| stderr のパイプが詰まって子が固まる | 親が専用スレッドで読み続け、末尾 60 行だけ保持する |
| 子が無応答になる | 読み取りをスレッドへ逃がし、`join` のタイムアウトで打ち切って `kill` |
| 子が `shutdown` に応じない | `wait(timeout)` → `kill` → `wait` の順で確実に終わらせる |

stdout の差し替えは特に重要で、`transformers` や `tqdm` は進捗を stdout に出す。
これを放置すると JSON パースが失敗し、原因が分かりにくい壊れ方をする。

```python
# runner_base.py — torch より前に import すること
_CHANNEL = sys.stdout
sys.stdout = sys.stderr
```

### 4.3 失敗の扱い

runner は**1 件の失敗でループを抜けない**。例外を捕まえて
`{"ok": false, "traceback": "..."}` を返し、次のリクエストを待つ。

親は `EngineProcessError` に runner の traceback と stderr 末尾を載せる。
プロセスをまたいでも原因が追えるようにするため。

---

## 5. モジュールの責務

### 共通層 `python/tts_sample/`

| モジュール | 責務 | 依存 |
|---|---|---|
| `types.py` | データ型と例外。`SynthesisRequest` / `SynthesisResult` / `Capability` / `EngineSpec` | なし |
| `engine.py` | `TTSEngine` 抽象。`validate()` で未対応を弾く | `types` |
| `subprocess_engine.py` | サブプロセス + JSONL の実装 | `engine`, `types` |
| `config.py` | `engines.toml` を読んで `EngineSpec` にする | `types`, `subprocess_engine` |
| `registry.py` | 名前 → `TTSEngine` を作る。バックエンドの選択点 | `config`, `subprocess_engine` |
| `script.py` | `cast.toml` と台本テキストのパース | `types` |
| `cli.py` | 5 つのサブコマンド | 上記すべて |

依存は一方向で、`types.py` が最下層。循環はない。

### エンジン側 `python/engines/`

| ファイル | 責務 |
|---|---|
| `_shared/runner_base.py` | プロトコルのループ、stdout の退避、PCM16 書き出し |
| `<engine>/pyproject.toml` | その環境の依存。ピンの上書きもここ |
| `<engine>/runner.py` | モデルの読み込みと合成。`model_id` と `synthesize()` だけ実装する |
| `<engine>/mise.toml` | 仮想環境を `.venvs/engine-<name>` に作らせる |
| `irodori/patch_vendor.py` | clone した上流リポジトリへの調整（冪等） |

`runner.py` はどれも 85〜183 行。プロトコルは `runner_base` が持つので、
各 runner はモデル固有の部分だけを書けばよい。

### 設定 `python/engines.toml`

エンジンの一覧・仮想環境の場所・対応機能・生成パラメータ。
**コードを変えずに調整できる範囲**をここに置いている。

```toml
[qwen]
venv = ".venvs/engine-qwen"                 # リポジトリのルートから
runner = "python/engines/qwen/runner.py"
cwd = "python/engines/qwen"
capabilities = ["CLONE", "SEED", "MULTILINGUAL", "VOICE_DESIGN"]
languages = ["ja", "en"]

[qwen.options]                              # runner へそのまま渡る
base_model = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
dtype = "bfloat16"
```

`options` の中身は共通層が解釈せず、JSON にして runner へ素通しする。
エンジン固有の設定を増やすときに共通層を触らずに済む。

---

## 6. ディレクトリ構成

```
mise.toml              Python 3.12 と uv の設定。TTS_REPO_ROOT の定義
.venvs/                仮想環境（git 管理外）
  common                 共通層。python -m tts_sample。torch なし
  engine-qwen            transformers 4.57.3
  engine-chatterbox      transformers 5.2.0
  engine-irodori         transformers 5.12.x
python/                Python のコードだけ
  pyproject.toml         共通層のパッケージ定義。pytest と ruff の設定
  engines.toml           エンジン定義
  mise.toml              .venvs/common を指す
  tts_sample/            共通層のパッケージ
  engines/               エンジンごとの環境と runner
  tests/                 モデル不要の検証
scripts/               セットアップ用 PowerShell
samples/               バッチ入力と台本の例
docs/                  手順書・解説・実装メモ・HTML
voices/                マスター音声（git 管理外）
outputs/               生成物（git 管理外）
```

### `python/` の中に `src/` を置かない

Python の src-layout は、インストール済みパッケージではなくカレントディレクトリの
ソースを誤って import するのを防ぐ慣習。ここでは採っていない。

`python/` 自体がソースの置き場で、その中でさらに `src/` を切ると
`tts_sample/` だけが `src/` に入り、同じくソースである `engines/*/runner.py` は
外に出る。**同じ性質のものが 2 か所に分かれる**ほうが害が大きいと判断した。

誤 import の懸念は、共通層が仮想環境にインストールされていて、
実行が `tts` コンソールスクリプト経由であることで実質的に消えている。

---

## 7. 意図的にやっていないこと

| やっていないこと | 理由 |
|---|---|
| 並列生成 | GPU が 1 枚なら同時実行しても速くならず、VRAM を圧迫する |
| 生成結果のキャッシュ | 台本の再生成は `id` 指定で部分的にやり直すほうが実態に合う |
| サンプリングレートの統一 | リサンプルは情報を落とす。manifest に実値を載せて下流に委ねる |
| 共通層での音声処理 | torch 非依存を保つため。音声を触るのは runner 側だけ |
| エンジンの自動選択 | 声の同一性が最優先なので、どのモデルを使うかは明示させる |
| Voice Design の指示文の正規化 | モデルごとに効き方が違い、共通化すると両方の良さが消える |

---

## 8. 今後の拡張点

### エンジンを足す

1. `python/engines/<name>/pyproject.toml` に依存を書く
2. `python/engines/<name>/mise.toml` で仮想環境の場所を指定する
3. `python/engines/<name>/runner.py` に `model_id` と `synthesize()` を書く
4. `python/engines.toml` にエントリを足す

共通層のコードは 1 行も触らない。

### HTTP バックエンドに移る

`TTSEngine` を実装した `HttpEngine` を足し、`registry.create_engine()` に
分岐を 1 つ増やす。`engines.toml` に `backend = "http"` と URL を持たせれば、
エンジンごとに方式を選べる。呼び出し側のコードは変わらない。

### 共通インターフェースに項目を足す

`SynthesisRequest` にフィールドを足し、`Capability` にフラグを足して
`engine.validate()` に検査を書く。各 runner は `message.get("新しいキー")` を読む。

Voice Design を追加したときが実例で、変更は
`types.py` / `engine.py` / `cli.py` / `engines.toml` と各 runner の数行で済んだ。
