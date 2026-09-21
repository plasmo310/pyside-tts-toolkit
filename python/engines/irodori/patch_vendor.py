"""vendor/Irodori-TTS の pyproject.toml に Windows + Python 3.12 用の調整を入れる。

上流リポジトリは .python-version が 3.10 で、sentencepiece を >=0.1.99,<0.2 に
ピンしている。0.1.99 には Python 3.12 用の Windows wheel が無く、ソースビルドには
Visual Studio が要る。Irodori 自身は sentencepiece を直接 import せず
transformers.AutoTokenizer(use_fast=True)（Rust 実装の tokenizers）しか使わないため、
wheel のある 0.2 系へ引き上げても動作に影響しない。

冪等。clone し直した直後に 1 回実行すればよい。
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "# --- python-tts-sample による追記 ---"
MISE_MARKER = "UV_PROJECT_ENVIRONMENT"

# clone の中に仮想環境を作らせないための設定。
# ルートの mise.toml が TTS_REPO_ROOT を定義している。
MISE_CONFIG = """# python-tts-sample が置いたファイル（上流リポジトリには無い）。
# 仮想環境をこの clone の中ではなく .venvs/engine-irodori に作らせる。
[env]
UV_PROJECT_ENVIRONMENT = "{{env.TTS_REPO_ROOT}}/.venvs/engine-irodori"
"""

BLOCK = f"""
{MARKER}
# sentencepiece 0.1.99 は cp312 の Windows wheel が無くビルドに VS が必要。
# Irodori は transformers の fast tokenizer しか使わないため 0.2 系で問題ない。
[tool.uv]
override-dependencies = ["sentencepiece>=0.2.0"]
"""


def read_keep_newlines(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return fh.read()


def write_keep_newlines(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def main() -> int:
    vendor = Path(__file__).resolve().parent / "vendor" / "Irodori-TTS"
    pyproject = vendor / "pyproject.toml"
    if not pyproject.is_file():
        print(f"vendor が見つかりません: {vendor}", file=sys.stderr)
        print("先に git clone してください（docs/setup/03_irodori-tts.md 参照）。", file=sys.stderr)
        return 1

    # newline="" で読み書きすることで、上流の改行コード（LF）を保つ。
    # 既定のままだと Windows で書き戻すときに CRLF へ変換され、全行が差分になる。
    # Path.read_text の newline 引数は 3.13 以降なので open() を使う。
    text = read_keep_newlines(pyproject)
    if MARKER in text:
        print("pyproject.toml は既にパッチ済みです。")
    else:
        # 上流は [tool.uv] を conflicts のために既に持っているので、そこへ足す。
        if "[tool.uv]\n" in text:
            text = text.replace(
                "[tool.uv]\n",
                "[tool.uv]\n"
                f"{MARKER}\n"
                "# sentencepiece 0.1.99 は cp312 の Windows wheel が無くビルドに VS が必要。\n"
                "# Irodori は transformers の fast tokenizer しか使わないため 0.2 系で問題ない。\n"
                'override-dependencies = ["sentencepiece>=0.2.0"]\n',
                1,
            )
        else:
            text = text.rstrip() + "\n" + BLOCK
        write_keep_newlines(pyproject, text)
        print("pyproject.toml に sentencepiece のオーバーライドを追記しました。")

    # .python-version を 3.12 に合わせる（プロジェクト全体で 3.12 に統一するため）。
    version_file = vendor / ".python-version"
    if read_keep_newlines(version_file).strip() != "3.12":
        version_file.write_text("3.12\n", encoding="utf-8")
        print(".python-version を 3.12 に変更しました。")

    # 仮想環境を clone の中ではなく .venvs/engine-irodori に作らせる。
    # 他の 3 プロジェクトは自前の mise.toml で同じことをしているが、
    # ここは上流の clone なのでこのスクリプトが置く。
    mise_file = vendor / "mise.toml"
    if not mise_file.is_file() or MISE_MARKER not in read_keep_newlines(mise_file):
        write_keep_newlines(mise_file, MISE_CONFIG)
        print("mise.toml を置きました（仮想環境は .venvs/engine-irodori に作られます）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
