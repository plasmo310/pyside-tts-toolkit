"""Chatterbox Multilingual V3 の runner。

この venv だけが chatterbox-tts / transformers 5.2.0 / torch 2.7.1+cu128 を持つ。
共通層とは stdin/stdout の JSONL でやり取りする（プロトコルは
python/tts_sample/subprocess_engine.py のドキュメント参照）。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# torch より前に import すること（stdout を退避するため）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import runner_base
from runner_base import log, serve, write_wav_pcm16

runner_base.set_engine_name("chatterbox")

import torch  # noqa: E402
from chatterbox.mtl_tts import SUPPORTED_LANGUAGES, ChatterboxMultilingualTTS  # noqa: E402


def resolve_device(requested: str) -> str:
    if requested.startswith("cuda") and not torch.cuda.is_available():
        log("CUDA が使えないため CPU で実行します（かなり遅くなります）。")
        return "cpu"
    return requested


class ChatterboxRunner:
    def __init__(self, options: dict) -> None:
        self.options = options
        self.device = resolve_device(str(options.get("device", "cuda")))
        self.t3_model = options.get("t3_model") or "v3"

        log(f"device={self.device} t3_model={self.t3_model}")
        started = time.monotonic()
        self.model = ChatterboxMultilingualTTS.from_pretrained(
            device=self.device, t3_model=self.t3_model
        )
        log(f"モデルのロード完了 ({time.monotonic() - started:.1f} 秒)")

    @property
    def model_id(self) -> str:
        return f"ResembleAI/chatterbox multilingual {self.t3_model}"

    def synthesize(self, message: dict) -> dict:
        language = message.get("language") or "ja"
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Chatterbox が対応していない言語です: {language}"
                f" (対応: {', '.join(sorted(SUPPORTED_LANGUAGES))})"
            )

        seed = message.get("seed")
        if seed is not None:
            # generate はサンプリングを含むため、再現性はグローバルシードで担保する。
            torch.manual_seed(int(seed))
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(int(seed))

        started = time.monotonic()
        wav = self.model.generate(
            message["text"],
            language_id=language,
            audio_prompt_path=message.get("reference_audio"),
            exaggeration=float(self.options.get("exaggeration", 0.5)),
            cfg_weight=float(self.options.get("cfg_weight", 0.5)),
            temperature=float(self.options.get("temperature", 0.8)),
        )
        elapsed = time.monotonic() - started

        sample_rate = int(self.model.sr)
        frames = write_wav_pcm16(message["output_path"], wav, sample_rate)
        return {
            "sample_rate": sample_rate,
            "duration_sec": frames / sample_rate,
            "elapsed_sec": elapsed,
        }


if __name__ == "__main__":
    sys.exit(serve(ChatterboxRunner))
