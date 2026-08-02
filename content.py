"""Content generation: script, post description, title, tags and JSON validation.

All text-generation helpers call the resilient LLM layer in :mod:`llm` and
return clean, ready-to-publish strings.
"""

from __future__ import annotations

import json
import re
import urllib.request

from ddgs import DDGS

from llm import safe_chat_completion
from logging_config import get_logger

logger = get_logger(__name__)

#: Tags that must always appear first in the generated tag list.
ALWAYS_FIRST_TAGS = ["foryou", "github"]
#: Generic tags appended when not already present.
GENERIC_TAGS = ["open source", "open", "privacy"]
#: Maximum length (excluding commas) of the final tag string.
MAX_TAGS_LENGTH = 450
#: Maximum title length in characters.
MAX_TITLE_LENGTH = 100
#: Maximum README characters fetched for context.
MAX_README_CHARS = 3000

GITHUB_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/[a-zA-Z0-9-]+/[a-zA-Z0-9_.-]+"
)


def fetch_readme(repo_url: str) -> str:
    """Download the README of a GitHub repository via the raw API.

    Args:
        repo_url: A GitHub repository URL.

    Returns:
        The README content (truncated) or a fallback string on failure.
    """
    repo_url = repo_url.rstrip("/")
    if "raw.githubusercontent.com" in repo_url:
        raw_url = repo_url
    else:
        parts = repo_url.replace("https://github.com/", "").split("/")
        owner, repo = parts[0], parts[1]
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/README.md"
    try:
        req = urllib.request.Request(raw_url, headers={"User-Agent": "devtok-pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode("utf-8", errors="ignore")
        return content[:MAX_README_CHARS]
    except Exception as exc:  # noqa: BLE001 - network fallback
        logger.warning("Could not download README: %s", exc)
        return f"GitHub repository: {repo_url}"


def search_repo_info(repo_url: str) -> str:
    """Search DuckDuckGo for extra context about a repository.

    Args:
        repo_url: A GitHub repository URL.

    Returns:
        A text summary of the top search results, or an empty string.
    """
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    query = f"{repo_name} github repository what is it what does it do"
    logger.info("Searching DuckDuckGo for: %s", query)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if results:
                summary = [
                    f"Title: {r.get('title')}\nSnippet: {r.get('body')}"
                    for r in results
                ]
                logger.info("Found %d search results.", len(results))
                return "\n\n".join(summary)
    except Exception as exc:  # noqa: BLE001 - network fallback
        logger.warning("DuckDuckGo search failed for %s: %s", repo_name, exc)
    return ""


def _build_reference(readme_text: str, web_context: str = "") -> str:
    """Combine README and optional web context into a single reference block."""
    reference = f"README:\n{readme_text}"
    if web_context:
        reference += f"\n\nAdditional Web Context:\n{web_context}"
    return reference


async def generate_script(readme_text: str, web_context: str = "") -> str:
    """Generate the voice-over script for the reel.

    Args:
        readme_text: The repository README text.
        web_context: Optional extra web context.

    Returns:
        The script text with a call-to-action appended.
    """
    reference = _build_reference(readme_text, web_context)
    prompt = (
        "You are an expert tech content creator. Summarize the following GitHub repository text "
        "into a script for an engaging reel/short with a maximum duration of around 40 seconds. "
        "Use short, high-impact sentences. Return ONLY and EXCLUSIVELY the text to be read aloud, "
        "without any intro, outro, direction notes, or comments.\n"
        "IMPORTANT RULES:\n"
        "- Do NOT include or read explicit commands, code snippets, or installation instructions "
        "(e.g. do NOT say 'run pip install', 'git clone', or 'docker compose up --build').\n"
        "- Instead, briefly mention the tools or requirements at a high level using simple conversational "
        "terms (e.g. say 'it supports docker compose', 'runs on python', 'requires a database').\n"
        "- Focus on what the tool is, what it does, and why it is awesome.\n\n"
        f"Text to summarize:\n{reference}"
    )
    script_text = await safe_chat_completion(prompt, temperature=0.7)
    script_text = script_text.replace("'", "'").replace("\u201c", '"').replace("\u201d", '"')

    cta = "Link in description. Follow for more open-source repo."
    if cta.lower() not in script_text.lower():
        script_text = f"{script_text.strip()} {cta}"
    return script_text


def limit_title(title_input: str) -> str:
    """Trim a title to at most :data:`MAX_TITLE_LENGTH` characters.

    Args:
        title_input: The raw title.

    Returns:
        The trimmed title.
    """
    title = title_input.strip().replace("\n", " ")
    if len(title) > MAX_TITLE_LENGTH:
        title = title[:MAX_TITLE_LENGTH]
        if " " in title:
            title = title.rsplit(" ", 1)[0]
        title = title.strip()
    return title


def format_and_limit_tags(tags_input: str) -> str:
    """Normalize and limit a tag list to :data:`MAX_TAGS_LENGTH` characters.

    Args:
        tags_input: Raw tags separated by commas or spaces.

    Returns:
        A comma-separated tag string.
    """
    raw_tags: list[str] = []
    parts = tags_input.split(",") if "," in tags_input else tags_input.split()
    always_first_lower = [t.lower() for t in ALWAYS_FIRST_TAGS]

    for part in parts:
        cleaned = part.strip().replace("#", "")
        if cleaned and cleaned.lower() not in always_first_lower:
            raw_tags.append(cleaned)

    all_tags = ALWAYS_FIRST_TAGS + raw_tags
    all_tags_lower = [t.lower() for t in all_tags]
    for generic in GENERIC_TAGS:
        if generic.lower() not in all_tags_lower:
            all_tags.append(generic)

    accepted: list[str] = []
    current_len = 0
    for tag in all_tags:
        added_len = len(tag) + (1 if accepted else 0)
        if current_len + added_len <= MAX_TAGS_LENGTH:
            accepted.append(tag)
            current_len += added_len
        else:
            break
    return ", ".join(accepted)


async def generate_post_description(readme_text: str, web_context: str = "") -> str:
    """Generate a ~200-word social media post description.

    Args:
        readme_text: The repository README text.
        web_context: Optional extra web context.

    Returns:
        The plain-text description.
    """
    reference = _build_reference(readme_text, web_context)
    prompt = (
        "You are an expert social media copywriter. Write an explanatory and engaging description for the following GitHub repository.\n"
        "The description must be written in English, and must be fluent and conversational.\n"
        "Follow these guidelines:\n"
        "- The description should be about 200 words.\n"
        "- Clearly explain what the repo is, what it does, and what task/problem it helps developers solve.\n"
        "- Describe the main features and in which practical scenarios this tool is useful.\n"
        "- Avoid unnecessary installation, configuration, or shell command details.\n"
        "- Do NOT use Markdown-style formatting such as asterisks (e.g. **bold**, *italic*) or underscores. Write only in plain, unformatted text.\n"
        "Return ONLY the description, nothing else.\n\n"
        f"Text to describe:\n{reference}"
    )
    description = await safe_chat_completion(prompt, temperature=0.5)
    return description.replace("**", "").replace("*", "")


async def generate_title(readme_text: str, web_context: str = "") -> str:
    """Generate a short, catchy title for the reel.

    Args:
        readme_text: The repository README text.
        web_context: Optional extra web context.

    Returns:
        The trimmed title.
    """
    reference = _build_reference(readme_text, web_context)
    prompt = (
        "Generate a catchy and explanatory title of about a single sentence for the following GitHub repository.\n"
        "The title must be in English, at most 90 characters for safety, and summarize the main value of the project.\n"
        "Return ONLY the title in plain text, without quotes and without any formatting.\n\n"
        f"Text:\n{reference}"
    )
    title = await safe_chat_completion(prompt, temperature=0.7)
    return limit_title(title.strip('"').strip("'"))


async def generate_tags(readme_text: str, web_context: str = "") -> str:
    """Generate a list of relevant tags for the reel.

    Args:
        readme_text: The repository README text.
        web_context: Optional extra web context.

    Returns:
        A comma-separated, normalized tag string.
    """
    reference = _build_reference(readme_text, web_context)
    prompt = (
        "Generate a list of tags/keywords related to the content of the following GitHub repository, without the hash symbol (#). Put the following tags first: 'github' 'foryou' 'ai'.\n"
        "The tags must be separated by commas. Make sure to generate the remaining tags needed to reach the 450-character limit (at least 10 words), including general terms about AI and GitHub, and consider that the limit must absolutely not be exceeded; double-check to verify you do not exceed that number.\n"
        "MANDATORY TAG RULES:\n"
        "- Each tag must consist EXCLUSIVELY of plain text (letters and/or digits), without hyphens (-), underscores (_), slashes (/), backslashes (\\), periods (.) or any other special character.\n"
        "- If a concept is made of multiple words (e.g. 'machine learning'), write it without spaces as a single word (e.g. 'machinelearning') or choose a single representative word.\n"
        "- NEVER use hyphens, slashes or special characters in tags, or the response will be invalidated.\n"
        "Return ONLY the comma-separated list of tags, nothing else.\n\n"
        f"Text:\n{reference}"
    )
    tags_raw = await safe_chat_completion(prompt, temperature=0.5)
    return format_and_limit_tags(tags_raw)


async def validate_and_fix_json(desc_data: dict, repo_url: str) -> dict:
    """Ask the LLM to verify and correct the generated JSON metadata.

    Args:
        desc_data: The generated metadata dictionary.
        repo_url: The source repository URL.

    Returns:
        The corrected metadata dictionary (original fields preserved on failure).
    """
    json_str = json.dumps(desc_data, ensure_ascii=False, indent=2)
    prompt = (
        "You are an expert social media content reviewer. You are given a JSON object with the metadata "
        "of a video reel related to the following GitHub repository:\n"
        f"Repository URL: {repo_url}\n\n"
        "The JSON object is the following:\n"
        f"{json_str}\n\n"
        "Verify and correct the following aspects for each field:\n"
        "1. 'titolo': must be in English, sensible, relevant to the repository, max 100 characters, plain text without Markdown formatting.\n"
        "2. 'descrizione_post': must be in English, fluent, about 200 words, relevant to the repository, plain text without Markdown formatting (no asterisks, no bullet points, no dashes as lists).\n"
        "3. 'tag': must be a comma-separated string of tags. CRITICAL RULE: each single tag must contain EXCLUSIVELY letters and/or digits, without hyphens (-), underscores (_), slashes (/), periods (.) or any other special character. If you find tags with special characters, remove them or join the words without separators. The tags must be relevant to the repository.\n"
        "4. 'testo_tts': must be in English, smooth for reading aloud, between 100 and 250 words, relevant to the repository, without shell commands or code fragments.\n\n"
        "If one or more fields contain errors, correct them. If they are all correct, return them unchanged.\n"
        "IMPORTANT: return EXCLUSIVELY the corrected JSON object, without introductory text, without comments, without markdown blocks (no ```json). Only the raw JSON."
    )
    try:
        raw = await safe_chat_completion(prompt, temperature=0.3)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw.strip())
        fixed_data = json.loads(raw)
        for key in desc_data:
            if key not in fixed_data:
                logger.warning("Validation: field '%s' missing, keeping original.", key)
                fixed_data[key] = desc_data[key]
        logger.info("JSON validated and corrected by LLM.")
        return fixed_data
    except Exception as exc:  # noqa: BLE001 - keep original data on failure
        logger.warning("JSON validation failed (%s); using original data.", exc)
        return desc_data
