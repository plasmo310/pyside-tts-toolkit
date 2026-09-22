"""台本の再生用 HTML 生成を検証する。モデルは使わない。"""

from __future__ import annotations

import json
import os
import re

from ttstoolkit.core._internal.script_player import (
    PLAYER_NAME,
    build_player_html,
    write_script_player,
)


def make_manifest(tmp_path) -> dict:
    """テスト用の manifest 辞書を作る。

    Args:
        tmp_path: pytest の一時ディレクトリ。

    Returns:
        dict: `_build_script_manifest()` と同じ形の辞書。
    """
    return {
        "total_duration_sec": 4.5,
        "items": [
            {
                "voice": "霊夢",
                "text": "今日はいい天気ね。",
                "duration_sec": 2.5,
                "output_path": str(tmp_path / "001-霊夢.wav"),
            },
            {
                "voice": "魔理沙",
                "text": "そうだな！",
                "duration_sec": 2.0,
                "output_path": str(tmp_path / "002-魔理沙.wav"),
            },
        ],
    }


def test_player_embeds_items_as_json(tmp_path) -> None:
    """台詞が voice / text / duration / file の形で埋め込まれること。"""
    html = build_player_html(
        "ep01",
        "2 lines",
        [
            {
                "voice": "霊夢",
                "text": "今日はいい天気ね。",
                "duration": 2.5,
                "file": "001-霊夢.wav",
            }
        ],
    )
    match = re.search(r"const items = (\[.*?\]);", html)
    assert match is not None
    items = json.loads(match.group(1))
    assert items == [
        {
            "voice": "霊夢",
            "text": "今日はいい天気ね。",
            "duration": 2.5,
            "file": "001-霊夢.wav",
        }
    ]


def test_player_buttons_are_not_garbled() -> None:
    """一括再生・個別再生・停止のラベルが文字化けしていないこと。"""
    html = build_player_html("ep01", "0 lines", [])
    assert "一括再生" in html
    assert "▶ 再生" in html
    assert "停止" in html


def test_write_script_player_uses_wav_basename(tmp_path) -> None:
    """output_path からファイル名だけを取り出して埋め込むこと。

    HTML は wav と同じディレクトリに書き出す前提なので、相対参照で
    足りる (絶対パスのままだと別マシンへ持ち出したときに壊れる)。
    """
    manifest = make_manifest(tmp_path)
    path = write_script_player(str(tmp_path), "ep01", manifest)
    assert path == os.path.join(str(tmp_path), PLAYER_NAME)
    with open(path, encoding="utf-8") as file:
        html = file.read()
    assert "001-霊夢.wav" in html
    assert str(tmp_path) not in html
    assert "2 lines" in html
    assert "total 4.5s" in html
