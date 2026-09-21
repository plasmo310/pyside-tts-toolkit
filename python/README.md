# tts_sample

Qwen3-TTS / Chatterbox / Irodori-TTS を、入出力を共通化したラッパー越しに使うサンプルの
**コード部分**。使い方は [ルートの README](../README.md)、導入手順は
[docs/setup/](../docs/setup/) を参照。

このディレクトリには Python のコードだけを置く。生成物（`outputs/`）、
サンプルデータ（`samples/`）、セットアップスクリプト（`scripts/`）、
仮想環境（`.venvs/`）はリポジトリ直下にある。

パッケージは `src/` を挟まず `python/tts_sample/` に直接置いている。
`python/` 自体がソースの置き場なので、その中でさらに `src/` を切ると
`engines/` 配下の runner だけが外に出て一貫しなくなるため。

## 構成

```
python/
  pyproject.toml           共通層のパッケージ定義。pytest と ruff の設定もここ
  engines.toml             エンジン定義（venv パス、モデル ID、生成パラメータ）
  mise.toml                仮想環境を .venvs/common に作らせる設定
  tts_sample/              共通層（torch に依存しない）
    types.py               SynthesisRequest / SynthesisResult / Capability / 例外
    engine.py              TTSEngine（抽象。未対応パラメータの検証もここ）
    subprocess_engine.py   runner を常駐させ JSONL で駆動するバックエンド
    script.py              cast.toml と台本テキストの読み込み
    config.py              engines.toml の読み込み
    registry.py            名前 → TTSEngine の生成
    cli.py                 synth / script / batch / engines / doctor
  engines/
    _shared/runner_base.py プロトコルと PCM16 書き出しの共有実装
    qwen/                  pyproject.toml + runner.py + mise.toml
    chatterbox/            pyproject.toml + runner.py + mise.toml
    irodori/               runner.py + patch_vendor.py + vendor/Irodori-TTS/
  tests/
    fake_runner.py         本物と同じ規約でふるまうダミー runner
    test_protocol.py       プロトコルの検証
    test_script.py         台本パーサの検証
```

## 設計

3 モデルは `transformers` と `torch` のピンが互いに排他的なので、1 つの venv には
同居できない。共通層はモデルを import せず、エンジンごとの venv にある `runner.py`
をサブプロセスとして起動し、標準入出力の JSON でやり取りする。

```
tts_sample (.venvs/common, torch なし)
  └─ SubprocessEngine ── stdin/stdout JSONL ──┬─ .venvs/engine-qwen/python runner.py
                                              ├─ .venvs/engine-chatterbox/python runner.py
                                              └─ .venvs/engine-irodori/python runner.py
```

この境界のおかげで、将来 GUI や Remotion 連携から使うときも共通層をそのまま
再利用できる。HTTP バックエンド（Irodori-TTS-Server のような OpenAI 互換サーバ）を
足す場合も、`TTSEngine` を実装して `registry.py` に分岐を 1 つ増やすだけで済む。

プロトコルの詳細は `tts_sample/subprocess_engine.py` の docstring にある。

## 対応機能

|  | 日本語 | 英語 | クローン | Voice Design | 話速 | シード | レート |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---:|
| qwen | ○ | ○ | ○ | ○ | × | ○ | 24 kHz |
| chatterbox | ○ | ○ | ○ | × | × | ○ | 24 kHz |
| irodori | ○ | × | ○ | ○ | ○ | ○ | 48 kHz |

未対応のパラメータは黙って無視されず、`TTSEngine.validate()` が
モデルをロードする前にエラーにする。

## Python から使う

```python
from pathlib import Path
from tts_sample import create_engine, SynthesisRequest

with create_engine("irodori") as engine:
    result = engine.synthesize(
        SynthesisRequest(
            text="こんにちは。",
            output_path=Path("outputs/hello.wav"),
            language="ja",
            seed=42,
        )
    )
    print(result.sample_rate, result.duration_sec)
```

`with` を抜けるまでモデルは常駐する。複数件を投げるなら 1 つの `with` の中で回す。
プロセスの起動は最初の `synthesize()` まで遅延するので、`validate()` で弾かれる
リクエストではモデルをロードしない。

## テストと lint

```powershell
cd python
.\.venvs\common\Scripts\python.exe -m pytest tests\ -q
.\.venvs\common\Scripts\ruff.exe check .
.\.venvs\common\Scripts\ruff.exe format .
```

`tests/fake_runner.py` が本物のエンジンと同じ規約でふるまうダミーになっていて、
JSONL のやり取り、UTF-8、失敗時の復帰、未対応パラメータの拒否を
モデル無しで検証している。
