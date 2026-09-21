"""コマンドラインの入口。

    python -m ttstoolkit.cli synth   -e irodori -t "こんにちは。"
    python -m ttstoolkit.cli batch   -e qwen sample.ja.json
    python -m ttstoolkit.cli script  ep01.ja.txt -c cast.toml
    python -m ttstoolkit.cli engines
    python -m ttstoolkit.cli doctor

ここには「実行の土台」と「引数の形」だけを置く。各コマンドの中身は
`commands.py` にある。`core` は画面出力もプロセス終了もしないので、
ログの行き先と終了コードの決定はこのファイルが引き受ける。
GUI では代わりに `logger.py` が Handler を用意して同じことをする。
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import sys

from ttstoolkit.cli import commands
from ttstoolkit.core.paths import OUTPUT_DIR
from ttstoolkit.core.settings import (
    ROOT_LOGGER_NAME,
    SETUP_SCRIPT,
    TTSToolkitError,
)
from ttstoolkit.tool_config import engine_names

logger = logging.getLogger(ROOT_LOGGER_NAME)

# このプロジェクトが想定する Python のバージョン。変更するときは
# mise.toml と engine_env/*/pyproject.toml の requires-python、
# pyproject.toml の target-version も合わせること。
_REQUIRED_PYTHON = (3, 12)

# ログレベル -> 行頭に付けるラベル
_LEVEL_LABELS = {
    logging.DEBUG: "debug",
    logging.INFO: "info",
    logging.WARNING: "warn",
    logging.ERROR: "error",
    logging.CRITICAL: "error",
}


class _BracketFormatter(logging.Formatter):
    """`[info] メッセージ` の形に整える Formatter。"""

    def format(self, record: logging.LogRecord) -> str:
        """レベルのラベルを角括弧で前置した 1 行にする。"""
        label = _LEVEL_LABELS.get(record.levelno, record.levelname.lower())
        return f"[{label}] {record.getMessage()}"


# ---------------------------------------------------------------------
# 実行の土台
# ---------------------------------------------------------------------


def setup_logging(verbose: bool = False) -> None:
    """このツールのログを標準エラーへ出すよう設定する。

    ルートロガーには触らない (torch 自身のログまで拾わないため)。

    Args:
        verbose: DEBUG まで出すか。
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_BracketFormatter())
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False


def check_python_version() -> None:
    """想定したバージョンの Python で動いていなければ警告する。

    共通層の仮想環境を使い忘れてシステムの Python で実行している、と
    いった取り違えに気づくためのチェック。処理は止めない。
    """
    actual = sys.version_info[:2]
    if actual == _REQUIRED_PYTHON:
        return
    want = ".".join(str(part) for part in _REQUIRED_PYTHON)
    got = ".".join(str(part) for part in actual)
    logger.warning(
        "This project expects Python %s but Python %s is running. "
        "Use the interpreter in .venvs/common (see %s).",
        want,
        got,
        SETUP_SCRIPT,
    )


def enable_utf8_stdout() -> None:
    """標準出力/標準エラーを UTF-8 に切り替える。

    Windows の cp932 コンソールやリダイレクト先で日本語が化けないように
    する。切り替えられない環境ではそのまま続行する。
    """
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError, OSError):
            stream.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------
