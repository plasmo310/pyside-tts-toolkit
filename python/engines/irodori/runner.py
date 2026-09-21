"""Irodori-TTS v4.1 Small の runner。

Irodori は PyPI 未公開（依存の dacvae も PyPI に無い）ため、上流リポジトリを
vendor/Irodori-TTS へ clone し、そのリポジトリ自身の venv を使う。
この runner は cwd = vendor/Irodori-TTS で起動され、irodori_tts を import する。

infer.py を毎回 CLI として叩くとリクエストごとにモデルをロードし直すので、
内部 API（InferenceRuntime）を直接使ってモデルを常駐させる。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# torch より前に import すること（stdout を退避するため）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import runner_base
from runner_base import log, serve, write_wav_pcm16

runner_base.set_engine_name("irodori")

import torch  # noqa: E402

# 上流リポジトリは非パッケージ扱い（build-system が無い）で venv には入らないため、
# clone したリポジトリルートを sys.path に足して irodori_tts を import する。
# cwd は subprocess_engine が同じディレクトリに設定するが、Python はスクリプトの
# 置き場所しか sys.path に入れないので、ここで明示する。
_VENDOR = Path(__file__).resolve().parent / "vendor" / "Irodori-TTS"
if not (_VENDOR / "irodori_tts").is_dir():
    raise SystemExit(
        f"Irodori-TTS の clone が見つかりません: {_VENDOR}\n"
        "docs/setup/03_irodori-tts.md の手順で clone してください。"
    )
sys.path.insert(0, str(_VENDOR))

from irodori_tts.inference_runtime import (  # noqa: E402
    InferenceRuntime,
    RuntimeKey,
    SamplingRequest,
    default_runtime_device,
    download_hf_checkpoint,
    resolve_cfg_scales,
)


class IrodoriRunner:
    def __init__(self, options: dict) -> None:
        self.options = options
        self.checkpoint_repo = str(options.get("hf_checkpoint", "Aratako/Irodori-TTS-v4.1-Small"))
        device = str(options.get("device") or default_runtime_device())
        if device.startswith("cuda") and not torch.cuda.is_available():
            log("CUDA が使えないため CPU で実行します（かなり遅くなります）。")
            device = "cpu"

        log(f"チェックポイントを取得中: {self.checkpoint_repo}")
        checkpoint_path = download_hf_checkpoint(self.checkpoint_repo)

        log(f"モデルをロード中 (device={device})")
        started = time.monotonic()
        self.runtime = InferenceRuntime.from_key(
            RuntimeKey(
                checkpoint=str(checkpoint_path),
                model_device=device,
                codec_repo=str(options.get("codec_repo", "Aratako/Semantic-DACVAE-Japanese-32dim")),
                model_precision=str(options.get("model_precision", "fp32")),
                codec_device=str(options.get("codec_device", "cpu")),
                codec_precision=str(options.get("codec_precision", "fp32")),
            )
        )
        log(f"ロード完了 ({time.monotonic() - started:.1f} 秒)")

    @property
    def model_id(self) -> str:
        return self.checkpoint_repo

    def synthesize(self, message: dict) -> dict:
        language = message.get("language")
        if language not in (None, "ja"):
            raise ValueError(f"Irodori-TTS は日本語専用です（指定: {language}）。")

        ref_wav = message.get("reference_audio")
        no_ref = ref_wav is None
        # Voice Design（文章による声の設計）。リクエストの指定が engines.toml の
        # 既定値より優先される。参照音声と併用でき、その場合は
        # 声質が参照音声・話し方が caption になる。
        caption = (
            message.get("voice_design")
            or message.get("caption")
            or self.options.get("caption")
            or None
        )
        if caption is not None and not str(caption).strip():
            caption = None

        model_cfg = self.runtime.model_cfg
        use_speaker = bool(model_cfg.use_speaker_condition_resolved and not no_ref)
        cfg_text, cfg_caption, cfg_speaker, messages = resolve_cfg_scales(
            cfg_guidance_mode=str(self.options.get("cfg_guidance_mode", "independent")),
            cfg_scale_text=float(self.options.get("cfg_scale_text", 3.0)),
            cfg_scale_caption=float(self.options.get("cfg_scale_caption", 3.0)),
            cfg_scale_speaker=float(self.options.get("cfg_scale_speaker", 5.0)),
            cfg_scale=None,
            use_caption_condition=bool(model_cfg.use_caption_condition and caption),
            use_speaker_condition=use_speaker,
        )
        for msg in messages:
            log(msg)

        # 共通層の speed は「速いほど短い」。Irodori の duration_scale は
        # 「大きいほど長い」ので逆数を渡す。
        speed = float(message.get("speed") or 1.0)
        duration_scale = 1.0 / speed

        num_steps = self.options.get("num_steps")
        request = SamplingRequest(
            text=message["text"],
            caption=caption,
            ref_wav=ref_wav,
            no_ref=no_ref,
            seed=message.get("seed"),
            duration_scale=duration_scale,
            num_steps=int(num_steps) if num_steps else None,
            cfg_scale_text=cfg_text,
            cfg_scale_caption=cfg_caption,
            cfg_scale_speaker=cfg_speaker,
            cfg_guidance_mode=str(self.options.get("cfg_guidance_mode", "independent")),
        )

        started = time.monotonic()
        result = self.runtime.synthesize(request, log_fn=log)
        elapsed = time.monotonic() - started

        for msg in result.messages or []:
            log(msg)

        sample_rate = int(result.sample_rate)
        frames = write_wav_pcm16(message["output_path"], result.audio, sample_rate)
        return {
            "sample_rate": sample_rate,
            "duration_sec": frames / sample_rate,
            "elapsed_sec": elapsed,
        }


if __name__ == "__main__":
    sys.exit(serve(IrodoriRunner))
