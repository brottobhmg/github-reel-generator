import urllib
import asyncio
import os
import json
import urllib.request
import numpy as np
import scipy.io.wavfile as wavfile
from openai import OpenAI, AsyncOpenAI
from playwright.async_api import async_playwright
from kokoro import KPipeline
from moviepy.video.VideoClip import TextClip
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.audio.io.AudioFileClip import AudioFileClip
from ddgs import DDGS
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes


NVIDIA_NIM_API_KEY = os.getenv("NVIDIA_NIM_API_KEY","NVIDIA_NIM_API_KEY_REMOVED")
GROQ_API_KEY = os.getenv("GROQ_API_KEY","GROQ_API_KEY_REMOVED")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "OPENROUTER_API_KEY_REMOVED")

MODEL = "nvidia/nemotron-3-super-120b-a12b"
MODEL_FALLBACK = "nvidia/nemotron-3-super-120b-a12b:free"

groq_client = AsyncOpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
gemini_client = AsyncOpenAI(api_key=NVIDIA_NIM_API_KEY, base_url="https://integrate.api.nvidia.com/v1", timeout=45.0)
openrouter_client = AsyncOpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")

LOAD_DELAY = 3.0

TOKEN = "TELEGRAM_BOT_TOKEN_REMOVED"
GITHUB_REGEX = r"(https?://)?(www\.)?github\.com/[a-zA-Z0-9-]+/[a-zA-Z0-9_.-]+"


async def safe_chat_completion(prompt: str, temperature: float = 0.7) -> str:
    """Invia una richiesta di chat completion provando prima nvidia/nemotron-3-super-120b-a12b su Nvidia NIM,
    e come fallback lo stesso modello su OpenRouter (:free)."""
    # 1. Tentativo principale: Nvidia NIM (nvidia/nemotron-3-super-120b-a12b)
    try:
        print(f"🤖 [Nvidia NIM] Invio richiesta con modello {MODEL}...")
        response = await gemini_client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            timeout=15.0
        )
        print(f"✅ Nvidia NIM ({MODEL}) ha risposto con successo.")
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Nvidia NIM ({MODEL}) fallito o in timeout: {e}. Provo il fallback su OpenRouter...")

    # 2. Tentativo di fallback: OpenRouter (nvidia/nemotron-3-super-120b-a12b:free)
    try:
        print(f"🤖 [OpenRouter] Invio richiesta con modello {MODEL_FALLBACK}...")
        response = await openrouter_client.chat.completions.create(
            model=MODEL_FALLBACK,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            timeout=20.0
        )
        print(f"✅ OpenRouter ({MODEL_FALLBACK}) ha risposto con successo.")
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Tutti i tentativi (Nvidia NIM e OpenRouter) sono falliti: {e}")
        raise e


async def elabora_link_github(url: str):
    # Simula il lavoro (es. scraping, download, analisi)
    await asyncio.sleep(2) 
    return f"Elaborazione completata con successo per: {url}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ciao! Inviami un link GitHub e inizierò a lavorarci.")

