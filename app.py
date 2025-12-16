import streamlit as st
<<<<<<< HEAD
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
=======
from github import Github, GithubException
import openai
import os
import json

# --- KONFIGURACJA ---
st.set_page_config(page_title="Builder Bot V4 (Beton-Dysk)", page_icon="🏢", layout="wide")

GH_TOKEN = os.getenv("GH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
INFRA_REPO_NAME = "homelab-infra"

# WYMUSZENIE ORGANIZACJI:
# Jeśli zmienna nie jest ustawiona w Portainerze, użyjemy "beton-dysk"
GITHUB_ORG_NAME = os.getenv("GITHUB_ORG_NAME", "beton-dysk") 

if not GH_TOKEN or not OPENAI_API_KEY:
    st.error("❌ Brak kluczy środowiskowych.")
    st.stop()

# Inicjalizacja
g = Github(GH_TOKEN)
client = openai.OpenAI(api_key=OPENAI_API_KEY)
# user = g.get_user() # <- To nam już niepotrzebne jako główne źródło

# --- LOGIKA: TYLKO ORGANIZACJA ---
try:
    # Pobieramy konkretnie organizację
    target_entity = g.get_organization(GITHUB_ORG_NAME)
    # Weryfikacja (dla pewności, że to org)
    if target_entity.type != "Organization":
        st.error(f"❌ {GITHUB_ORG_NAME} nie jest Organizacją!")
        st.stop()
        
    owner_name = GITHUB_ORG_NAME.lower()
    
    # Pobieramy użytkownika tylko po to, żeby mieć dostęp do repo infra (jeśli infra jest na prywatnym)
    # Jeśli infra TEŻ jest w organizacji beton-dysk, zmień poniżej 'g.get_user()' na 'target_entity'
    infra_owner = g.get_user() 
    
except Exception as e:
    st.error(f"❌ Nie mam dostępu do organizacji '{GITHUB_ORG_NAME}'. Sprawdź uprawnienia tokena GH_TOKEN! Błąd: {e}")
    st.stop()

st.sidebar.success(f"🏢 WYMUSZONA ORGANIZACJA: {GITHUB_ORG_NAME}")

# --- FUNKCJE ---

def generate_project_structure(prompt):
    """Pyta AI o kod i strukturę plików."""
    system_prompt = """
    Jesteś ekspertem DevOps i Python. Tworzysz mikroserwisy webowe.
    Twoim zadaniem jest wygenerowanie kompletnego kodu aplikacji na podstawie opisu.
    
    MUSISZ zwrócić odpowiedź TYLKO jako czysty JSON w formacie:
    {
        "nazwa_projektu": "krotka-nazwa-bez-spacji-malymi-literami",
        "pliki": {
            "app.py": "kod aplikacji...",
            "requirements.txt": "lista bibliotek...",
            "Dockerfile": "instrukcja docker...",
            "README.md": "opis..."
        }
    }
    ZASADY:
    1. Dockerfile MUSI być poprawny i wystawiać port 80.
    2. Kod ma być prosty i działający.
    3. JSON musi być poprawny.
    """
    
    response = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def create_github_repo(project_name, files):
    """Tworzy lub aktualizuje repo w Organizacji lub u Użytkownika."""
    repo = None
    try:
        # 1. Próba pobrania istniejącego repo (użytkownika lub org)
        try:
            repo = target_entity.get_repo(project_name)
            st.warning(f"⚠️ Repozytorium '{project_name}' już istnieje w {owner_name}. Nadpisuję...")
        except GithubException:
            # 2. Tworzenie nowego (jeśli nie istnieje)
            # target_entity to albo User albo Organization object
            repo = target_entity.create_repo(project_name, private=True)
            st.success(f"✅ Utworzono nowe repozytorium: {owner_name}/{project_name}")
        
        # 3. GitHub Action (Z poprawionym IMAGE_NAME pod organizację)
        workflow_content = f"""
name: Build and Push
on: [push]
env:
  REGISTRY: ghcr.io
  IMAGE_NAME: {owner_name}/{project_name}
jobs:
  build-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ${{{{ env.REGISTRY }}}}
          username: ${{{{ github.actor }}}}
          password: ${{{{ secrets.GITHUB_TOKEN }}}}
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}:latest
        """
        files[".github/workflows/deploy.yml"] = workflow_content

        # 4. Upload plików
        for filename, content in files.items():
            try:
                existing_file = repo.get_contents(filename)
                repo.update_file(existing_file.path, f"Update {filename}", content, existing_file.sha)
            except GithubException:
                repo.create_file(filename, f"Init {filename}", content)
        
        return repo.html_url

    except Exception as e:
        st.error(f"Błąd GitHub: {e}")
        return None

def update_infra_stack(project_name):
    """Aktualizuje homelab-infra."""
    try:
        # Infra zawsze jest na koncie użytkownika (lub też w orgu, zależy gdzie trzymasz)
        # Zakładam, że infra jest tam, gdzie user ma dostęp.
        repo = target_entity.get_repo(INFRA_REPO_NAME) 
        file = repo.get_contents("docker-compose.yml")
        content = file.decoded_content.decode("utf-8")
        
        # Generujemy URL obrazu z uwzględnieniem organizacji!
        image_url = f"ghcr.io/{owner_name}/{project_name}:latest"
        
        new_service = f"""
  
  # --- Auto: {project_name} ({owner_name}) ---
  {project_name}:
    image: {image_url}
    container_name: {project_name}
    restart: always
    labels:
      - "tsdproxy.enable=true"
      - "tsdproxy.name={project_name}"
      - "tsdproxy.container_port=80"
      - "traefik.enable=true"
      - "traefik.http.routers.{project_name}.rule=Host(`{project_name}.${{DOMAIN}}`)"
      - "traefik.http.routers.{project_name}.entrypoints=web"
      - "com.centurylinklabs.watchtower.enable=true"
    networks:
      - siec
"""
        if f"container_name: {project_name}" in content:
            return "Serwis już istnieje w infra."

        if "networks:" in content:
            parts = content.split("networks:")
            new_content = parts[0] + new_service + "\nnetworks:" + parts[1]
        else:
            new_content = content + new_service

        repo.update_file(file.path, f"Add service {project_name}", new_content, file.sha)
        return "Zaktualizowano homelab-infra"
    except Exception as e:
        return f"Błąd infra: {e}"

# --- GUI ---

with st.form("builder_form"):
    prompt = st.text_area("Co budujemy dla Organizacji?", "Strona wizytówka dla firmy...")
    submitted = st.form_submit_button("🚀 Buduj w Organizacji")

if submitted:
    with st.status("🏗️ Pracuję...", expanded=True) as status:
        st.write("🧠 Generowanie kodu...")
        project_data = generate_project_structure(prompt)
        p_name = project_data['nazwa_projektu']
        
        st.write(f"📂 Tworzenie repo w: {owner_name}...")
        repo_url = create_github_repo(p_name, project_data['pliki'])
        
        if repo_url:
            st.write("🔗 Aktualizacja infrastruktury...")
            update_infra_stack(p_name)
            status.update(label="✅ Gotowe!", state="complete")
            st.success(f"Repozytorium: {repo_url}")
            st.info(f"Adres: https://{p_name}.osabosa.pl")
>>>>>>> 8cb88ba4daf6c8e12f0e03b77b2793276c6bea27
