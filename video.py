"""Video generation: GitHub scroll recording, transcription and final assembly.

Uses Playwright to record a scrolling capture of the repository page, Groq
Whisper to obtain word-level timestamps, and MoviePy to composite the final
reel with karaoke-style subtitles.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.VideoClip import TextClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.video.io.VideoFileClip import VideoFileClip
from playwright.async_api import async_playwright

from config import settings
from llm import groq_client
from logging_config import get_logger

logger = get_logger(__name__)

#: Maximum scroll speed in px/s used to keep the capture readable.
MAX_SCROLL_SPEED = 100.0
#: Number of words grouped per subtitle chunk.
WORDS_PER_CHUNK = 3
#: Vertical position of subtitles as a fraction of video height.
SUBTITLE_Y_FRACTION = 0.83


async def record_github_scroll(
    url: str, duration: float, output_video_path: str
) -> None:
    """Record a scrolling capture of a GitHub page with Playwright.

    Args:
        url: The repository URL to record.
        duration: Duration of the recording in seconds.
        output_video_path: Destination path for the remuxed WebM file.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 "
                "Mobile/15E148 Safari/604.1"
            ),
            device_scale_factor=2,
            viewport={"width": 1000, "height": 1350},
            is_mobile=True,
            has_touch=True,
            record_video_dir=str(settings.videos_dir),
        )
        page = await context.new_page()

        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(int(settings.load_delay * 1000))
        await page.evaluate("document.body.style.zoom = '1.0'")

        total_scroll = await page.evaluate(
            "document.body.scrollHeight - window.innerHeight"
        )
        # Diagnostic: also measure scrollHeight on documentElement and the
        # actual scrollable height, since GitHub may scroll on a different
        # container than document.body.
        diag = await page.evaluate(
            """() => ({
                bodyScrollHeight: document.body.scrollHeight,
                docScrollHeight: document.documentElement.scrollHeight,
                innerHeight: window.innerHeight,
                bodyClientHeight: document.body.clientHeight,
                docClientHeight: document.documentElement.clientHeight,
            })"""
        )
        print(f"[SCROLL-DIAG] {diag}")
        print(f"[SCROLL-DIAG] total_scroll (body) = {total_scroll}px")

        if total_scroll > 0 and duration > 0:
            scroll_speed = min(MAX_SCROLL_SPEED, total_scroll / duration)
        else:
            scroll_speed = 0.0

        logger.info(
            "Scroll info: height=%dpx, duration=%.2fs -> speed=%.2f px/s",
            total_scroll,
            duration,
            scroll_speed,
        )
        print(
            f"[SCROLL-DIAG] duration={duration}s, scroll_speed={scroll_speed:.2f} px/s"
        )

        # Scroll in-browser: a single evaluate runs the animation inside the
        # page at 60 fps (requestAnimationFrame) with a setInterval fallback.
        # Position is computed from elapsed time, so throttled/dropped frames
        # cannot stall or stutter the scroll. A Python-side loop (evaluate +
        # sleep per step) caused visible lag in the recording.
        await page.evaluate(
            """({ duration, maxScroll }) => new Promise((resolve) => {
                const durationMs = duration * 1000;
                const scroller = document.scrollingElement || document.documentElement;
                const limit = Math.max(0, Math.min(
                    maxScroll, scroller.scrollHeight - window.innerHeight
                ));
                const start = performance.now();
                let finished = false;
                const finish = () => {
                    if (!finished) { finished = true; clearInterval(timer); resolve(); }
                };
                const step = () => {
                    const t = Math.min((performance.now() - start) / durationMs, 1);
                    window.scrollTo(0, t * limit);
                    if (t >= 1) finish();
                };
                const timer = setInterval(step, 16);
                const raf = () => { step(); if (!finished) requestAnimationFrame(raf); };
                requestAnimationFrame(raf);
            })""",
            {"duration": duration, "maxScroll": max(total_scroll, 0)},
        )

        # Diagnostic: verify the final scroll position actually applied.
        final_pos = await page.evaluate("window.scrollY")
        print(f"[SCROLL-DIAG] final scrollY = {final_pos}px (expected ~{total_scroll}px)")

        video_path = await page.video.path()
        await browser.close()

        # Remux to fix missing WebM duration metadata (required by MoviePy).
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-c", "copy", output_video_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


