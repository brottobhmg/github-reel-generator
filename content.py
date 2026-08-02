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
        "Sei un esperto copywriter per i social media. Scrivi una descrizione esplicativa e accattivante per la seguente repository GitHub.\n"
        "La descrizione deve essere scritta in lingua inglese, deve essere fluida e discorsiva.\n"
        "Concentrati sulle seguenti linee guida:\n"
        "- La descrizione deve essere di circa 200 parole.\n"
        "- Spiega in modo chiaro cos'è la repo, cosa fa e che compito/problema permette di risolvere agli sviluppatori.\n"
        "- Descrivi le caratteristiche principali e in quali scenari pratici è utile utilizzare questo strumento.\n"
        "- Evita dettagli superflui di installazione, configurazione o comandi shell.\n"
        "- NON utilizzare formattazioni in stile Markdown come asterischi (es. **grassetto**, *corsivo*) o trattini bassi. Scrivi solo in testo semplice non formattato.\n"
        "Restituisci SOLO la descrizione, nient'altro.\n\n"
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
        "Genera un titolo accattivante ed esplicativo di circa una singola frase per la seguente repository GitHub.\n"
        "Il titolo deve essere in lingua inglese, di massimo 90 caratteri per sicurezza, e riassumere il valore principale del progetto.\n"
        "Restituisci SOLO il titolo in testo semplice, senza virgolette e senza alcuna formattazione.\n\n"
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
        "Genera una lista di tag/parole chiave relative al contenuto della seguente repository GitHub, senza il simbolo cancelletto (#). Poni come primi tag i seguenti: 'github' 'foryou' 'ai'.\n"
        "I tag devono essere separati da virgole. Assicurati di generare i restanti tag necessari per arrivare al limite di 450 caratteri (minimo 10 parole), inserendo termini anche generali su IA e Github, e considera che il limite è da assolutamente non superare, fai un doppio controllo per verificare di non superare quel numero.\n"
        "REGOLE OBBLIGATORIE PER I TAG:\n"
        "- Ogni tag deve essere composto ESCLUSIVAMENTE da testo semplice (lettere e/o cifre), senza trattini (-), trattini bassi (_), barre (/), barre inverse (\\), punti (.) o qualsiasi altro carattere speciale.\n"
        "- Se un concetto è composto da più parole (es. 'machine learning'), scrivilo senza spazi come una sola parola (es. 'machinelearning') oppure scegli una singola parola rappresentativa.\n"
        "- NON usare mai trattini, slash o caratteri speciali nei tag, pena l'invalidazione della risposta.\n"
        "Restituisci SOLO la lista di tag separati da virgole, nient'altro.\n\n"
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
        "Sei un esperto revisore di contenuti per social media. Ti viene fornito un oggetto JSON con i metadati "
        "di un video reel relativo alla repository GitHub seguente:\n"
        f"Repository URL: {repo_url}\n\n"
        "L'oggetto JSON è il seguente:\n"
        f"{json_str}\n\n"
        "Verifica e correggi i seguenti aspetti per ciascun campo:\n"
        "1. 'titolo': deve essere in inglese, sensato, pertinente alla repository, max 100 caratteri, testo semplice senza formattazione Markdown.\n"
        "2. 'descrizione_post': deve essere in inglese, fluida, circa 200 parole, pertinente alla repository, testo semplice senza formattazione Markdown (niente asterischi, niente bullet point, niente trattini come liste).\n"
        "3. 'tag': deve essere una stringa di tag separati da virgole. REGOLA CRITICA: ogni singolo tag deve contenere ESCLUSIVAMENTE lettere e/o cifre, senza trattini (-), trattini bassi (_), barre (/), punti (.) o qualsiasi altro carattere speciale. Se trovi tag con caratteri speciali, rimuovili o unisci le parole senza separatori. I tag devono essere pertinenti alla repository.\n"
        "4. 'testo_tts': deve essere in inglese, scorrevole per la lettura ad alta voce, tra 100 e 250 parole, pertinente alla repository, senza comandi shell o frammenti di codice.\n\n"
        "Se uno o più campi contengono errori, correggili. Se sono tutti corretti, restituiscili invariati.\n"
        "IMPORTANTE: restituisci ESCLUSIVAMENTE l'oggetto JSON corretto, senza testo introduttivo, senza commenti, senza blocchi markdown (no ```json). Solo il JSON grezzo."
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
