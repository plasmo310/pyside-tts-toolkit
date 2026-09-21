"""入出力フォルダとエンジン環境の場所を解決するモジュール。

音声合成とは無関係な「このリポジトリのフォルダ構成」だけを扱う。

呼ばれる先: cli/, gui/, core の全部
呼ぶ先: core.settings

    <ルート>/python/ttstoolkit/core/  ... このファイルの置き場所
    <ルート>/input/voices/   ... 参照音声 (オリジナルボイスの素材)
    <ルート>/input/script/   ... キャスト定義と台本
    <ルート>/input/batch/    ... バッチ入力 JSON
    <ルート>/output/         ... 書き出し結果
    <ルート>/.venvs/         ... 共通層と各エンジンの仮想環境

既定のパスは「実行時のカレントディレクトリ」ではなく
「このファイルの位置から辿ったリポジトリルート」を基準にする。
そうしないと実行時のカレントディレクトリに `output/` が作られてしまう。

Attributes:
    CORE_DIR (str): core パッケージ (`python/ttstoolkit/core/`)。
    PACKAGE_DIR (str): パッケージ (`python/ttstoolkit/`) の絶対パス。
    PYTHON_DIR (str): 検索パスに入れる `python/` の絶対パス。
    ROOT_DIR (str): リポジトリルートの絶対パス。
    INPUT_DIR (str): 入力ルート (`input/`) の絶対パス。
    VOICES_DIR (str): 参照音声の既定の置き場 (`input/voices/`)。
    SCRIPT_DIR (str): 台本の既定の置き場 (`input/script/`)。
    BATCH_DIR (str): バッチ入力の既定の置き場 (`input/batch/`)。
    OUTPUT_DIR (str): 書き出し先 (`output/`)。
    VENVS_DIR (str): 仮想環境をまとめた場所 (`.venvs/`)。
"""

from __future__ import annotations

import hashlib
import os

from ttstoolkit.core.settings import IS_WINDOWS, TTSToolkitError

CORE_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_DIR = os.path.dirname(CORE_DIR)
PYTHON_DIR = os.path.dirname(PACKAGE_DIR)
ROOT_DIR = os.path.dirname(PYTHON_DIR)

INPUT_DIR = os.path.join(ROOT_DIR, "input")
VOICES_DIR = os.path.join(INPUT_DIR, "voices")
SCRIPT_DIR = os.path.join(INPUT_DIR, "script")
BATCH_DIR = os.path.join(INPUT_DIR, "batch")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")

VENVS_DIR = os.path.join(ROOT_DIR, ".venvs")


def resolve_input(path: str, default_dir: str | None = None) -> str:
    """入力ファイルのパスを解決する。

    1. 指定されたパスをそのまま（＝カレントディレクトリ基準）
    2. リポジトリルート基準
    3. 既定の置き場 (input/voices, input/script) 基準

    の順に探し、最初に見つかったものを返す。

    これにより、リポジトリのどこから実行しても `input/voices/a.wav` と
    書けるうえ、ファイル名だけ (`a.wav`) を渡しても既定の置き場から拾える。

    Args:
        path: 利用者が指定したパス。絶対パスならそのまま扱う。
        default_dir: 3 番目に探す既定の置き場。None なら探さない。

    Returns:
        str: 実在が確認できた最初のパス。どれも見つからなければ `path`
            をそのまま返す（存在チェックと "見つかりません" の表示は
            呼び出し側の役目）。
    """
    candidates = [path]
    if not os.path.isabs(path):
        candidates.append(os.path.join(ROOT_DIR, path))
        if default_dir is not None:
            candidates.append(os.path.join(default_dir, path))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return path


def resolve_existing(path: str, default_dir: str, missing_message: str) -> str:
    """入力パスを解決し、実在することを確かめる。

    `resolve_input()` との違いは、見つからなければ例外にすること。
    CLI も GUI も「解決して、無ければエラー」を同じ形で使うので
    ここに 1 つだけ置く。

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


def resolve_output(output_dir: str, output_name: str | None) -> str | None:
    """書き出し先のパスを決める。

    ファイル名が絶対パスならそのまま、相対パスなら `output_dir` から
    たどる。ファイル名が未指定なら None を返すので、呼び出し側が
    `default_output_path()` などの既定値を当てる。

    Args:
        output_dir: 書き出し先ディレクトリ。
        output_name: 書き出すファイル名。空や None なら None を返す。

    Returns:
        str | None: 書き出す wav のパス。ファイル名が無ければ None。

    Raises:
        TTSToolkitError: 書き出し先ディレクトリが未指定のとき。
    """
    if not output_dir:
        raise TTSToolkitError("Select an output directory")
    if not output_name:
        return None
    if os.path.isabs(output_name):
        return output_name
    return os.path.join(output_dir, output_name)


def default_output_path(engine: str, text: str, output_dir: str) -> str:
    """テキストから決まるファイル名を作る (再生成時の取り違え防止)。

    Args:
        engine: エンジン名。
        text: 読み上げるテキスト。
        output_dir: 書き出し先ディレクトリ。

    Returns:
        str: 書き出す wav のパス。
    """
    digest = hashlib.sha256(f"{engine}\n{text}".encode()).hexdigest()[:12]
    return os.path.join(output_dir, f"{engine}-{digest}.wav")


def venv_python(venv_name: str) -> str:
    """`.venvs/<name>` の python 実行ファイルのパスを返す。

    Args:
        venv_name: 仮想環境のフォルダ名 (`common`, `engine-qwen` など)。

    Returns:
        str: python 実行ファイルの絶対パス。実在は確認しない。
    """
    venv_dir = os.path.join(VENVS_DIR, venv_name)
    if IS_WINDOWS:
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")
