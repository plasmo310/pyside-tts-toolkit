"""共通層の検証。実モデルを使わずダミー runner でプロトコルを確認する。"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import pytest

from tts_sample.subprocess_engine import SubprocessEngine
from tts_sample.types import (
    Capability,
    EngineProcessError,
    EngineSpec,
    SynthesisRequest,
    UnsupportedLanguageError,
    UnsupportedParameterError,
)

HERE = Path(__file__).resolve().parent
FAKE_RUNNER = HERE / "fake_runner.py"

JA_TEXT = "こんにちは。音声合成のテストです。絵文字も🤭通ること。"


def make_spec(**overrides) -> EngineSpec:
    defaults = {
        "name": "fake",
        "description": "テスト用",
        "capabilities": Capability.CLONE | Capability.SEED | Capability.MULTILINGUAL,
        "languages": ("ja", "en"),
        "model_id": "fake-model",
        "python": Path(sys.executable),
        "runner": FAKE_RUNNER,
        "cwd": HERE,
        "setup_doc": "README.md",
        "options": {"model_id": "fake-model"},
        "env": {},
    }
    defaults.update(overrides)
    return EngineSpec(**defaults)


def read_wav(path: Path) -> tuple[int, int]:
    with wave.open(str(path), "rb") as wf:
        return wf.getframerate(), wf.getnframes()


def test_roundtrip_japanese(tmp_path: Path) -> None:
    """日本語と絵文字が UTF-8 のまま往復し、wav が出ること。"""
    out = tmp_path / "a.wav"
    with SubprocessEngine(make_spec()) as engine:
        result = engine.synthesize(SynthesisRequest(text=JA_TEXT, output_path=out, language="ja"))
    assert out.is_file()
    rate, frames = read_wav(out)
    assert rate == result.sample_rate == 24000
    assert frames > 0
    assert result.model_id == "fake-model"
    assert result.engine == "fake"


def test_model_stays_loaded_across_requests(tmp_path: Path) -> None:
    """1 プロセスで複数件を処理できること（バッチでロードを繰り返さない根拠）。"""
    with SubprocessEngine(make_spec()) as engine:
        results = engine.synthesize_many(
            [
                SynthesisRequest(text=f"{i} 件目です。", output_path=tmp_path / f"{i}.wav")
                for i in range(3)
            ]
        )
    assert len(results) == 3
    assert all(r.output_path.is_file() for r in results)


def test_stdout_pollution_is_isolated(tmp_path: Path) -> None:
    """runner 内の print が stdout を汚してもプロトコルが壊れないこと。

    fake_runner は起動時に print() を呼ぶ。それが stderr に逃げているので
    ready と応答の読み取りが成功する。
    """
    with SubprocessEngine(make_spec()) as engine:
        engine.synthesize(SynthesisRequest(text="テスト", output_path=tmp_path / "b.wav"))


def test_unsupported_language_fails_before_launch(tmp_path: Path) -> None:
    """未対応言語は runner を起動せずに弾かれること。"""
    spec = make_spec(
        languages=("ja",),
        capabilities=Capability.CLONE | Capability.SEED,
        python=Path("C:/does-not-exist/python.exe"),  # 起動したら必ず失敗するパス
    )
    engine = SubprocessEngine(spec)
    with pytest.raises(UnsupportedLanguageError):
        engine.synthesize(
            SynthesisRequest(text="Hello.", output_path=tmp_path / "c.wav", language="en")
        )


def test_unsupported_speed_is_explicit_error(tmp_path: Path) -> None:
    """speed 非対応エンジンに speed を渡すと、黙殺されずエラーになること。"""
    engine = SubprocessEngine(make_spec(python=Path("C:/does-not-exist/python.exe")))
    with pytest.raises(UnsupportedParameterError):
        engine.synthesize(
            SynthesisRequest(text="テスト", output_path=tmp_path / "d.wav", speed=1.5)
        )


def test_unsupported_seed_is_explicit_error(tmp_path: Path) -> None:
    engine = SubprocessEngine(
        make_spec(capabilities=Capability.CLONE, python=Path("C:/does-not-exist/python.exe"))
    )
    with pytest.raises(UnsupportedParameterError):
        engine.synthesize(SynthesisRequest(text="テスト", output_path=tmp_path / "e.wav", seed=1))


def test_runner_failure_surfaces_traceback(tmp_path: Path) -> None:
    """runner 側の例外が親までトレースバック付きで届くこと。"""
    spec = make_spec(options={"model_id": "fake-model", "fail_on_text": "壊れろ"})
    with SubprocessEngine(spec) as engine, pytest.raises(EngineProcessError) as excinfo:
        engine.synthesize(SynthesisRequest(text="壊れろ", output_path=tmp_path / "f.wav"))
    assert "テスト用の意図的な失敗" in str(excinfo.value)


def test_engine_recovers_after_failure(tmp_path: Path) -> None:
    """1 件失敗しても同じプロセスで次を処理できること（batch --keep-going の前提）。"""
    spec = make_spec(options={"model_id": "fake-model", "fail_on_text": "壊れろ"})
    with SubprocessEngine(spec) as engine:
        with pytest.raises(EngineProcessError):
            engine.synthesize(SynthesisRequest(text="壊れろ", output_path=tmp_path / "g.wav"))
        result = engine.synthesize(
            SynthesisRequest(text="次は成功する。", output_path=tmp_path / "h.wav")
        )
    assert result.output_path.is_file()


def test_missing_venv_is_reported(tmp_path: Path) -> None:
    engine = SubprocessEngine(make_spec(python=Path("C:/does-not-exist/python.exe")))
    with pytest.raises(Exception) as excinfo:
        engine.start()
    assert "venv" in str(excinfo.value)


def test_close_is_idempotent(tmp_path: Path) -> None:
    engine = SubprocessEngine(make_spec())
    engine.start()
    engine.close()
    engine.close()


def test_empty_text_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        SynthesisRequest(text="   ", output_path=tmp_path / "i.wav")


def test_missing_reference_audio_is_reported(tmp_path: Path) -> None:
    """参照音声が無い場合は FileNotFoundError になること。

    batch の --keep-going はこの例外も捕まえる必要がある（TTSError ではない）。
    """
    engine = SubprocessEngine(make_spec(python=Path("C:/does-not-exist/python.exe")))
    with pytest.raises(FileNotFoundError):
        engine.synthesize(
            SynthesisRequest(
                text="テスト",
                output_path=tmp_path / "j.wav",
                reference_audio=tmp_path / "missing.wav",
            )
        )
