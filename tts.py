"""Local text-to-speech synthesis using Kokoro.

Generates a voice-over WAV file on CPU from a script, without any cloud TTS
dependency.
"""

from __future__ import annotations

import numpy as np
import scipy.io.wavfile as wavfile
from kokoro import KPipeline

from logging_config import get_logger

logger = get_logger(__name__)

#: Kokoro sample rate (Hz).
SAMPLE_RATE = 24000
#: Default voice used for synthesis.
VOICE = "af_heart"


def generate_tts_local(text: str, output_audio_path: str, voice: str = VOICE) -> None:
    """Synthesize speech locally and write it to a WAV file.

    Args:
        text: The text to read aloud.
        output_audio_path: Destination path for the generated WAV file.
        voice: Kokoro voice identifier.

    Raises:
        RuntimeError: If no audio segments are produced.
    """
    logger.info("Loading Kokoro model and synthesizing speech...")
    pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")

    generator = pipeline(text, voice=voice, speed=1.0)
    audio_chunks: list[np.ndarray] = []
    for _, _, audio in generator:
        if audio is not None:
            audio_chunks.append(audio)

    if not audio_chunks:
        raise RuntimeError("Kokoro produced no audio segments.")

    final_audio = np.concatenate(audio_chunks)
    wavfile.write(output_audio_path, SAMPLE_RATE, final_audio)
    logger.info("Audio written to %s", output_audio_path)
