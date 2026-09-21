"""入出力フォルダとエンジン環境の場所を解決するモジュール。

音声合成とは無関係な「このリポジトリのフォルダ構成」だけを扱う。

    <ルート>/python/ttstoolkit/engine/  ... このファイルの置き場所
    <ルート>/input/voices/   ... 参照音声 (オリジナルボイスの素材)
    <ルート>/input/script/   ... キャスト定義と台本
    <ルート>/input/batch/    ... バッチ入力 JSON
    <ルート>/output/         ... 書き出し結果
    <ルート>/.venvs/         ... 共通層と各エンジンの仮想環境
    <ルート>/engine_env/     ... 各エンジンの仮想環境を作るための定義

既定のパスは「実行時のカレントディレクトリ」ではなく
「このファイルの位置から辿ったリポジトリルート」を基準にする。
そうしないと実行時のカレントディレクトリに `output/` が作られてしまう。

Attributes:
    ENGINE_DIR (str): engine パッケージ (`python/ttstoolkit/engine/`)。
    PACKAGE_DIR (str): パッケージ (`python/ttstoolkit/`) の絶対パス。
    PYTHON_DIR (str): 検索パスに入れる `python/` の絶対パス。
    ROOT_DIR (str): リポジトリルートの絶対パス。
    INPUT_DIR (str): 入力ルート (`input/`) の絶対パス。
    VOICES_DIR (str): 参照音声の既定の置き場 (`input/voices/`)。
    SCRIPT_DIR (str): 台本の既定の置き場 (`input/script/`)。
    BATCH_DIR (str): バッチ入力の既定の置き場 (`input/batch/`)。
    OUTPUT_DIR (str): 書き出し先 (`output/`)。
    VENVS_DIR (str): 仮想環境をまとめた場所 (`.venvs/`)。
    ENGINE_ENV_DIR (str): エンジン環境の定義 (`engine_env/`)。
"""

from __future__ import annotations

import os

from ttstoolkit.engine.settings import IS_WINDOWS

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_DIR = os.path.dirname(ENGINE_DIR)
PYTHON_DIR = os.path.dirname(PACKAGE_DIR)
ROOT_DIR = os.path.dirname(PYTHON_DIR)

INPUT_DIR = os.path.join(ROOT_DIR, "input")
VOICES_DIR = os.path.join(INPUT_DIR, "voices")
SCRIPT_DIR = os.path.join(INPUT_DIR, "script")
BATCH_DIR = os.path.join(INPUT_DIR, "batch")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")

VENVS_DIR = os.path.join(ROOT_DIR, ".venvs")
ENGINE_ENV_DIR = os.path.join(ROOT_DIR, "engine_env")


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
