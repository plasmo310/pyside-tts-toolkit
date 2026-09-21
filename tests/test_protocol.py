"""共通層の検証。実モデルを使わずダミー runner でプロトコルを確認する。"""

from __future__ import annotations

import os
import subprocess
import sys
import wave

import pytest

from ttstoolkit.core.paths import PYTHON_DIR
from ttstoolkit.core.subprocess_engine import SubprocessEngine
from ttstoolkit.core.types import (
    Capability,
    EngineNotInstalledError,
    EngineProcessError,
    EngineSpec,
    UnsupportedLanguageError,
    UnsupportedParameterError,
)
from ttstoolkit.engine._shared.protocol import (
    SynthesisRequest,
    SynthesisResponse,
)

HERE = os.path.dirname(os.path.abspath(__file__))

# 起動したら必ず失敗するパス。validate() が起動前に弾くことの確認に使う
MISSING_PYTHON = os.path.join(HERE, "does-not-exist", "python.exe")

JA_TEXT = "こんにちは。音声合成のテストです。絵文字も🤭通ること。"


def make_spec(**overrides: object) -> EngineSpec:
    """ダミー runner を指す定義を作る。

    Args:
        **overrides: 差し替えたいフィールド。

    Returns:
        EngineSpec: テスト用の定義。
    """
    defaults = {
        "name": "fake",
        "description": "for tests",
        "capabilities": (
            Capability.CLONE | Capability.SEED | Capability.MULTILINGUAL
        ),
        "languages": ("ja", "en"),
        "model_id": "fake-model",
        "python": sys.executable,
        "runner": "fake_runner",
        "cwd": HERE,
        "setup_doc": "README.md",
        "options": {"model_id": "fake-model"},
        "python_path": (PYTHON_DIR, HERE),
    }
    defaults.update(overrides)
    return EngineSpec(**defaults)


def read_wav(path: str) -> tuple[int, int]:
    """wav のサンプリングレートとフレーム数を返す。

    Args:
        path: wav のパス。

    Returns:
        tuple[int, int]: サンプリングレートとフレーム数。
    """
    with wave.open(path, "rb") as wav_file:
        return wav_file.getframerate(), wav_file.getnframes()


def test_roundtrip_japanese(tmp_path) -> None:
    """日本語と絵文字が UTF-8 のまま往復し、wav が出ること。"""
    output = str(tmp_path / "a.wav")
    with SubprocessEngine(make_spec()) as engine:
        result = engine.synthesize(
            SynthesisRequest(text=JA_TEXT, output_path=output, language="ja")
        )
    assert os.path.isfile(output)
    rate, frames = read_wav(output)
    assert rate == result.sample_rate == 24000
    assert frames > 0
    assert result.model_id == "fake-model"
    assert result.engine == "fake"


def test_model_stays_loaded_across_requests(tmp_path) -> None:
    """1 プロセスで複数件を処理できること。

    バッチでモデルのロードを繰り返さない根拠になる。
    """
    with SubprocessEngine(make_spec()) as engine:
        results = [
            engine.synthesize(
                SynthesisRequest(
                    text=f"{index} 件目です。",
                    output_path=str(tmp_path / f"{index}.wav"),
                )
            )
            for index in range(3)
        ]
    assert len(results) == 3
    assert all(os.path.isfile(result.output_path) for result in results)


def test_stdout_pollution_is_isolated(tmp_path) -> None:
    """runner 内の print が stdout を汚してもプロトコルが壊れないこと。

    fake_runner は起動時に print() を呼ぶ。それが stderr に逃げている
    ので ready と応答の読み取りが成功する。
    """
    with SubprocessEngine(make_spec()) as engine:
        engine.synthesize(
            SynthesisRequest(
                text="テスト", output_path=str(tmp_path / "b.wav")
            )
        )


def test_unsupported_language_fails_before_launch(tmp_path) -> None:
    """未対応言語は runner を起動せずに弾かれること。"""
    spec = make_spec(
        languages=("ja",),
        capabilities=Capability.CLONE | Capability.SEED,
        python=MISSING_PYTHON,
    )
    with pytest.raises(UnsupportedLanguageError):
        SubprocessEngine(spec).synthesize(
            SynthesisRequest(
                text="Hello.",
                output_path=str(tmp_path / "c.wav"),
                language="en",
            )
        )


def test_unsupported_speed_is_explicit_error(tmp_path) -> None:
    """speed 非対応エンジンに speed を渡すと、黙殺されずエラーになること。"""
    engine = SubprocessEngine(make_spec(python=MISSING_PYTHON))
    with pytest.raises(UnsupportedParameterError):
        engine.synthesize(
            SynthesisRequest(
                text="テスト",
                output_path=str(tmp_path / "d.wav"),
                speed=1.5,
            )
        )


def test_unsupported_seed_is_explicit_error(tmp_path) -> None:
    """seed 非対応エンジンに seed を渡すとエラーになること。"""
    engine = SubprocessEngine(
        make_spec(capabilities=Capability.CLONE, python=MISSING_PYTHON)
    )
    with pytest.raises(UnsupportedParameterError):
        engine.synthesize(
            SynthesisRequest(
                text="テスト",
                output_path=str(tmp_path / "e.wav"),
                seed=1,
            )
        )


