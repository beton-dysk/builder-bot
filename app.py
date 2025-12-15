import streamlit as st
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
