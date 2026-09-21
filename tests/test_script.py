"""台本とキャスト定義の読み込みを検証する。モデルは使わない。"""

from __future__ import annotations

import os

import pytest

from ttstoolkit.engine.script import (
    ScriptError,
    load_script,
    parse_cast,
    parse_script,
)

CAST = """
[voices."霊夢"]
engine = "irodori"
voice_design = "落ち着いた少女の声。"
language = "ja"
seed = 42

[voices."魔理沙"]
engine = "irodori"
speed = 1.1

[voices."ナレーター"]
engine = "qwen"
"""


def write(tmp_path, name: str, body: str) -> str:
    """一時ディレクトリにファイルを書いてパスを返す。

    Args:
        tmp_path: pytest の一時ディレクトリ。
        name: ファイル名。
        body: 書く内容。

    Returns:
        str: 書いたファイルのパス。
    """
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return str(path)


def cast_file(tmp_path) -> str:
    """共通のキャスト定義を書いてパスを返す。

    Args:
        tmp_path: pytest の一時ディレクトリ。

    Returns:
        str: cast.toml のパス。
    """
    return write(tmp_path, "cast.toml", CAST)


# ---------------------------------------------------------------------
# cast.toml
# ---------------------------------------------------------------------


def test_cast_reads_japanese_names(tmp_path) -> None:
    """日本語のキャラクター名をそのまま読めること。"""
    cast = parse_cast(cast_file(tmp_path))
    assert set(cast) == {"霊夢", "魔理沙", "ナレーター"}
    assert cast["霊夢"].engine == "irodori"
    assert cast["霊夢"].seed == 42
    assert cast["魔理沙"].speed == 1.1


def test_cast_resolves_reference_audio_relative_to_itself(tmp_path) -> None:
    """参照音声は cast.toml からの相対で解決されること。"""
    (tmp_path / "voices").mkdir()
    path = write(
        tmp_path,
        "cast.toml",
        '[voices."A"]\nengine = "qwen"\nreference_audio = "voices/a.wav"\n',
    )
    cast = parse_cast(path)
    assert cast["A"].reference_audio == str(tmp_path / "voices" / "a.wav")


def test_cast_rejects_unknown_key(tmp_path) -> None:
    """知らないキーは黙って無視せずエラーにすること。"""
    path = write(
        tmp_path,
        "cast.toml",
        '[voices."A"]\nengine = "qwen"\ncolour = "red"\n',
    )
    with pytest.raises(ScriptError) as error:
        parse_cast(path)
    assert "colour" in str(error.value)


def test_cast_requires_engine(tmp_path) -> None:
    """engine が無いキャラクターはエラーになること。"""
    path = write(tmp_path, "cast.toml", '[voices."A"]\nseed = 1\n')
    with pytest.raises(ScriptError) as error:
        parse_cast(path)
    assert "engine" in str(error.value)


def test_cast_without_voices_table_explains_format(tmp_path) -> None:
    """[voices."名前"] が無いときは書き方を案内すること。"""
    path = write(tmp_path, "cast.toml", 'engine = "qwen"\n')
    with pytest.raises(ScriptError) as error:
        parse_cast(path)
    assert "[voices." in str(error.value)


# ---------------------------------------------------------------------
# script.txt
# ---------------------------------------------------------------------


def test_parses_speakers_and_order(tmp_path) -> None:
    """話者と並び順をそのまま読めること。"""
    cast = parse_cast(cast_file(tmp_path))
    path = write(
        tmp_path,
        "ep.txt",
        "# コメント\n\n霊夢: 一言目。\n魔理沙: 二言目。\n霊夢: 三言目。\n",
    )
    script = parse_script(path, cast)
    assert [line.index for line in script.lines] == [1, 2, 3]
    assert [line.voice for line in script.lines] == [
        "霊夢",
        "魔理沙",
        "霊夢",
    ]
    assert script.lines[0].text == "一言目。"


def test_continuation_lines_join_without_separator(tmp_path) -> None:
    """インデント継続は区切り文字なしで連結されること。

    日本語の台詞に余計な空白が入らないようにしている。
    """
    cast = parse_cast(cast_file(tmp_path))
    path = write(
        tmp_path, "ep.txt", "霊夢: まあいいわ。\n  お茶でも淹れてくる。\n"
    )
    script = parse_script(path, cast)
    assert script.lines[0].text == "まあいいわ。お茶でも淹れてくる。"