def test_unsupported_voice_design_is_explicit_error(tmp_path) -> None:
    """Voice Design 非対応エンジンに指示を渡すとエラーになること。"""
    engine = SubprocessEngine(make_spec(python=MISSING_PYTHON))
    with pytest.raises(UnsupportedParameterError):
        engine.synthesize(
            SynthesisRequest(
                text="テスト",
                output_path=str(tmp_path / "f.wav"),
                voice_design="落ち着いた低い声",
            )
        )


def test_runner_failure_surfaces_traceback(tmp_path) -> None:
    """runner 側の例外が親までトレースバック付きで届くこと。"""
    spec = make_spec(
        options={"model_id": "fake-model", "fail_on_text": "壊れろ"}
    )
    with (
        SubprocessEngine(spec) as engine,
        pytest.raises(EngineProcessError) as error,
    ):
        engine.synthesize(
            SynthesisRequest(
                text="壊れろ", output_path=str(tmp_path / "g.wav")
            )
        )
    assert "deliberate failure for tests" in str(error.value)


def test_engine_recovers_after_failure(tmp_path) -> None:
    """1 件失敗しても同じプロセスで次を処理できること。

    batch の --keep-going が成り立つ前提になる。
    """
    spec = make_spec(
        options={"model_id": "fake-model", "fail_on_text": "壊れろ"}
    )
    with SubprocessEngine(spec) as engine:
        with pytest.raises(EngineProcessError):
            engine.synthesize(
                SynthesisRequest(
                    text="壊れろ", output_path=str(tmp_path / "h.wav")
                )
            )
        result = engine.synthesize(
            SynthesisRequest(
                text="次は成功する。", output_path=str(tmp_path / "i.wav")
            )
        )
    assert os.path.isfile(result.output_path)


def test_missing_venv_is_reported() -> None:
    """仮想環境が無いときは手順への案内が出ること。"""
    engine = SubprocessEngine(make_spec(python=MISSING_PYTHON))
    with pytest.raises(EngineNotInstalledError) as error:
        engine.start()
    assert "setup_engines" in str(error.value)


def test_close_is_idempotent() -> None:
    """close() を重ねて呼んでも安全なこと。"""
    engine = SubprocessEngine(make_spec())
    engine.start()
    engine.close()
    engine.close()


def test_empty_text_rejected(tmp_path) -> None:
    """空のテキストはリクエストを作った時点で弾かれること。"""
    with pytest.raises(ValueError):
        SynthesisRequest(text="   ", output_path=str(tmp_path / "j.wav"))


def test_missing_reference_audio_is_reported(tmp_path) -> None:
    """参照音声が無い場合は FileNotFoundError になること。

    batch の --keep-going はこの例外も捕まえる必要がある
    (TTSToolkitError ではないため)。
    """
    engine = SubprocessEngine(make_spec(python=MISSING_PYTHON))
    with pytest.raises(FileNotFoundError):
        engine.synthesize(
            SynthesisRequest(
                text="テスト",
                output_path=str(tmp_path / "k.wav"),
                reference_audio=str(tmp_path / "missing.wav"),
            )
        )


# ---------------------------------------------------------------------
# 契約そのもの
# ---------------------------------------------------------------------


def test_request_survives_a_json_round_trip(tmp_path) -> None:
    """リクエストが JSON を往復しても同じ内容であること。"""
    original = SynthesisRequest(
        text=JA_TEXT,
        output_path=str(tmp_path / "a.wav"),
        language="ja",
        reference_audio=None,
        reference_text="書き起こし",
        voice_design="落ち着いた低い声",
        seed=42,
        speed=1.25,
    )
    assert SynthesisRequest.from_json(original.to_json()) == original


def test_request_ignores_envelope_keys(tmp_path) -> None:
    """封筒のキーが混ざっていても読めること。

    runner は封筒ごと `from_json()` に渡すので、これが成り立つ必要がある。
    """
    payload = SynthesisRequest(
        text="テスト", output_path=str(tmp_path / "b.wav")
    ).to_json()
    payload.update({"op": "synthesize", "id": 7})
    assert SynthesisRequest.from_json(payload).text == "テスト"


def test_response_survives_a_json_round_trip() -> None:
    """レスポンスが JSON を往復しても同じ内容であること。"""
    original = SynthesisResponse(
        sample_rate=48000,
        duration_sec=3.25,
        elapsed_sec=1.5,
        model_id="Aratako/Irodori-TTS-v4.1-Small",
    )
    assert SynthesisResponse.from_json(original.to_json()) == original


def test_broken_response_is_rejected() -> None:
    """項目が足りないレスポンスはその場で弾かれること。"""
    with pytest.raises(ValueError):
        SynthesisResponse.from_json({"sample_rate": 24000})


def test_importing_core_does_not_hijack_stdout() -> None:
    """core を読み込んでも標準出力が差し替わらないこと。

    `engine/_shared/runner_base.py` は import した時点で `sys.stdout` を
    `sys.stderr` に差し替える。親プロセス側がうっかりあれを引き込むと
    CLI の表示が丸ごと壊れるので、ここで検出する。
    """
    code = (
        "import sys;"
        "import ttstoolkit.core.subprocess_engine;"
        "import ttstoolkit.core.jobs;"
        "import ttstoolkit.cli.commands;"
        "print('clean' if sys.stdout is not sys.stderr else 'hijacked')"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONPATH": PYTHON_DIR},
        check=True,
    )
    assert completed.stdout.strip() == "clean"
