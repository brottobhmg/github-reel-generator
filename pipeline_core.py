"""Core pipeline orchestration.

Runs the full media-generation flow for a single GitHub repository:
1. Fetch README + web context
2. Generate script, description, title, tags
3. Validate JSON metadata
4. Synthesize voice-over (Kokoro)
5. Record GitHub scroll (Playwright)
6. Transcribe audio (Groq Whisper)
7. Assemble final video (MoviePy)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from moviepy.audio.io.AudioFileClip import AudioFileClip

from config import settings
from content import (
    fetch_readme,
    generate_post_description,
    generate_script,
    generate_tags,
    generate_title,
    search_repo_info,
    validate_and_fix_json,
)
from logging_config import get_logger
from tts import generate_tts_local
from video import assemble_final_video, get_word_timestamps_from_groq, record_github_scroll

logger = get_logger(__name__)


def _repo_name(repo_url: str) -> str:
    """Derive the repository folder name from its URL."""
    return repo_url.rstrip("/").split("/")[-1].replace(".git", "")


async def run_pipeline(repo_url: str) -> dict:
    """Run the full pipeline for a repository and return output paths.

    Args:
        repo_url: The GitHub repository URL.

    Returns:
        A dict with ``message``, ``video_path``, ``description_path`` and
        ``repo_name``.
    """
    repo_name = _repo_name(repo_url)
    repo_dir = settings.output_dir / repo_name
    repo_dir.mkdir(parents=True, exist_ok=True)

    tmp_audio = settings.output_dir / "voice.wav"
    tmp_video = settings.output_dir / "scroll.webm"
    final_mp4 = repo_dir / f"{repo_name}_reel.mp4"
    description_path = repo_dir / "descrizione.json"

    logger.info("[1/5] Generating texts...")
    readme_text = fetch_readme(repo_url)
    web_context = search_repo_info(repo_url)

    script = await generate_script(readme_text, web_context)
    logger.info("TTS script generated: %s", script)

    post_desc = await generate_post_description(readme_text, web_context)
    post_desc = f"{post_desc.strip()}\n\n{repo_url}"
    logger.info("Post description generated: %s...", post_desc[:100])

    title = await generate_title(readme_text, web_context)
    logger.info("Title generated: %s", title)

    tags = await generate_tags(readme_text, web_context)
    logger.info("Tags generated: %s", tags)

    desc_data = {
        "testo_tts": script,
        "descrizione_post": post_desc,
        "titolo": title,
        "tag": tags,
    }

    logger.info("Validating JSON metadata with LLM...")
    desc_data = await validate_and_fix_json(desc_data, repo_url)

    with open(description_path, "w", encoding="utf-8") as desc_file:
        json.dump(desc_data, desc_file, ensure_ascii=False, indent=4)
    logger.info("Saved description.json to %s", description_path)

    logger.info("[2/5] Synthesizing voice-over with Kokoro...")
    generate_tts_local(script, str(tmp_audio))
    audio_duration = AudioFileClip(str(tmp_audio)).duration

    logger.info("[3/5] Recording GitHub scroll (duration %.2fs)...", audio_duration)
    await record_github_scroll(repo_url, audio_duration, str(tmp_video))

    logger.info("[4/5] Extracting word timestamps with Groq Whisper...")
    words_data = await get_word_timestamps_from_groq(str(tmp_audio))

    logger.info("[5/5] Rendering final video with MoviePy...")
    assemble_final_video(str(tmp_video), str(tmp_audio), words_data, str(final_mp4))

    # Clean up temporary files.
    for tmp in (tmp_audio, tmp_video):
        if tmp.exists():
            tmp.unlink()

    msg = f"🚀 Pipeline completata con successo! Video salvato in: {final_mp4}"
    logger.info(msg)
    return {
        "message": msg,
        "video_path": str(final_mp4),
        "description_path": str(description_path),
        "repo_name": repo_name,
    }
