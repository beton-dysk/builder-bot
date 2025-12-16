import streamlit as st
import openai
import os
import subprocess
import sys
import time
import signal
import threading
from queue import Queue, Empty

# --- KONFIGURACJA ---
st.set_page_config(page_title="Builder Lab", page_icon="🧪", layout="wide")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PREVIEW_URL = os.getenv("PREVIEW_URL", "http://localhost:5000")
if not OPENAI_API_KEY:
    st.error("❌ Brak klucza OPENAI_API_KEY.")
    st.stop()

client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Ścieżki i Porty
SANDBOX_DIR = "sandbox"
APP_FILE = os.path.join(SANDBOX_DIR, "app.py")

# Upewnij się, że katalog istnieje
os.makedirs(SANDBOX_DIR, exist_ok=True)

# --- STAN APLIKACJI (SESSION STATE) ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": """
        Jesteś ekspertem Python/Flask. Twoim celem jest tworzenie prototypów aplikacji webowych.
        ZASADY:
        1. Generuj ZAWSZE kompletny kod pliku `app.py` używając frameworka Flask.
        2. Aplikacja MUSI nasłuchiwać na porcie 5000 (app.run(host='0.0.0.0', port=5000)).
        3. Nie używaj 'debug=True' w trybie produkcyjnym/reloader, bo to blokuje subprocess.
        4. Odpowiadaj krótko. Kod umieszczaj w bloku ```python.
        5. Jeśli użytkownik prosi o zmianę, wygeneruj CAŁY poprawiony kod pliku app.py od nowa.
        """}
    ]
if "generated_code" not in st.session_state:
    st.session_state.generated_code = ""
if "server_process" not in st.session_state:
    st.session_state.server_process = None
if "logs" not in st.session_state:
    st.session_state.logs = []

# --- FUNKCJE ---

def run_app():
    """Uruchamia aplikację Flask w tle."""
    stop_app() # Najpierw ubij starą
    
    # Zapisz kod do pliku
    with open(APP_FILE, "w") as f:
        f.write(st.session_state.generated_code)
    
    st.session_state.logs = []
    
    # Uruchom proces
    # Używamy unbuffered python (-u) żeby logi spływały na bieżąco
    process = subprocess.Popen(
        [sys.executable, "-u", APP_FILE],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, # Łączymy błędy z logami
        text=True,
        cwd=SANDBOX_DIR
    )
    st.session_state.server_process = process
    
    # Wątek do czytania logów (uproszczony)
    def log_reader(proc):
        for line in iter(proc.stdout.readline, ''):
            st.session_state.logs.append(line)
            # Limit logów żeby nie zapchać pamięci
            if len(st.session_state.logs) > 100:
                st.session_state.logs.pop(0)
    
    t = threading.Thread(target=log_reader, args=(process,), daemon=True)
    t.start()

def stop_app():
    """Zatrzymuje działający proces."""
    if st.session_state.server_process:
        p = st.session_state.server_process
        p.terminate()
        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            p.kill()
        st.session_state.server_process = None

def generate_response(prompt):
    """Komunikacja z OpenAI."""
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    response = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        messages=st.session_state.messages
    )
    
    bot_reply = response.choices[0].message.content
    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
    
    # Wyciąganie kodu z Markdowna (prosty parser)
    code = ""
    if "```python" in bot_reply:
        code = bot_reply.split("```python")[1].split("```")[0]
    elif "```" in bot_reply: # Fallback
        code = bot_reply.split("```")[1].split("```")[0]
        
    if code:
        st.session_state.generated_code = code
        run_app() # Auto-run po wygenerowaniu
        
    return bot_reply

# --- INTERFEJS UI (Dwie Kolumny) ---

st.title("🧪 Builder Lab (Agentic Mode)")

col_left, col_right = st.columns([1, 1], gap="medium")

# --- LEWA KOLUMNA: CHAT ---
with col_left:
    st.subheader("💬 Rozmowa z Agentem")
    
    # Kontener na historię czatu
    chat_container = st.container(height=500)
    with chat_container:
        for msg in st.session_state.messages:
            if msg["role"] != "system":
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
    
    # Input
    if prompt := st.chat_input("Co budujemy? (np. 'Prosty kalkulator we Flask')"):
        with st.spinner("Agent myśli i koduje..."):
            generate_response(prompt)
            st.rerun()

# --- PRAWA KOLUMNA: PREVIEW / CODE / LOGS ---
with col_right:
    st.subheader("👁️ Podgląd & Debug")
    
    tab1, tab2, tab3 = st.tabs(["🌐 Preview", "💻 Kod Źródłowy", "terminal Logi"])
    
    # TAB 1: PREVIEW (IFRAME)
    with tab1:
        st.caption(f"Adres serwera: {PREVIEW_URL}")
        
        # Pasek kontrolny
        c1, c2, c3 = st.columns([1,1,2])
        if c1.button("🔄 Odśwież"):
            st.rerun()
        if c2.button("⏹️ Stop"):
            stop_app()
            st.rerun()
            
        status = "🟢 Działa" if st.session_state.server_process and st.session_state.server_process.poll() is None else "🔴 Zatrzymany"
        c3.markdown(f"**Status:** {status}")

        if status == "🟢 Działa":
            # Iframe wyświetlający aplikację
            # WAŻNE: Przeglądarka musi mieć dostęp do PREVIEW_URL
            st.components.v1.iframe(PREVIEW_URL, height=500, scrolling=True)
        else:
            st.info("Aplikacja nie jest uruchomiona.")

    # TAB 2: KOD
    with tab2:
        if st.session_state.generated_code:
            st.code(st.session_state.generated_code, language="python")
        else:
            st.info("Jeszcze nie wygenerowano kodu.")

    # TAB 3: LOGI
    with tab3:
        st.caption("Output z konsoli (stdout/stderr):")
        log_box = st.empty()
        # Wyświetlamy ostatnie logi
        log_text = "".join(st.session_state.logs)
        log_box.code(log_text, language="bash")
        
        if st.button("Wyczyść logi"):
            st.session_state.logs = []
            st.rerun()
