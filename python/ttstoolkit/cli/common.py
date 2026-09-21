"""5 本の CLI で共通の、引数定義とログの設定。

`engine` パッケージは画面出力もプロセス終了もしないので、その面倒を
ここで引き受ける。GUI 側は代わりに `logger.py` が Handler を用意して
同じことをする。
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import sys
from collections.abc import Callable

from ttstoolkit.engine.paths import OUTPUT_DIR, resolve_input
from ttstoolkit.engine.registry import engine_names
from ttstoolkit.engine.settings import (
    ROOT_LOGGER_NAME,
    SETUP_SCRIPT,
    TTSToolkitError,
)

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
    する。切り替えに失敗する環境では何もせずに続行する。
    """
    for stream in (sys.stdout, sys.stderr):
        # 切り替えられない環境（差し替え済みのストリームなど）は諦める
        with contextlib.suppress(AttributeError, ValueError, OSError):
            stream.reconfigure(encoding="utf-8", errors="replace")


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """どの CLI にもある引数を登録する。

    Args:
        parser: 登録先のパーサ。
    """
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show the engine's own output as well",
    )


def add_engine_arg(parser: argparse.ArgumentParser) -> None:
    """エンジンを選ぶ引数を登録する。

    Args:
        parser: 登録先のパーサ。
    """
    parser.add_argument(
        "-e",
        "--engine",
        required=True,
        choices=engine_names(),
        help="Engine to use",
    )


def add_voice_args(parser: argparse.ArgumentParser) -> None:
    """声の指定に関わる引数を登録する。

    Args:
        parser: 登録先のパーサ。
    """
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


def add_output_dir_arg(parser: argparse.ArgumentParser) -> None:
    """書き出し先ディレクトリの引数を登録する。

    Args:
        parser: 登録先のパーサ。
    """
    parser.add_argument(
        "-o", "--output-dir", default=OUTPUT_DIR, help="Output directory"
    )


def resolve_existing(path: str, default_dir: str, missing_message: str) -> str:
    """入力パスを解決し、実在することを確かめる。

    Args:
        path: 利用者が指定したパス。
        default_dir: 見つからないときに最後に探す既定の置き場。
        missing_message: 見つからないときの文言。末尾にパスが付く。

    Returns:
        str: 実在が確認できたパス。

    Raises:
        TTSToolkitError: どこにも見つからないとき。
    """
    resolved = resolve_input(path, default_dir)
    if not os.path.isfile(resolved):
        raise TTSToolkitError(f"{missing_message}: {resolved}")
    return resolved


def report_result(result: object) -> None:
    """1 件の合成結果を標準出力へ出す。

    Args:
        result: `SynthesisResult`。
    """
    print(f"wrote {result.output_path}")
    print(f"  model    {result.model_id}")
    print(f"  audio    {result.sample_rate} Hz / {result.duration_sec:.2f}s")
    print(f"  took     {result.elapsed_sec:.2f}s")


def run(main_func: Callable[[], int]) -> int:
    """CLI の共通の前処理と、エラーの受け止めをまとめる。

    Args:
        main_func: 実際の処理。終了コードを返す。

    Returns:
        int: プロセスの終了コード。失敗なら 1、中断なら 130。
    """
    enable_utf8_stdout()
    setup_logging("-v" in sys.argv or "--verbose" in sys.argv)
    check_python_version()
    try:
        return main_func()
    except TTSToolkitError as e:
        logger.error("%s", e)
        return 1
    except (FileNotFoundError, ValueError) as e:
        logger.error("%s", e)
        return 1
    except KeyboardInterrupt:
        logger.warning("Canceled")
        return 130
