# doctor — 環境の健全性チェック

```powershell
tts doctor
```

合成がうまくいかないときに最初に叩くコマンドです。引数はありません。

```
== Toolkit ==
python  3.12.14
        D:\...\.venvs\common\Scripts\python.exe
root    D:\workspace\GitProjects\python-tts-sample

== GPU ==
NVIDIA GeForce RTX 5070, 12227 MiB, 2529 MiB, 595.79

== Engines ==

[qwen] Qwen/Qwen3-TTS-12Hz-1.7B-Base
  torch 2.11.0+cu128 / CUDA ok / NVIDIA GeForce RTX 5070

[chatterbox] ResembleAI/chatterbox (multilingual v3)
  torch 2.7.1+cu128 / CUDA ok / NVIDIA GeForce RTX 5070

[irodori] Aratako/Irodori-TTS-v4.1-Small
  torch 2.10.0+cu128 / CUDA ok / NVIDIA GeForce RTX 5070
```

## 何を見ているか

| 節 | 内容 |
|---|---|
| Toolkit | 共通層の Python のバージョンと場所、リポジトリのルート |
| GPU | `nvidia-smi` の出力（名前 / VRAM / 使用量 / ドライバ） |
| Engines | **各エンジンの仮想環境の中で** torch を読み込んだ結果 |

エンジンの仮想環境は互いに独立しているので、それぞれの python を
子プロセスとして起動して調べています。torch のバージョンがエンジンごとに
違うのは正常です。

## 出る可能性のあるメッセージ

### `not set up; see docs/setup/...`

その仮想環境がまだ作られていません。案内された手順を実行します。
1 つでも未構築だと終了コードは 1 になります。

### `CUDA unavailable (CPU only)`

CPU で動きます。合成はできますが、日本語の量産に使える速度ではありません。
ドライバと、その仮想環境の torch が CUDA ビルドかを確認します。

### `! sm_120 is missing from arch_list: ...`

Blackwell 世代（RTX 50 系）で、その torch が対応アーキに `sm_120` を
含んでいません。実行時に
`no kernel image is available for execution on the device` になります。
`engine_env/<name>/pyproject.toml` で cu128 ビルドを指定し直してから
仮想環境を作り直してください（[../setup/02_chatterbox.md](../setup/02_chatterbox.md)
に経緯があります）。

### `could not import torch: ...`

仮想環境は在るが壊れています。作り直すのが早いです。

```powershell
Remove-Item -Recurse -Force .venvs\engine-qwen
pwsh scripts\win\SetupEngines.ps1 -Targets qwen
```

### `nvidia-smi not found`

GPU が無いか、ドライバが入っていません。CPU で動きます。