async def gestisci_messaggio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    testo = update.message.text

    
    # Cerca se nel testo c'è un link GitHub
    match = re.search(GITHUB_REGEX, testo)
    
    if match:
        link_estratto = match.group(0)
        await update.message.reply_text(f"Link GitHub rilevato! Inizio l'elaborazione di: {link_estratto}")
        print(f"Link estratto: {link_estratto}")
        # Esegui la tua logica
    
        repos_file = "./repos"
        output_dir = "./output"
        if os.path.exists(repos_file):
            all_repos = []
            with open(repos_file, "r", encoding="utf-8") as f:
                all_repos = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            for url in all_repos:
                if (link_estratto==url):
                    await update.message.reply_text("Link già processato nel passato! ❌")
                    return

        try:
            risultato_dict = await run_pipeline(link_estratto)
            try:
                with open(repos_file, "a", encoding="utf-8") as f:
                    f.write(f"{link_estratto}\n")
            except Exception as fe:
                print(f"⚠️ Impossibile salvare il link nel file repos: {fe}")
            
            # 1. Invia messaggio testuale di successo
            await update.message.reply_text(risultato_dict["message"])
            
            # 2. Invia la descrizione come testo (utile per copiare e incollare facilmente)
            desc_path = risultato_dict["description_path"]
            if os.path.exists(desc_path):
                try:
                    with open(desc_path, "r", encoding="utf-8") as desc_file:
                        desc_data = json.load(desc_file)
                    
                    tags_str = desc_data.get('tag', '')
                    hashtags_list = []
                    if tags_str:
                        for t in tags_str.split(','):
                            cleaned_tag = t.strip().replace(" ", "")
                            if cleaned_tag:
                                hashtags_list.append(f"#{cleaned_tag}")
                    hashtags_str = " ".join(hashtags_list)

                    testo_messaggio = (
                        f"✨ TITOLO:\n{desc_data.get('titolo', '')}\n\n"
                        f"📝 DESCRIZIONE POST:\n{desc_data.get('descrizione_post', '')}\n\n"
                        f"🏷️ TAG:\n{tags_str}\n\n"
                        f"🏷️ HASHTAGS:\n{hashtags_str}\n\n"
                        f"🎙️ TESTO TTS:\n{desc_data.get('testo_tts', '')}"
                    )
                    await update.message.reply_text(testo_messaggio)
                except Exception as de:
                    print(f"⚠️ Errore nell'invio della descrizione come testo: {de}")
            
            # 3. Invia il file descrizione (.json) come documento
            if os.path.exists(desc_path):
                try:
                    with open(desc_path, "rb") as desc_file:
                        await update.message.reply_document(
                            document=desc_file,
                            filename="descrizione.json",
                            caption="📄 File di descrizione e metadati JSON"
                        )
                except Exception as de:
                    print(f"⚠️ Errore nell'invio del file descrizione: {de}")
            
            # 4. Invia il file video direttamente
            video_path = risultato_dict["video_path"]
            if os.path.exists(video_path):
                await update.message.reply_text("📤 Invio del video reel in corso... ⏳")
                try:
                    with open(video_path, "rb") as video_file:
                        await update.message.reply_document(
                            document=video_file, 
                            filename=f"{risultato_dict['repo_name']}_reel.mp4",
                            caption=f"🎥 Reel per {risultato_dict['repo_name']}"
                        )
                except Exception as ve:
                    await update.message.reply_text(f"❌ Errore nell'invio del file video: {ve}")
                    
        except Exception as e:
            await update.message.reply_text(f"❌ Errore durante la pipeline per {link_estratto}: {e}")
    else:
        await update.message.reply_text("Non ho trovato nessun link GitHub valido in questo messaggio.")


def search_repo_info(repo_url: str) -> str:
    """Cerca su DuckDuckGo informazioni utili sulla repository se il README è scarno o per arricchire il contesto."""
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    query = f"{repo_name} github repository what is it what does it do"
    print(f"🔍 Ricerca online su DuckDuckGo per: '{query}'...")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if results:
                summary = []
                for r in results:
                    summary.append(f"Title: {r.get('title')}\nSnippet: {r.get('body')}")
                print(f"✅ Ricerca completata con successo. Trovati {len(results)} risultati.")
                return "\n\n".join(summary)
    except Exception as e:
        print(f"⚠️ Errore durante la ricerca online con DDG per {repo_name}: {e}")
    return ""


