# セットアップ手順

3 つの TTS モデルをローカルで動かし、共通インターフェースから使えるようにするための手順書。

| ファイル | 内容 |
|---|---|
| [00_common.md](00_common.md) | **最初に読む。** 全体構成、mise / uv / Python 3.12、一括セットアップ |
| [01_qwen3-tts.md](01_qwen3-tts.md) | Qwen3-TTS 1.7B（日英、クローン、Voice Design） |
| [02_chatterbox.md](02_chatterbox.md) | Chatterbox Multilingual V3（23 言語、最も軽い） |
| [03_irodori-tts.md](03_irodori-tts.md) | Irodori-TTS v4.1 Small（日本語専用、48kHz） |

導入が終わったら [../cli/](../cli/) と [../gui/usage.md](../gui/usage.md)、
作り込みは [../guide/](../guide/) を参照。

## なぜエンジンごとに環境を分けるのか

3 モデルは依存が互いに排他的で、1 つの仮想環境には同居できない。

| モデル | transformers | torch |
|---|---|---|
| Qwen3-TTS | `==4.57.3` | cu128 系 |
| Chatterbox | `==5.2.0` | `==2.6.0`（後述の理由で上書きする） |
| Irodori-TTS | `>=5.12.1,<6` | `>=2.10.0,<2.11.0` |

そのため共通層はモデルを直接 import せず、エンジンごとの仮想環境にある
runner をサブプロセスとして起動し、標準入出力の JSON でやり取りする。
共通層自体は torch に依存しないので、CLI からも GUI からも同じものを呼べる。

```
.venvs/common               CLI・GUI・共通層。torch なし
  ├─ .venvs/engine-qwen        transformers 4.57.3
  ├─ .venvs/engine-chatterbox  transformers 5.2.0
  └─ .venvs/engine-irodori     transformers 5.12.x
```

仮想環境を作るための定義は `engine_env/<name>/` にある。

## 機能対応表

|  | 日本語 | 英語 | 声クローン | Voice Design | 話速 | シード | レート |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---:|
| Qwen3-TTS | ○ | ○ | ○ | ○ | × | ○ | 24 kHz |
| Chatterbox | ○ | ○ | ○ | × | × | ○ | 24 kHz |
| Irodori-TTS | ○ | **×** | ○ | ○ | ○ | ○ | 48 kHz |

Voice Design は文章の指示から声そのものを設計する機能
（[../guide/original-voice.md](../guide/original-voice.md)）。

未対応のパラメータを渡すと、黙って無視されるのではなく明示的にエラーになる。
その判定は共通層で行うので、モデルをロードする前に即座に失敗する。

## ライセンス

いずれもローカル生成は無料・無制限で、商用利用も可能。

| モデル | コード | 重み |
|---|---|---|
| Qwen3-TTS | Apache-2.0 | Apache-2.0 |
| Chatterbox | MIT | MIT（生成音声に PerTh 電子透かしが入る） |
| Irodori-TTS | MIT | MIT |

ただし**参照音声（声素材）の権利は別**である。実在の人物の声をクローンする場合は、
本人の同意と利用範囲の確認が必要になる。
