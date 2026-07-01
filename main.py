import time
import datetime
import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
import requests

# --- CONFIGURAZIONE ---
API_ENDPOINT = "https://PRIVATE_VPS_ENDPOINT_REMOVED/api/get_next_video"
DEVICE_ID = "a77c9581"  # Lascia vuoto se hai un solo telefono connesso
RELATIVE_PATH = "Pictures/TTUploader"
POSSIBLE_APPS = ["com.zhiliaoapp.musically"]



def adb(command):
    """Invia comandi nativi ad ADB."""
    prefix = f"adb -s {DEVICE_ID} " if DEVICE_ID else "adb "
    proc = subprocess.Popen(
        prefix + command, stdout=subprocess.PIPE, shell=True
    )
    out, err = proc.communicate()
    return out.decode("utf-8")


def get_screen_size():
    """Ritorna (width, height) dello schermo usando i dati nativi di adb."""
    size_str = adb("shell wm size")
    match = re.search(r"(\d+)x(\d+)", size_str)
    if match:
        return int(match.group(1)), int(match.group(2))
    return (1080, 2400)  # Fallback standard


def touch_relative(x_prop, y_prop):
    """Simula un tap usando coordinate relative (es: 0.5, 0.99)."""
    w, h = get_screen_size()
    x = int(x_prop * w)/100
    y = int(y_prop * h)/100
    print("Tap in: ", x, y, " - ", x_prop, y_prop)
    adb(f"shell input tap {x} {y}")



def wake_and_unlock():
    """Sveglia lo schermo in modo forzato e sblocca il dispositivo."""
    # 1. Controllo dello schermo tramite 'mScreenOn' (più universale su vecchi e nuovi Android)
    power_state = adb("shell dumpsys power")
    
    # Se mScreenOn è false o viene rilevato lo stato di Asleep/OFF
    is_asleep = any(x in power_state for x in ["mScreenOn=false", "mWakefulness=Asleep", "Display Power: state=OFF"])
    
    if is_asleep:
        print("Schermo spento. Invio trigger di accensione hardware...")
        # Il KEYCODE_POWER (26) è l'equivalente fisico del tasto laterale. È il più potente.
        adb("shell input keyevent 26")
        time.sleep(0.8)  # Diamo un po' più di tempo al display per svegliarsi
    else:
        print("Lo schermo sembra già acceso.")

    # 2. Doppio controllo di sicurezza
    # Se per qualche motivo il toggle ha fallito o era un falso positivo, 
    # mandiamo una simulazione di tap sullo schermo spento (molti telefoni si svegliano col doppio tap o tap singolo)
    # o un evento di movimento per forzare il risveglio della lockscreen.
    adb("shell input keyevent 82") # KEYCODE_MENU: su molti Android sblocca/accende direttamente la lockscreen
    time.sleep(0.3)

    # 3. Esegui lo swipe verso l'alto per rimuovere la schermata di blocco vuota
    print("Eseguo lo swipe di sblocco...")
    w, h = get_screen_size()
    x_start = x_end = int(0.5 * w)
    y_start = int(0.8 * h)
    y_end = int(0.2 * h)
    
    # Aumentiamo leggermente il tempo dello swipe (500ms) per renderlo più "umano" e far sì che Android lo prenda
    adb(f"shell input swipe {x_start} {y_start} {x_end} {y_end} 700")
    time.sleep(0.5)
    
    # 4. Ritorna alla Home
    adb("shell input keyevent 3")  # KEYCODE_HOME
    print("Dispositivo sbloccato.")

def type_text(text):
    """Digita testo (gestendo spazi e caratteri speciali tramite shell)."""
    # Sostituisce spazi con %s, che è il modo in cui ADB interpreta gli spazi in input text
    # I caratteri speciali (come @, #, ecc.) vengono gestiti abbastanza bene da ADB nativamente,
    # ma %s è cruciale per gli spazi.
    escaped_text = text.replace(" ", "%s")
    adb(f'shell input text {escaped_text}')

def open_telegram_monkey():
    """Apre Telegram simulando un evento di lancio tramite monkey (più robusto)."""
    print("Apertura di Telegram via Monkey...")
    adb("shell monkey -p org.telegram.messenger -c android.intent.category.LAUNCHER 1")

def pull_file_from_phone(phone_filename, local_destination="./"):
    """Sposta un file dalla cartella Download di Telegram al PC."""

    #Lista degli elementi dentro la cartella
    print(adb("shell ls -al /storage/emulated/0/Download/Telegram/"))


    phone_path = f"/storage/emulated/0/Download/Telegram/{phone_filename}"
    
    # Nota: adb pull è un comando nativo di ADB, non va sotto 'shell'
    # Usiamo la tua funzione nativa passandogli il comando pull direttamente
    print(f"Prelevo {phone_filename} dal telefono...")
    adb(f"pull {phone_path} {local_destination}")

def upload_tiktok(video_path, caption):

    APP_NAME = "com.zhiliaoapp.musically"

    #print("🚀 Avvio di TikTok...")
    adb(f"shell am start -n {APP_NAME}/com.ss.android.ugc.aweme.splash.SplashActivity")
    time.sleep(10)

    
    touch_relative(95,95)
    time.sleep(2)
    touch_relative(50,95)
    time.sleep(2)
    touch_relative(5,90)
    time.sleep(2)
    touch_relative(5,20)
    time.sleep(2)
    touch_relative(80,95)
    time.sleep(2)
    touch_relative(80,90)

    time.sleep(2)
    #titolo click: 453 600
    touch_relative(42,25)
    type_text("test titolo")

    time.sleep(2)
    #descrzione click: 400 875
    touch_relative(37,36)
    type_text("test descrizione")

    #pubblica tasto: 800 2300
    time.sleep(2)
    #touch_relative(74,96)
    

    print("✅ Operazione conclusa!")
    return True



def main():

    adb("start-server")
    
    #wake_and_unlock()
    

    #upload_tiktok("descrizione")




if __name__ == "__main__":
    main()