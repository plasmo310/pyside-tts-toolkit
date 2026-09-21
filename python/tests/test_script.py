"""台本とキャスト定義の読み込みを検証する。モデルは使わない。"""

from __future__ import annotations

from pathlib import Path

import pytest

from tts_sample.script import ScriptError, load_script, parse_cast, parse_script

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


def write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def cast_file(tmp_path: Path) -> Path:
    return write(tmp_path, "cast.toml", CAST)


# ----------------------------------------------------------------- cast


def test_cast_reads_japanese_names(tmp_path: Path) -> None:
    cast = parse_cast(cast_file(tmp_path))
    assert set(cast) == {"霊夢", "魔理沙", "ナレーター"}
    assert cast["霊夢"].engine == "irodori"
    assert cast["霊夢"].seed == 42
    assert cast["魔理沙"].speed == 1.1


def test_cast_resolves_reference_audio_relative_to_itself(tmp_path: Path) -> None:
    """参照音声は cast.toml からの相対で解決されること。"""
    (tmp_path / "voices").mkdir()
    path = write(
        tmp_path,
        "cast.toml",
        '[voices."A"]\nengine = "qwen"\nreference_audio = "voices/a.wav"\n',
    )
    cast = parse_cast(path)
    assert cast["A"].reference_audio == (tmp_path / "voices" / "a.wav").resolve()


def test_cast_rejects_unknown_key(tmp_path: Path) -> None:
    path = write(tmp_path, "cast.toml", '[voices."A"]\nengine = "qwen"\ncolour = "red"\n')
    with pytest.raises(ScriptError) as excinfo:
        parse_cast(path)
    assert "colour" in str(excinfo.value)


def test_cast_requires_engine(tmp_path: Path) -> None:
    path = write(tmp_path, "cast.toml", '[voices."A"]\nseed = 1\n')
    with pytest.raises(ScriptError) as excinfo:
        parse_cast(path)
    assert "engine" in str(excinfo.value)


def test_cast_without_voices_table_explains_format(tmp_path: Path) -> None:
    path = write(tmp_path, "cast.toml", 'engine = "qwen"\n')
    with pytest.raises(ScriptError) as excinfo:
        parse_cast(path)
    assert "[voices." in str(excinfo.value)


# --------------------------------------------------------------- script


def test_parses_speakers_and_order(tmp_path: Path) -> None:
    cast = parse_cast(cast_file(tmp_path))
    path = write(
        tmp_path,
        "ep.txt",
        "# コメント\n\n霊夢: 一言目。\n魔理沙: 二言目。\n霊夢: 三言目。\n",
    )
    script = parse_script(path, cast)
    assert [ln.index for ln in script.lines] == [1, 2, 3]
    assert [ln.voice for ln in script.lines] == ["霊夢", "魔理沙", "霊夢"]
    assert script.lines[0].text == "一言目。"


def test_continuation_lines_join_without_separator(tmp_path: Path) -> None:
    """インデント継続は区切り文字なしで連結されること（日本語に空白を入れない）。"""
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "霊夢: まあいいわ。\n  お茶でも淹れてくる。\n")
    script = parse_script(path, cast)
    assert script.lines[0].text == "まあいいわ。お茶でも淹れてくる。"


def test_line_options_override_cast(tmp_path: Path) -> None:
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "霊夢[speed=0.9, seed=7, id=key]: 台詞。\n")
    script = parse_script(path, cast)
    line = script.lines[0]
    assert line.speed == 0.9
    assert line.seed == 7
    assert line.id == "key"

    request = script.to_request(line, tmp_path / "out.wav")
    assert request.speed == 0.9
    assert request.seed == 7  # 行の指定がキャストの 42 に勝つ
    assert request.voice_design == "落ち着いた少女の声。"  # キャストから引き継ぐ
    assert request.language == "ja"


def test_cast_defaults_apply_when_line_has_no_options(tmp_path: Path) -> None:
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "霊夢: 台詞。\n魔理沙: 台詞。\n")
    script = parse_script(path, cast)
    assert script.to_request(script.lines[0], tmp_path / "a.wav").seed == 42
    assert script.to_request(script.lines[1], tmp_path / "b.wav").speed == 1.1


def test_output_name_uses_index_and_id(tmp_path: Path) -> None:
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "霊夢: 一。\n魔理沙[id=punchline]: 二。\n")
    script = parse_script(path, cast)
    assert script.lines[0].output_name() == "001-霊夢.wav"
    assert script.lines[1].output_name() == "002-punchline.wav"


def test_engines_used_keeps_first_appearance_order(tmp_path: Path) -> None:
    """エンジン単位でまとめて処理するので、登場順が保たれること。"""
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "ナレーター: 一。\n霊夢: 二。\n魔理沙: 三。\n")
    script = parse_script(path, cast)
    assert script.engines_used() == ["qwen", "irodori"]
    assert script.voices_used() == ["ナレーター", "霊夢", "魔理沙"]


def test_fullwidth_colon_is_accepted(tmp_path: Path) -> None:
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "霊夢：全角コロンでも通る。\n")
    script = parse_script(path, cast)
    assert script.lines[0].text == "全角コロンでも通る。"


def test_unknown_speaker_names_the_line(tmp_path: Path) -> None:
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "霊夢: 一。\nこいし: 二。\n")
    with pytest.raises(ScriptError) as excinfo:
        parse_script(path, cast)
    assert "2 行目" in str(excinfo.value)
    assert "こいし" in str(excinfo.value)


def test_unknown_line_option_is_rejected(tmp_path: Path) -> None:
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "霊夢[pitch=2]: 台詞。\n")
    with pytest.raises(ScriptError) as excinfo:
        parse_script(path, cast)
    assert "pitch" in str(excinfo.value)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "霊夢[id=a]: 一。\n魔理沙[id=a]: 二。\n")
    with pytest.raises(ScriptError) as excinfo:
        parse_script(path, cast)
    assert "重複" in str(excinfo.value)


def test_unparsable_line_is_reported_with_line_number(tmp_path: Path) -> None:
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "霊夢: 一。\nコロンのない行\n")
    with pytest.raises(ScriptError) as excinfo:
        parse_script(path, cast)
    assert "2 行目" in str(excinfo.value)


def test_empty_script_is_rejected(tmp_path: Path) -> None:
    cast = parse_cast(cast_file(tmp_path))
    path = write(tmp_path, "ep.txt", "# コメントだけ\n\n")
    with pytest.raises(ScriptError):
        parse_script(path, cast)


def test_load_script_reads_both_files(tmp_path: Path) -> None:
    cast_path = cast_file(tmp_path)
    script_path = write(tmp_path, "ep.txt", "霊夢: 台詞。\n")
    script = load_script(cast_path, script_path)
    assert script.source == script_path
    assert len(script.lines) == 1
