import streamlit as st
import openai
import os
import subprocess
import sys
import threading
import time

# --- KONFIGURACJA ---
st.set_page_config(page_title="Builder Lab", page_icon="🧪", layout="wide")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DOMAIN = os.getenv("DOMAIN")

if not OPENAI_API_KEY:
    st.error("❌ Brak klucza OPENAI_API_KEY.")
    st.stop()

if not DOMAIN:
    st.warning("⚠️ Brak zmiennej DOMAIN. Podgląd może nie działać.")
    PREVIEW_URL = "http://localhost:5000"
else:
    # Generujemy poprawny, publiczny adres HTTPS
    PREVIEW_URL = f"https://preview.{DOMAIN}"

client = openai.OpenAI(api_key=OPENAI_API_KEY)
SANDBOX_DIR = "sandbox"
APP_FILE = os.path.join(SANDBOX_DIR, "app.py")
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
if "server_process" not in st.session_state:
    st.session_state.server_process = None
if "logs" not in st.session_state:
    st.session_state.logs = []

# --- FUNKCJE ---

def run_app():
    """Uruchamia aplikację Flask."""
    stop_app()
    
    # Zapisz kod
    with open(APP_FILE, "w") as f:
        f.write(st.session_state.generated_code)
    
    st.session_state.logs = []
    
    # Uruchom proces
    process = subprocess.Popen(
        [sys.executable, "-u", APP_FILE],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=SANDBOX_DIR
    )
    st.session_state.server_process = process
    
    def log_reader(proc):
        for line in iter(proc.stdout.readline, ''):
            st.session_state.logs.append(line)
            if len(st.session_state.logs) > 50:
                st.session_state.logs.pop(0)
    
    t = threading.Thread(target=log_reader, args=(process,), daemon=True)
    t.start()
    
    # Daj mu chwilę na start
    time.sleep(2)

def stop_app():
    if st.session_state.server_process:
        st.session_state.server_process.terminate()
        st.session_state.server_process = None

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
        # BEZPIECZNIK: Wymuszamy host 0.0.0.0 nawet jak AI zapomni
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
    
    # Pasek statusu
    c1, c2, c3 = st.columns([2, 1, 1])
    is_running = st.session_state.server_process is not None
    
    c1.markdown(f"**URL:** `{PREVIEW_URL}`")
    if c2.button("🔄 Restart"):
        if st.session_state.generated_code:
            run_app()
            st.rerun()
    
    if is_running:
        c3.success("Running")
        # --- TU JEST IFRAME ---
        # Używamy pełnej wysokości i scrollowania
        st.components.v1.iframe(PREVIEW_URL, height=600, scrolling=True)
    else:
        c3.error("Stopped")
        st.info("Wpisz polecenie w czacie, aby uruchomić serwer.")

    with st.expander("Terminal Logs / Source Code"):
        st.text("Ostatnie logi:")
        st.code("".join(st.session_state.logs), language="bash")
        st.text("Kod źródłowy:")
        st.code(st.session_state.generated_code, language="python")
