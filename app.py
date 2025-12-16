import streamlit as st
import openai
import os
import subprocess
import sys
import time
import signal

# --- KONFIGURACJA ---
st.set_page_config(page_title="Builder Lab", page_icon="🧪", layout="wide")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DOMAIN = os.getenv("DOMAIN")

if not OPENAI_API_KEY:
    st.error("❌ Brak klucza OPENAI_API_KEY.")
    st.stop()

# Ustalanie adresu podglądu
if not DOMAIN:
    PREVIEW_URL = "http://localhost:5000"
else:
    PREVIEW_URL = f"https://preview.{DOMAIN}"

client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Ścieżki
SANDBOX_DIR = "sandbox"
APP_FILE = os.path.join(SANDBOX_DIR, "app.py")
LOG_FILE = os.path.join(SANDBOX_DIR, "server.log")

os.makedirs(SANDBOX_DIR, exist_ok=True)

# --- SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": """
        Jesteś ekspertem Python/Flask. 
        ZASADY:
        1. Generuj kod pliku `app.py`.
        2. Aplikacja MUSI startować na porcie 5000 i host=0.0.0.0.
        3. Przykład startu: `if __name__ == '__main__': app.run(host='0.0.0.0', port=5000)`
        4. Nie używaj debug=True.
        """}
    ]
if "generated_code" not in st.session_state:
    st.session_state.generated_code = ""
# Przechowujemy PID procesu zamiast obiektu, żeby przetrwało odświeżenie strony
if "server_pid" not in st.session_state:
    st.session_state.server_pid = None

# --- FUNKCJE ---

def run_app():
    """Uruchamia aplikację Flask i przekierowuje logi do pliku."""
    stop_app()
    
    # Zapisz kod
    with open(APP_FILE, "w") as f:
        f.write(st.session_state.generated_code)
    
    # Otwórz plik logów
    log_file = open(LOG_FILE, "w")
    
    # Uruchom proces (stdout i stderr idą do pliku)
    process = subprocess.Popen(
        [sys.executable, "-u", "app.py"],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=SANDBOX_DIR
    )
    st.session_state.server_pid = process.pid
    
    # Daj chwilę na start
    time.sleep(1)

def stop_app():
    """Ubija proces na podstawie PID."""
    if st.session_state.server_pid:
        try:
            os.kill(st.session_state.server_pid, signal.SIGTERM)
            st.session_state.server_pid = None
        except ProcessLookupError:
            st.session_state.server_pid = None
        except Exception as e:
            st.error(f"Błąd zatrzymywania: {e}")

def get_logs():
    """Czyta logi z pliku."""
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            return f.read()
    return "Brak logów."

def generate_response(prompt):
    st.session_state.messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        messages=st.session_state.messages
    )
    bot_reply = response.choices[0].message.content
    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
    
    code = ""
    if "```python" in bot_reply:
        code = bot_reply.split("```python")[1].split("```")[0]
    elif "```" in bot_reply:
        code = bot_reply.split("```")[1].split("```")[0]
        
    if code:
        if "app.run" in code and "0.0.0.0" not in code:
            code = code.replace("app.run(", "app.run(host='0.0.0.0', ")
        st.session_state.generated_code = code
        run_app()

# --- UI ---
st.title("🧪 Builder Lab")

col_left, col_right = st.columns([1, 1.2], gap="large")

with col_left:
    st.subheader("💬 Chat")
    chat_container = st.container(height=600)
    with chat_container:
        for msg in st.session_state.messages:
            if msg["role"] != "system":
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
    
    if prompt := st.chat_input("Co budujemy?"):
        with st.spinner("Kodowanie..."):
            generate_response(prompt)
            st.rerun()

with col_right:
    st.subheader("👁️ Preview")
    
    # Sprawdzamy czy proces żyje
    is_running = False
    if st.session_state.server_pid:
        try:
            os.kill(st.session_state.server_pid, 0) # Sygnał 0 sprawdza czy proces istnieje
            is_running = True
        except ProcessLookupError:
            st.session_state.server_pid = None

    c1, c2, c3 = st.columns([2, 1, 1])
    c1.markdown(f"**URL:** `{PREVIEW_URL}`")
    
    if c2.button("🔄 Restart"):
        if st.session_state.generated_code:
            run_app()
            st.rerun()
    
    if is_running:
        c3.success("Running")
        st.components.v1.iframe(PREVIEW_URL, height=600, scrolling=True)
    else:
        c3.error("Stopped")
    
    with st.expander("Terminal Logs / Source Code", expanded=True):
        st.caption("Ostatnie logi (odśwież stronę aby zaktualizować):")
        st.code(get_logs(), language="bash")
        st.caption("Kod:")
        st.code(st.session_state.generated_code, language="python")
