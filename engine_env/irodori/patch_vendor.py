"""clone した Irodori-TTS に Windows + Python 3.12 用の調整を入れる。

上流リポジトリは .python-version が 3.10 で、sentencepiece を
>=0.1.99,<0.2 にピンしている。0.1.99 には Python 3.12 用の Windows
wheel が無く、ソースビルドには Visual Studio が要る。Irodori 自身は
sentencepiece を直接 import せず transformers.AutoTokenizer
(use_fast=True) の Rust 実装しか使わないため、wheel のある 0.2 系へ
引き上げても動作に影響しない。

あわせて、仮想環境が clone の中に作られないよう mise.toml を置く。

冪等。clone し直した直後に 1 回実行すればよい。

    .venvs\\common\\Scripts\\python.exe engine_env\\irodori\\patch_vendor.py
"""

from __future__ import annotations

import os
import sys

# 追記済みかどうかの目印。オーバーライドそのものを探すので、目印の
# 文言を変えても二重に追記されない。
_MARKER = "# --- added by TTS Toolkit ---"
_OVERRIDE_MARKER = "sentencepiece>=0.2.0"
_MISE_MARKER = "UV_PROJECT_ENVIRONMENT"

# clone の中に仮想環境を作らせないための設定。
# ルートの mise.toml が TTS_REPO_ROOT を定義している。
_MISE_CONFIG = """# TTS Toolkit が置いたファイル（上流リポジトリには無い）。
# 仮想環境をこの clone の中ではなく .venvs/engine-irodori に作らせる。
[env]
UV_PROJECT_ENVIRONMENT = "{{env.TTS_REPO_ROOT}}/.venvs/engine-irodori"
"""

# pyproject.toml の [tool.uv] に足す内容
_OVERRIDE_LINES = (
    f"{_MARKER}\n"
    "# sentencepiece 0.1.99 は cp312 の Windows wheel が無く、"
    "ビルドに VS が要る。\n"
    "# Irodori は transformers の fast tokenizer しか使わないため "
    "0.2 系で問題ない。\n"
    'override-dependencies = ["sentencepiece>=0.2.0"]\n'
)


def read_keep_newlines(path: str) -> str:
    """改行コードを変換せずにファイルを読む。

    Args:
        path: 読むファイルのパス。

    Returns:
        str: ファイルの中身。
    """
    with open(path, encoding="utf-8", newline="") as file:
        return file.read()


def write_keep_newlines(path: str, text: str) -> None:
    """改行コードを変換せずにファイルへ書く。

    既定のままだと Windows で書き戻すときに LF が CRLF へ変換され、
    上流との差分が全行に出てしまう。

    Args:
        path: 書くファイルのパス。
        text: 書く内容。
    """
    with open(path, "w", encoding="utf-8", newline="") as file:
        file.write(text)


def patch_pyproject(vendor_dir: str) -> None:
    """sentencepiece のオーバーライドを pyproject.toml に足す。

    Args:
        vendor_dir: clone したリポジトリのパス。
    """
    path = os.path.join(vendor_dir, "pyproject.toml")
    text = read_keep_newlines(path)
    if _OVERRIDE_MARKER in text:
        print("pyproject.toml is already patched")
        return

    # 上流は conflicts のために [tool.uv] を既に持っているので、そこへ足す
    if "[tool.uv]\n" in text:
        text = text.replace("[tool.uv]\n", "[tool.uv]\n" + _OVERRIDE_LINES, 1)
    else:
        text = text.rstrip() + "\n\n[tool.uv]\n" + _OVERRIDE_LINES
    write_keep_newlines(path, text)
    print("patched pyproject.toml (sentencepiece override)")


def patch_python_version(vendor_dir: str) -> None:
    """.python-version をプロジェクト全体と同じ 3.12 に揃える。

    Args:
        vendor_dir: clone したリポジトリのパス。
    """
    path = os.path.join(vendor_dir, ".python-version")
    if read_keep_newlines(path).strip() == "3.12":
        return
    write_keep_newlines(path, "3.12\n")
    print("patched .python-version (3.12)")


def put_mise_config(vendor_dir: str) -> None:
    """仮想環境の置き場を指定する mise.toml を置く。

    他の 3 つは自前の mise.toml で同じことをしているが、ここは上流の
    clone なのでこのスクリプトが置く。

    Args:
        vendor_dir: clone したリポジトリのパス。
    """
    path = os.path.join(vendor_dir, "mise.toml")
    if os.path.isfile(path) and _MISE_MARKER in read_keep_newlines(path):
        return
    write_keep_newlines(path, _MISE_CONFIG)
    print("put mise.toml (venv goes to .venvs/engine-irodori)")


def main() -> int:
    """clone に調整を入れる。

    Returns:
        int: 正常終了なら 0、clone が無ければ 1。
    """
    vendor_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "vendor", "Irodori-TTS"
    )
    if not os.path.isfile(os.path.join(vendor_dir, "pyproject.toml")):
        print(f"Clone not found: {vendor_dir}", file=sys.stderr)
        print(
            "Run scripts\\win\\SetupEngines.ps1 first "
            "(see docs/setup/03_irodori-tts.md).",
            file=sys.stderr,
        )
        return 1

    patch_pyproject(vendor_dir)
    patch_python_version(vendor_dir)
    put_mise_config(vendor_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