def test_line_options_override_cast(tmp_path) -> None:
    """行の角括弧の指定がキャストの既定より優先されること。"""
    cast = parse_cast(cast_file(tmp_path))
    path = write(
        tmp_path, "ep.txt", "霊夢[speed=0.9, seed=7, id=key]: 台詞。\n"
    )
    script = parse_script(path, cast)
    line = script.lines[0]
    assert line.speed == 0.9
    assert line.seed == 7
    assert line.id == "key"

    request = script.to_request(line, str(tmp_path / "out.wav"))
    assert request.speed == 0.9
    # 行の指定がキャストの 42 に勝つ
    assert request.seed == 7
    # 行で指定していないものはキャストから引き継ぐ
    assert request.voice_design == "落ち着いた少女の声。"
    assert request.language == "ja"


def test_cast_defaults_apply_when_line_has_no_options(tmp_path) -> None:
    """行に指定が無ければキャストの既定が使われること。"""
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "霊夢: 台詞。\n魔理沙: 台詞。\n")
    script = parse_script(path, cast)
    first = script.to_request(script.lines[0], str(tmp_path / "a.wav"))
    second = script.to_request(script.lines[1], str(tmp_path / "b.wav"))
    assert first.seed == 42
    assert second.speed == 1.1


def test_output_name_uses_index_and_id(tmp_path) -> None:
    """出力ファイル名が連番と id から決まること。"""
    cast = parse_cast(cast_file(tmp_path))
    path = write(
        tmp_path, "ep.txt", "霊夢: 一。\n魔理沙[id=punchline]: 二。\n"
    )
    script = parse_script(path, cast)
    assert script.lines[0].output_name() == "001-霊夢.wav"
    assert script.lines[1].output_name() == "002-punchline.wav"


def test_engines_used_keeps_first_appearance_order(tmp_path) -> None:
    """エンジン単位でまとめて処理するので、登場順が保たれること。"""
    cast = parse_cast(cast_file(tmp_path))
    path = write(
        tmp_path, "ep.txt", "ナレーター: 一。\n霊夢: 二。\n魔理沙: 三。\n"
    )
    script = parse_script(path, cast)
    assert script.engines_used() == ["qwen", "irodori"]
    assert script.voices_used() == ["ナレーター", "霊夢", "魔理沙"]


def test_fullwidth_colon_is_accepted(tmp_path) -> None:
    """全角コロンでも台詞として読めること。"""
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "霊夢：全角コロンでも通る。\n")
    script = parse_script(path, cast)
    assert script.lines[0].text == "全角コロンでも通る。"


def test_unknown_speaker_names_the_line(tmp_path) -> None:
    """キャストに無い話者は行番号つきで知らせること。"""
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "霊夢: 一。\nこいし: 二。\n")
    with pytest.raises(ScriptError) as error:
        parse_script(path, cast)
    assert "Line 2" in str(error.value)
    assert "こいし" in str(error.value)


def test_unknown_line_option_is_rejected(tmp_path) -> None:
    """知らない行オプションはエラーになること。"""
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "霊夢[pitch=2]: 台詞。\n")
    with pytest.raises(ScriptError) as error:
        parse_script(path, cast)
    assert "pitch" in str(error.value)


def test_duplicate_ids_are_rejected(tmp_path) -> None:
    """id が重複すると出力が上書きされるのでエラーにすること。"""
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "霊夢[id=a]: 一。\n魔理沙[id=a]: 二。\n")
    with pytest.raises(ScriptError) as error:
        parse_script(path, cast)
    assert "Duplicated ids" in str(error.value)


def test_unparsable_line_is_reported_with_line_number(tmp_path) -> None:
    """解釈できない行は行番号つきで知らせること。"""
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "霊夢: 一。\nコロンのない行\n")
    with pytest.raises(ScriptError) as error:
        parse_script(path, cast)
    assert "Line 2" in str(error.value)


def test_empty_script_is_rejected(tmp_path) -> None:
    """台詞が 1 つも無い台本はエラーになること。"""
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "# コメントだけ\n\n")
    with pytest.raises(ScriptError):
        parse_script(path, cast)


def test_load_script_reads_both_files(tmp_path) -> None:
    """キャストと台本をまとめて読めること。"""
    script = load_script(
        cast_file(tmp_path), write(tmp_path, "ep.txt", "霊夢: 台詞。\n")
    )
    assert script.source == os.path.join(str(tmp_path), "ep.txt")
    assert len(script.lines) == 1
