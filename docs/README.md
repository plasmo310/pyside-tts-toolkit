# ドキュメント

| ディレクトリ | 内容 |
|---|---|
| [setup/](setup/) | 導入手順。**最初に読む** |
| [cli/](cli/) | コマンドラインの使い方 |
| [gui/](gui/) | GUI の使い方 |
| [guide/](guide/) | 作り込みの解説（台本・オリジナルボイス） |
| [development/](development/) | 全体構成と設計の根拠 |
| [instructions/](instructions/) | コードを書くときの決まりごと |
| [references/](references/) | TTS の調査結果 |
| [plan/](plan/) | 当初の要件 |

## setup — 導入

| ファイル | 内容 |
|---|---|
| [setup/README.md](setup/README.md) | なぜ環境を分けるのか、機能対応表、ライセンス |
| [setup/00_common.md](setup/00_common.md) | **最初に読む。** mise / uv / Python 3.12、一括セットアップ |
| [setup/01_qwen3-tts.md](setup/01_qwen3-tts.md) | Qwen3-TTS 1.7B（日英、クローン、Voice Design） |
| [setup/02_chatterbox.md](setup/02_chatterbox.md) | Chatterbox Multilingual V3（23 言語、最も軽い） |
| [setup/03_irodori-tts.md](setup/03_irodori-tts.md) | Irodori-TTS v4.1 Small（日本語専用、48kHz） |

## cli — コマンドライン

| ファイル | 内容 |
|---|---|
| [cli/common_options.md](cli/common_options.md) | 呼び方、共通の引数、パスの解決、終了コード |
| [cli/synth.md](cli/synth.md) | テキストを 1 件合成する |
| [cli/batch.md](cli/batch.md) | JSON をまとめて合成する |
| [cli/script.md](cli/script.md) | キャラクター台本からまとめて合成する |
| [cli/engines.md](cli/engines.md) | エンジン一覧と対応機能 |
| [cli/doctor.md](cli/doctor.md) | 環境の健全性チェック |

## gui / guide — 使い込む

| ファイル | 内容 |
|---|---|
| [gui/usage.md](gui/usage.md) | 画面の使い方 |
| [guide/script.md](guide/script.md) | キャラクター台本の書き方 |
| [guide/original-voice.md](guide/original-voice.md) | オリジナルの声を設計して固定する |

## development / instructions — 手を入れる

| ファイル | 内容 |
|---|---|
| [development/architecture.md](development/architecture.md) | なぜこの構成なのか。制約・設計判断・プロトコル |
| [development/build.md](development/build.md) | PyInstaller で GUI を exe にする |
| [instructions/code_guide.md](instructions/code_guide.md) | 書き方の決まりと、よくある変更の手順 |