# 引数の定義
# ---------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """サブコマンドを並べたパーサを組み立てる。

    共通の引数は親パーサにまとめ、`parents=` で配る。

    Returns:
        argparse.ArgumentParser: 組み立てたパーサ。
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show the engine's own output as well",
    )

    output = argparse.ArgumentParser(add_help=False)
    output.add_argument(
        "-o", "--output-dir", default=OUTPUT_DIR, help="Output directory"
    )

    engine = argparse.ArgumentParser(add_help=False)
    engine.add_argument(
        "-e",
        "--engine",
        required=True,
        choices=engine_names(),
        help="Engine to use",
    )

    parser = argparse.ArgumentParser(
        prog="python -m ttstoolkit.cli",
        description="Drive local TTS models through one interface",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_synth(subparsers, common, output, engine)
    _add_batch(subparsers, common, output, engine)
    _add_script(subparsers, common, output)
    _add_engines(subparsers, common)
    _add_doctor(subparsers, common)
    return parser


def _add_synth(subparsers, common, output, engine) -> None:
    """synth サブコマンドを登録する。"""
    parser = subparsers.add_parser(
        "synth",
        parents=[engine, output, common],
        help="Synthesize one line of text",
        description="Synthesize one line of text",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-t", "--text", help="Text to speak")
    source.add_argument(
        "-f", "--text-file", help="Read the text from a UTF-8 file"
    )
    parser.add_argument(
        "-O",
        "--output",
        default=None,
        metavar="WAV",
        help="Output file. Derived from the text when omitted",
    )
    parser.add_argument(
        "-l",
        "--language",
        default=None,
        choices=["ja", "en"],
        help="Language code; left to the engine when omitted",
    )
    parser.add_argument(
        "-r",
        "--reference",
        default=None,
        metavar="WAV",
        help="Reference audio to clone the voice from. Relative paths are "
        "searched from the current directory, repository root, then "
        "input/voices",
    )
    parser.add_argument(
        "--reference-text",
        default=None,
        metavar="TEXT",
        help="Transcript of the reference audio (improves Qwen cloning)",
    )
    parser.add_argument(
        "--voice-design",
        default=None,
        metavar="TEXT",
        help="Describe the voice in words instead of cloning it",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Speaking rate (only on engines that support it)",
    )
    parser.set_defaults(func=commands.cmd_synth)


def _add_batch(subparsers, common, output, engine) -> None:
    """batch サブコマンドを登録する。"""
    parser = subparsers.add_parser(
        "batch",
        parents=[engine, output, common],
        help="Synthesize every line in a JSON file",
        description="Synthesize every line in a JSON file",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "input",
        help="Input JSON. Relative paths are searched from the current "
        "directory, repository root, then input/batch",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue with the remaining lines after a failure",
    )
    parser.set_defaults(func=commands.cmd_batch)


def _add_script(subparsers, common, output) -> None:
    """script サブコマンドを登録する。"""
    parser = subparsers.add_parser(
        "script",
        parents=[output, common],
        help="Synthesize a character script",
        description="Synthesize a character script",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "script",
        help="Script text. Relative paths are searched from the current "
        "directory, repository root, then input/script",
    )
    parser.add_argument(
        "-c",
        "--cast",
        default=None,
        metavar="TOML",
        help="Cast file. Defaults to cast.toml next to the script",
    )
    parser.add_argument(
        "--gap",
        type=float,
        default=0.3,
        help="Silence between lines used to compute start_sec (seconds)",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue with the remaining lines after a failure",
    )
    parser.set_defaults(func=commands.cmd_script)


def _add_engines(subparsers, common) -> None:
    """engines サブコマンドを登録する。"""
    parser = subparsers.add_parser(
        "engines",
        parents=[common],
        help="List the engines and what they support",
        description="List the engines and what they support",
    )
    parser.set_defaults(func=commands.cmd_engines)


def _add_doctor(subparsers, common) -> None:
    """doctor サブコマンドを登録する。"""
    parser = subparsers.add_parser(
        "doctor",
        parents=[common],
        help="Check that the environment is ready to synthesize",
        description="Check that the environment is ready to synthesize",
    )
    parser.set_defaults(func=commands.cmd_doctor)


# ---------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """引数を解析してサブコマンドを実行する。

    Args:
        argv: コマンドライン引数。None なら `sys.argv` を使う。

    Returns:
        int: プロセスの終了コード。失敗なら 1、中断なら 130。
    """
    enable_utf8_stdout()
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)
    check_python_version()
    try:
        return args.func(args)
    except TTSToolkitError as e:
        logger.error("%s", e)
        return 1
    except (FileNotFoundError, ValueError) as e:
        logger.error("%s", e)
        return 1
    except KeyboardInterrupt:
        logger.warning("Canceled")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
