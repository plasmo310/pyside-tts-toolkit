"""Qwen3-TTS の runner。

この venv だけが qwen-tts / transformers 4.57.3 / torch cu128 を持つ。

Qwen3-TTS はチェックポイントが用途別に分かれている:
  - Base        : 参照音声からのゼロショットクローン (generate_voice_clone)
  - CustomVoice : プリセット話者 + 自然言語の演技指示 (generate_custom_voice)
リクエストに参照音声があるかどうかで使い分ける。両方を常にロードすると
12GB 級の VRAM を圧迫するので、必要になった時点で初めてロードする。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# torch より前に import すること（stdout を退避するため）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import runner_base
from runner_base import log, serve, write_wav_pcm16

runner_base.set_engine_name("qwen")

import torch  # noqa: E402
from qwen_tts import Qwen3TTSModel  # noqa: E402

# 共通層の言語コード -> Qwen が受け取る言語名。
LANGUAGE_NAMES = {"ja": "Japanese", "en": "English"}

DTYPES = {
    "bfloat16": torch.bfloat16,
    "float16": torch.float16,
    "float32": torch.float32,
}


def resolve_device(requested: str) -> str:
    if requested.startswith("cuda") and not torch.cuda.is_available():
        log("CUDA が使えないため CPU で実行します（かなり遅くなります）。")
        return "cpu"
    return requested


class QwenRunner:
    def __init__(self, options: dict) -> None:
        self.options = options
        self.device = resolve_device(str(options.get("device", "cuda:0")))
        self.dtype = DTYPES[str(options.get("dtype", "bfloat16"))]
        # flash_attention_2 は Windows でビルドが通らないため既定は sdpa。
        self.attn = str(options.get("attn_implementation", "sdpa"))
        self.base_model_id = str(options.get("base_model", "Qwen/Qwen3-TTS-12Hz-1.7B-Base"))
        self.custom_model_id = str(
            options.get("custom_voice_model", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
        )
        self.voice_design_model_id = str(
            options.get("voice_design_model", "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign")
        )
        self.default_speaker = str(options.get("default_speaker", "ono_anna"))
        # 言語ごとの既定話者。Qwen のプリセットは言語色が強いので分けられる。
        self.speakers_by_language = {
            str(k): str(v) for k, v in (options.get("speakers") or {}).items()
        }
        self.max_new_tokens = int(options.get("max_new_tokens", 2048))
        self._models: dict = {}

        log(f"device={self.device} dtype={self.dtype} attn={self.attn}")
        log("モデルはリクエストに応じて遅延ロードします（VRAM 節約のため）。")

    @property
    def model_id(self) -> str:
        return f"{self.base_model_id} / {self.custom_model_id}"

    def _load(self, model_id: str):
        model = self._models.get(model_id)
        if model is not None:
            return model
        log(f"ロード中: {model_id}")
        started = time.monotonic()
        model = Qwen3TTSModel.from_pretrained(
            model_id,
            device_map=self.device,
            dtype=self.dtype,
            attn_implementation=self.attn,
        )
        self._models[model_id] = model
        log(f"ロード完了 ({time.monotonic() - started:.1f} 秒)")
        return model

    def synthesize(self, message: dict) -> dict:
        language_code = message.get("language")
        # None は Qwen 側の自動判定に任せる。
        language = LANGUAGE_NAMES.get(language_code) if language_code else None

        seed = message.get("seed")
        if seed is not None:
            # generate はサンプリングを含むため、再現性はグローバルシードで担保する。
            torch.manual_seed(int(seed))
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(int(seed))

        ref_audio = message.get("reference_audio")
        voice_design = (message.get("voice_design") or "").strip() or None
        started = time.monotonic()

        if voice_design:
            # 文章から架空の声を作る。Qwen では専用チェックポイントが必要で、
            # 参照音声とは併用できない（声の出どころがどちらか 1 つに決まるため）。
            if ref_audio:
                raise ValueError(
                    "Qwen3-TTS では --voice-design と --ref は併用できません。"
                    " 文章から声を作る場合は --ref を外してください。"
                )
            model_id = self.voice_design_model_id
            model = self._load(model_id)
            wavs, sample_rate = model.generate_voice_design(
                text=message["text"],
                instruct=voice_design,
                language=language,
                max_new_tokens=self.max_new_tokens,
            )
        elif ref_audio:
            model_id = self.base_model_id
            model = self._load(model_id)
            ref_text = message.get("reference_text")
            # ref_text が無いと ICL モードを使えない。話者埋め込みだけのモードへ
            # 落とすが、クローン品質は下がるので警告を残す。
            x_vector_only = ref_text is None
            if x_vector_only:
                log(
                    "参照音声の書き起こし (--ref-text) が無いため x_vector_only_mode で"
                    "実行します。クローン品質を上げるには書き起こしを渡してください。"
                )
            wavs, sample_rate = model.generate_voice_clone(
                text=message["text"],
                language=language,
                ref_audio=ref_audio,
                ref_text=ref_text,
                x_vector_only_mode=x_vector_only,
                max_new_tokens=self.max_new_tokens,
            )
        else:
            model_id = self.custom_model_id
            model = self._load(model_id)
            speaker = self._resolve_speaker(model, language_code)
            wavs, sample_rate = model.generate_custom_voice(
                text=message["text"],
                speaker=speaker,
                language=language,
                instruct=self.options.get("instruct") or None,
                max_new_tokens=self.max_new_tokens,
            )

        elapsed = time.monotonic() - started
        if not wavs:
            raise RuntimeError("Qwen3-TTS が音声を返しませんでした。")

        frames = write_wav_pcm16(message["output_path"], wavs[0], sample_rate)
        return {
            "sample_rate": int(sample_rate),
            "duration_sec": frames / int(sample_rate),
            "elapsed_sec": elapsed,
            "model_id": model_id,
        }

    def _resolve_speaker(self, model, language_code: str | None) -> str:
        wanted = self.speakers_by_language.get(language_code or "", self.default_speaker)
        speakers = model.get_supported_speakers() or []
        if not speakers:
            return wanted
        # 話者 ID は小文字。設定で大文字始まりを書いても通るようにする。
        lookup = {s.lower(): s for s in speakers}
        if wanted.lower() in lookup:
            return lookup[wanted.lower()]
        raise ValueError(
            f"話者 '{wanted}' はこのモデルにありません。"
            f" engines.toml の [qwen.options.speakers] を次から選んでください:"
            f" {', '.join(speakers)}"
        )


if __name__ == "__main__":
    sys.exit(serve(QwenRunner))