def fetch_readme(repo_url: str) -> str:
    """Scarica il README dalla repository GitHub tramite l'API raw di GitHub."""
    # Normalizza l'URL: https://github.com/owner/repo -> raw.githubusercontent.com
    repo_url = repo_url.rstrip("/")
    if "raw.githubusercontent.com" in repo_url:
        raw_url = repo_url
    else:
        # Estrae owner/repo dal URL github.com
        parts = repo_url.replace("https://github.com/", "").split("/")
        owner, repo = parts[0], parts[1]
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/README.md"
    #print(raw_url)
    try:
        req = urllib.request.Request(raw_url, headers={"User-Agent": "devtok-pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode("utf-8", errors="ignore")
        # Tronca a 3000 caratteri per non superare i limiti del prompt
        return content[:3000]
    except Exception as e:
        print(f"⚠️ Impossibile scaricare il README: {e}")
        return f"GitHub repository: {repo_url}"


async def generate_script(readme_text, web_context=""):
    """1. Genera lo script del Reel usando Gemini (senza comandi espliciti di build)"""
    reference_content = f"README:\n{readme_text}"
    if web_context:
        reference_content += f"\n\nAdditional Web Context:\n{web_context}"

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
        f"Text to summarize:\n{reference_content}"
    )
    
    script_text = await safe_chat_completion(prompt, temperature=0.7)
    script_text = script_text.replace("'", "'").replace("\u201c", '"').replace("\u201d", '"')
    
    # Aggiungi la call to action finale
    cta = "Link in description. Follow for more open-source repo."
    if cta.lower() not in script_text.lower():
        script_text = f"{script_text.strip()} {cta}"
        
    return script_text

def limit_title(title_input: str) -> str:
    """Limita il titolo a massimo 100 caratteri."""
    title = title_input.strip().replace("\n", " ")
    if len(title) > 100:
        title = title[:100]
        if " " in title:
            title = title.rsplit(" ", 1)[0]
        title = title.strip()
    return title


def format_and_limit_tags(tags_input: str) -> str:
    """Formatta e limita la lista di tag a massimo 100 caratteri esclusi i caratteri virgola."""
    raw_tags = []
    if "," in tags_input:
        parts = tags_input.split(",")
    else:
        parts = tags_input.split()
        
    for p in parts:
        cleaned = p.strip().replace("#", "")
        if cleaned:
            raw_tags.append(cleaned)
            
    generic_tags = ["github", "open source", "open", "privacy", "foryou"]
    raw_tags_lower = [t.lower() for t in raw_tags]
    for gt in generic_tags:
        if gt.lower() not in raw_tags_lower:
            raw_tags.append(gt)
            
    accepted_tags = []
    current_non_comma_len = 0
    for tag in raw_tags:
        added_len = len(tag) + (1 if accepted_tags else 0)
        if current_non_comma_len + added_len <= 100:
            accepted_tags.append(tag)
            current_non_comma_len += added_len
        else:
            break
            
    return ", ".join(accepted_tags)


async def generate_post_description(readme_text, web_context=""):
    """Genera una descrizione dettagliata del post di circa 300 parole."""
    reference_content = f"README:\n{readme_text}"
    if web_context:
        reference_content += f"\n\nAdditional Web Context:\n{web_context}"

    prompt = (
        "Sei un esperto copywriter per i social media. Scrivi una descrizione esplicativa e accattivante per la seguente repository GitHub.\n"
        "La descrizione deve essere scritta in lingua inglese, deve essere fluida e discorsiva.\n"
        "Concentrati sulle seguenti linee guida:\n"
        "- La descrizione deve essere di circa 200 parole. Massima lunghezza 2100 caratteri, inclusi spazi e punteggiatura.\n"
        "- Spiega in modo chiaro cos'è la repo, cosa fa e che compito/problema permette di risolvere agli sviluppatori.\n"
        "- Descrivi le caratteristiche principali e in quali scenari pratici è utile utilizzare questo strumento.\n"
        "- Evita dettagli superflui di installazione, configurazione o comandi shell.\n"
        "- NON utilizzare formattazioni in stile Markdown come asterischi (es. **grassetto**, *corsivo*) o trattini bassi. Scrivi solo in testo semplice non formattato.\n"
        "Restituisci SOLO la descrizione, nient'altro.\n\n"
        f"Text to describe:\n{reference_content}"
    )
    description = await safe_chat_completion(prompt, temperature=0.5)
    description = description.replace("**", "").replace("*", "")
    return description


async def generate_title(readme_text, web_context=""):
    """Genera un titolo di circa una frase con massimo 100 caratteri."""
    reference_content = f"README:\n{readme_text}"
    if web_context:
        reference_content += f"\n\nAdditional Web Context:\n{web_context}"

    prompt = (
        "Genera un titolo accattivante ed esplicativo di circa una singola frase per la seguente repository GitHub.\n"
        "Il titolo deve essere in lingua inglese, di massimo 90 caratteri per sicurezza, e riassumere il valore principale del progetto.\n"
        "Restituisci SOLO il titolo in testo semplice, senza virgolette e senza alcuna formattazione.\n\n"
        f"Text:\n{reference_content}"
    )
    title = await safe_chat_completion(prompt, temperature=0.7)
    title = title.strip('"').strip("'")
    return limit_title(title)


async def generate_tags(readme_text, web_context=""):
    """Genera una lista di tag relativi al contenuto di massimo 100 caratteri esclusi le virgole."""
    reference_content = f"README:\n{readme_text}"
    if web_context:
        reference_content += f"\n\nAdditional Web Context:\n{web_context}"

    prompt = (
        "Genera una lista ricca e abbondante di tag/parole chiave relative al contenuto della seguente repository GitHub, senza il simbolo cancelletto (#).\n"
        "I tag devono essere separati da virgole. Assicurati di generare molti tag per poter sfruttare appieno il limite di 100 caratteri.\n"
        "Restituisci SOLO la lista di tag separati da virgole, nient'altro.\n\n"
        f"Text:\n{reference_content}"
    )
    tags_raw = await safe_chat_completion(prompt, temperature=0.5)
    return format_and_limit_tags(tags_raw)

def generate_tts_local(text, output_audio_path):
    """2. Genera la traccia vocale in locale su CPU usando Kokoro (Qualità eccellente)"""
    print("🎙️ Caricamento modello Kokoro ed esecuzione sintesi...")
    # 'i' imposta il frasario e la fonemizzazione per la lingua italiana
    pipeline = KPipeline(lang_code='a', repo_id='hexgrad/Kokoro-82M') 
    
    # Genera i segmenti audio usando la voce italiana 'it_vittoria'
    generator = pipeline(text, voice='af_heart', speed=1.0)
    
    all_audio_chunks = []
    for _, _, audio in generator:
        if audio is not None:
            all_audio_chunks.append(audio)
            
    if all_audio_chunks:
        # Unisce tutti i segmenti in un unico array di campionamento numerico
        final_audio = np.concatenate(all_audio_chunks)
        # Salva in formato WAV (Kokoro lavora nativamente a 24000Hz)
        wavfile.write(output_audio_path, 24000, final_audio)
    else:
        raise Exception("Errore durante la generazione dell'audio locale con Kokoro.")

async def record_github_scroll(url, duration, output_video_path):
    """3. Usa Playwright Headless per catturare lo scrolling della pagina"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Emuliamo un dispositivo mobile con aspect ratio 2:3 per un layout a colonna singola pulito
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            #viewport={'width': 1080, 'height': 1920}, # Aspect Ratio 2:3 (600x900)
            #viewport={'width': 1000, 'height': 1350}, # Aspect Ratio 2:3 (600x900)
            viewport={'width': 1000, 'height': 1350}, # Aspect Ratio 2:3 (600x900)
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
            record_video_dir="./videos/"
        )
        page = await context.new_page()
        
        # Naviga e attende che la pagina sia caricata e stabile
        # Codice commentato per caricare file locale riformattato:
        # if os.path.exists(url):
        #     target_url = f"file://{os.path.abspath(url)}"
        # else:
        #     target_url = url
        # await page.goto(target_url, wait_until="networkidle")
        
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(int(LOAD_DELAY * 1000))
        
        # Aumenta questo valore per fare più zoom (es. '1.5', '2.0')
        await page.evaluate("document.body.style.zoom = '1.0'")

        # Calcola la velocità di scroll in modo dinamico per coprire l'intera pagina durante l'audio
        total_scroll = await page.evaluate("document.body.scrollHeight - window.innerHeight")
        
        MAX_SCROLL_SPEED = 100.0  # px/s
        # Se total_scroll è negativo o zero (pagina non scorribile), la velocità sarà 0
        if total_scroll > 0 and duration > 0:
            estimated_speed = total_scroll / duration
            scroll_speed = min(MAX_SCROLL_SPEED, estimated_speed)
        else:
            scroll_speed = 0.0

        print(f"📊 Scroll Info: Altezza utile scroll = {total_scroll}px, Durata = {duration:.2f}s -> Velocità calcolata = {scroll_speed:.2f} px/s")

        # Esegui lo scroll continuo a 60 FPS per tutta la durata audio, poi si ferma
        await page.evaluate(
            """async (args) => {
                const { duration, speed, maxScroll } = args;
                return new Promise((resolve) => {
                    const start = performance.now();
                    function step(timestamp) {
                        const elapsed = (timestamp - start) / 1000;
                        const pos = Math.min(elapsed * speed, maxScroll);
                        window.scrollTo(0, pos);
                        if (elapsed < duration && pos < maxScroll) {
                            requestAnimationFrame(step);
                        } else {
                            resolve();
                        }
                    }
                    requestAnimationFrame(step);
                });
            }""",
            {"duration": duration, "speed": scroll_speed, "maxScroll": maxScroll_val if (maxScroll_val := total_scroll) > 0 else 0}
        )
            
        video_path = await page.video.path()
        await browser.close()
        
        # Remux to fix missing WebM duration metadata (required by MoviePy)
        import subprocess
        subprocess.run(["ffmpeg", "-y", "-i", video_path, "-c", "copy", output_video_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def get_word_timestamps_from_groq(audio_path):
    """4. Invia l'audio a Groq chiedendo i timestamp precisi per singola parola"""
    with open(audio_path, "rb") as file:
        transcription = await groq_client.audio.transcriptions.create(
            file=(os.path.basename(audio_path), file.read()),
            model="whisper-large-v3",
            response_format="verbose_json",
            language="en",
            timestamp_granularities=["word"] # <--- Corretto qui
        )
        
    words_data = []
    
    # Trasformiamo l'oggetto dell'SDK in un dizionario Python per un parsing sicuro
    transcription_dict = transcription if isinstance(transcription, dict) else transcription.model_dump()
    
    if "words" in transcription_dict and transcription_dict["words"]:
        for word in transcription_dict["words"]:
            words_data.append({
                "text": word['word'],
                "start": word['start'],
                "end": word['end']
            })
            
    return words_data

def assemble_final_video(video_path, audio_path, words_data, output_path):
    """5. Unisce i componenti ed esegue il compositing dei sottotitoli"""
    video_clip = VideoFileClip(video_path)
    audio_clip = AudioFileClip(audio_path)
    
    # Risoluzione delle sovrapposizioni temporali tra parole consecutive (anti-overlap)
    sorted_words = sorted(words_data, key=lambda x: x["start"])
    for i in range(len(sorted_words) - 1):
        curr_word = sorted_words[i]
        next_word = sorted_words[i+1]
        if curr_word["end"] > next_word["start"]:
            curr_word["end"] = next_word["start"]
            if curr_word["end"] <= curr_word["start"]:
                curr_word["end"] = curr_word["start"] + 0.05
                next_word["start"] = curr_word["end"]
    
    # Taglia il video per eliminare la schermata iniziale di caricamento
    video_clip = video_clip.subclip(LOAD_DELAY, LOAD_DELAY + audio_clip.duration)
    
    # Associazione traccia audio al video
    video_clip = video_clip.set_audio(audio_clip)
    
    # Raggruppa le parole in chunk da 2-3 per ottenere uno stile karaoke più leggibile
    WORDS_PER_CHUNK = 3
    valid_words = [w for w in sorted_words if w["start"] < audio_clip.duration]
    chunks = [valid_words[i:i+WORDS_PER_CHUNK] for i in range(0, len(valid_words), WORDS_PER_CHUNK)]
    
    txt_clips = []
    for chunk in chunks:
        if not chunk:
            continue
        
        chunk_text = " ".join(w["text"].upper() for w in chunk)
        chunk_start = chunk[0]["start"]
        chunk_end = min(chunk[-1]["end"], audio_clip.duration)
        
        if chunk_end <= chunk_start:
            chunk_end = chunk_start + 0.1
        
        # Simple subtitle (white) per chunk
        txt_clip = TextClip(
            txt=chunk_text,
            fontsize=38,
            color='white',
            stroke_color='black',
            stroke_width=2,
            font="Lato-Black",
            size=(int(video_clip.w * 0.85), None),
            method='caption'
        )
        txt_clip = txt_clip.set_start(chunk_start).set_end(chunk_end)
        target_y = int(video_clip.h * 0.83)
        txt_clip = txt_clip.set_position(('center', target_y))
        txt_clips.append(txt_clip)
        
        
    # Composizione finale e rendering effettivo
    final_video = CompositeVideoClip([video_clip] + txt_clips)
    final_video.write_videofile(output_path, fps=60, codec="libx264", audio_codec="aac")

async def run_pipeline(repo_url: str):
    # Derive repository name for folder (e.g., litellm-free-models-proxy)
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    output_dir = "./output"
    # Create a subfolder per repository
    repo_dir = os.path.join(output_dir, repo_name)
    os.makedirs(repo_dir, exist_ok=True)

    # Temporary audio/video files (can stay in project root)
    tmp_audio = "./voice.wav"
    tmp_video = "./scroll.webm"
    # Final video will be placed inside the repository‑specific folder
    final_mp4 = os.path.join(repo_dir, f"{repo_name}_reel.mp4")
    # Path for descrizione.json
    description_path = os.path.join(repo_dir, "descrizione.json")
    
    print("⏳ [1/5] Generazione dei testi con Gemini...")
    readme_text = fetch_readme(repo_url)
    web_context = search_repo_info(repo_url)
    
    script = await generate_script(readme_text, web_context)
    print(f"📝 Testo TTS generato: {script}")
    
    post_desc = await generate_post_description(readme_text, web_context)
    post_desc = f"{post_desc.strip()}\n\n{repo_url}"
    print(f"📝 Descrizione post generata: {post_desc[:100]}...")
    
    title = await generate_title(readme_text, web_context)
    print(f"📝 Titolo generato: {title}")
    
    tags = await generate_tags(readme_text, web_context)
    print(f"📝 Tag generati: {tags}")
    
    desc_data = {
        "testo_tts": script,
        "descrizione_post": post_desc,
        "titolo": title,
        "tag": tags
    }
    with open(description_path, "w", encoding="utf-8") as desc_file:
        json.dump(desc_data, desc_file, ensure_ascii=False, indent=4)
    print(f"💾 Salvato descrizione.json in {description_path}")
    
    print("⏳ [2/5] Sintesi vocale con Kokoro Locale...")
    generate_tts_local(script, tmp_audio)
    audio_duration = AudioFileClip(tmp_audio).duration
    
    print("⏳ [2b/5] Generazione dell'anteprima mobile per la repository...")
    #local_preview_path = "./mobile_preview.html"
    #repo_data = fetch_repo_data(repo_url)
    #generate_mobile_html(repo_data, local_preview_path)
    
    print(f"⏳ [3/5] Registrazione dello scroll con Playwright (Durata: {audio_duration:.2f}s)...")
    await record_github_scroll(repo_url, audio_duration, tmp_video)
    
    print("⏳ [4/5] Estrazione dei timestamp a livello di parola con Groq Whisper...")
    words_data = await get_word_timestamps_from_groq(tmp_audio)
    
    print("⏳ [5/5] Renderizzazione finale del file video con MoviePy...")
    assemble_final_video(tmp_video, tmp_audio, words_data, final_mp4)
    
    #Rimozione file temporanei audio e video
    if os.path.exists(tmp_audio):
        os.remove(tmp_audio)
    if os.path.exists(tmp_video):
        os.remove(tmp_video)
    msg = f"🚀 Pipeline completata con successo! Video salvato in: {final_mp4}"
    print(msg)
    return {
        "message": msg,
        "video_path": final_mp4,
        "description_path": description_path,
        "repo_name": repo_name
    }




def hear_and_elaborate():
    # Inizializza l'applicazione
    application = Application.builder().token(TOKEN).build()

    # Gestori dei comandi e dei messaggi di testo
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gestisci_messaggio))

    # Avvia il bot in modalità Polling
    print("Bot in ascolto (Polling)... Premere Ctrl+C per interrompere.")
    application.run_polling()


if __name__ == "__main__":
    hear_and_elaborate()