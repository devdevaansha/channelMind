import logging
import pathlib
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_MODEL_CACHE: dict = {}


def _get_model(model_size: str, device: str, compute_type: str):
    """Load and cache a WhisperModel. Avoids reloading on every task."""
    from faster_whisper import WhisperModel

    key = f"{model_size}:{device}:{compute_type}"
    if key not in _MODEL_CACHE:
        logger.info(
            "Loading WhisperModel size=%s device=%s compute_type=%s",
            model_size, device, compute_type,
        )
        _MODEL_CACHE[key] = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )
        logger.info("WhisperModel loaded.")
    return _MODEL_CACHE[key]


class WhisperClient:
    """
    Wrapper around faster-whisper for GPU-accelerated transcription.

    IMPORTANT: faster_whisper.transcribe() returns a *lazy generator*.
    It MUST be consumed eagerly here (iterated fully) to:
      1. fire progress callbacks at the right times
      2. avoid cross-thread / cross-process generator issues
    Do NOT return the generator to the caller.
    """

    def __init__(
        self,
        model_size: str = "turbo",
        device: str = "cuda",
        compute_type: str = "int8_float16",
        beam_size: int = 1,
    ):
        self._model = _get_model(model_size, device, compute_type)
        self._beam_size = beam_size

    def transcribe(
        self,
        audio_path: pathlib.Path,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> dict:
        """
        Transcribe audio file.

        Returns:
            {
                "language": str,
                "duration": float,
                "text": str,
                "segments": [{"start": float, "end": float, "text": str}, ...],
            }

        progress_callback receives a float in [0.0, 1.0].
        """
        logger.info("Transcribing %s", audio_path)

        segments_gen, info = self._model.transcribe(
            str(audio_path),
            beam_size=self._beam_size,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )

        duration = info.duration or 1.0
        all_segments = []
        text_parts = []

        # Consume the generator eagerly — this is intentional.
        for seg in segments_gen:
            all_segments.append({
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip(),
            })
            text_parts.append(seg.text)

            if progress_callback:
                pct = min(seg.end / duration, 1.0)
                progress_callback(pct)

        result = {
            "language": info.language,
            "duration": round(duration, 3),
            "text": " ".join(text_parts).strip(),
            "segments": all_segments,
        }

        logger.info(
            "Transcription complete: %d segments, language=%s, duration=%.1fs",
            len(all_segments), info.language, duration,
        )
        return result