async def get_word_timestamps_from_groq(audio_path: str) -> list[dict]:
    """Transcribe audio with Groq Whisper and return word-level timestamps.

    Args:
        audio_path: Path to the audio file.

    Returns:
        A list of ``{"text", "start", "end"}`` dictionaries.

    Raises:
        RuntimeError: If the Groq client is not configured.
    """
    if groq_client is None:
        raise RuntimeError("GROQ_API_KEY is not configured; cannot transcribe audio.")

    with open(audio_path, "rb") as file:
        transcription = await groq_client.audio.transcriptions.create(
            file=(os.path.basename(audio_path), file.read()),
            model="whisper-large-v3",
            response_format="verbose_json",
            language="en",
            timestamp_granularities=["word"],
        )

    transcription_dict = (
        transcription if isinstance(transcription, dict) else transcription.model_dump()
    )
    words_data: list[dict] = []
    for word in transcription_dict.get("words", []):
        words_data.append(
            {"text": word["word"], "start": word["start"], "end": word["end"]}
        )
    return words_data


def _resolve_overlaps(words_data: list[dict]) -> list[dict]:
    """Resolve temporal overlaps between consecutive words."""
    sorted_words = sorted(words_data, key=lambda w: w["start"])
    for i in range(len(sorted_words) - 1):
        curr, nxt = sorted_words[i], sorted_words[i + 1]
        if curr["end"] > nxt["start"]:
            curr["end"] = nxt["start"]
            if curr["end"] <= curr["start"]:
                curr["end"] = curr["start"] + 0.05
                nxt["start"] = curr["end"]
    return sorted_words


def assemble_final_video(
    video_path: str, audio_path: str, words_data: list[dict], output_path: str
) -> None:
    """Composite the final reel with subtitles and audio.

    Args:
        video_path: Path to the recorded WebM.
        audio_path: Path to the voice-over WAV.
        words_data: Word-level timestamps.
        output_path: Destination MP4 path.
    """
    video_clip = VideoFileClip(video_path)
    audio_clip = AudioFileClip(audio_path)

    sorted_words = _resolve_overlaps(words_data)

    # Trim the loading screen and attach the audio track.
    video_clip = video_clip.subclip(settings.load_delay, settings.load_delay + audio_clip.duration)
    video_clip = video_clip.set_audio(audio_clip)

    valid_words = [w for w in sorted_words if w["start"] < audio_clip.duration]
    chunks = [
        valid_words[i : i + WORDS_PER_CHUNK]
        for i in range(0, len(valid_words), WORDS_PER_CHUNK)
    ]

    txt_clips = []
    for chunk in chunks:
        if not chunk:
            continue
        chunk_text = " ".join(w["text"].upper() for w in chunk)
        chunk_start = chunk[0]["start"]
        chunk_end = min(chunk[-1]["end"], audio_clip.duration)
        if chunk_end <= chunk_start:
            chunk_end = chunk_start + 0.1

        txt_clip = TextClip(
            txt=chunk_text,
            fontsize=38,
            color="white",
            stroke_color="black",
            stroke_width=2,
            font="Lato-Black",
            size=(int(video_clip.w * 0.85), None),
            method="caption",
        )
        txt_clip = txt_clip.set_start(chunk_start).set_end(chunk_end)
        target_y = int(video_clip.h * SUBTITLE_Y_FRACTION)
        txt_clip = txt_clip.set_position(("center", target_y))
        txt_clips.append(txt_clip)

    final_video = CompositeVideoClip([video_clip] + txt_clips)
    final_video.write_videofile(output_path, fps=60, codec="libx264", audio_codec="aac")
    logger.info("Final video written to %s", output_path)
