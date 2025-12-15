import streamlit as st
from github import Github
import openai
import os
import json
import time

# --- KONFIGURACJA ---
st.set_page_config(page_title="Builder Bot V2", page_icon="🏗️", layout="wide")

GH_TOKEN = os.getenv("GH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
INFRA_REPO_NAME = "homelab-infra"  # Nazwa Twojego repo z infrastrukturą

# Sprawdzenie kluczy
if not GH_TOKEN or not OPENAI_API_KEY:
    st.error("❌ Brak kluczy środowiskowych (GH_TOKEN lub OPENAI_API_KEY).")
    st.stop()

# Inicjalizacja klientów
g = Github(GH_TOKEN)
client = openai.OpenAI(api_key=OPENAI_API_KEY)
user = g.get_user()

st.title(f"🏗️ Builder Bot V2.1 (Operator: {user.login})")
st.markdown("---")

# --- FUNKCJE POMOCNICZE ---

def generate_project_structure(prompt):
    """Pyta AI o kod i strukturę plików."""
    system_prompt = """
    Jesteś ekspertem DevOps i Python. Tworzysz mikroserwisy webowe.
    Twoim zadaniem jest wygenerowanie kompletnego kodu aplikacji na podstawie opisu.
    
    MUSISZ zwrócić odpowiedź TYLKO jako czysty JSON w formacie:
    {
        "nazwa_projektu": "krótka-nazwa-bez-spacji",
        "pliki": {
            "app.py": "kod aplikacji...",
            "requirements.txt": "lista bibliotek...",
            "Dockerfile": "instrukcja docker...",
            "README.md": "opis..."
        }
    }
    
    ZASADY:
    1. Dockerfile MUSI być poprawny i uruchamiać aplikację (np. EXPOSE 80).
    2. Aplikacja MUSI działać na porcie 80 (jeśli to webówka).
    3. Kod ma być prosty i działający.
    4. NIE dodawaj Markdowna (```json) na początku ani na końcu. Czysty JSON.
    """
    
    response = client.chat.completions.create(
        model="gpt-4-turbo-preview", # Lub gpt-3.5-turbo jeśli wolisz taniej
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def create_github_repo(project_name, files):
    """Tworzy repozytorium i wrzuca pliki."""
    try:
        # 1. Tworzenie repo
        repo = user.create_repo(project_name, private=True)
        
        # 2. Tworzenie plików aplikacji
        for filename, content in files.items():
            repo.create_file(filename, f"Init {filename}", content)
            
        # 3. Tworzenie GitHub Action (Build & Push)
        workflow_content = f"""
name: Build and Push
on: [push]
env:
  REGISTRY: ghcr.io
  IMAGE_NAME: {user.login.lower()}/{project_name}
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
        repo.create_file(".github/workflows/deploy.yml", "Add CI workflow", workflow_content)
        
        return repo.html_url
    except Exception as e:
        st.error(f"Błąd przy tworzeniu repozytorium: {e}")
        return None

def update_infra_stack(project_name):
    """Aktualizuje docker-compose.yml w repo homelab-infra."""
    try:
        repo = g.get_user().get_repo(INFRA_REPO_NAME)
        file = repo.get_contents("docker-compose.yml")
        content = file.decoded_content.decode("utf-8")
        
        # Szablon nowego serwisu (GitOps)
        new_service = f"""
  
  # --- Auto-generated: {project_name} ---
  {project_name}:
    image: ghcr.io/{user.login.lower()}/{project_name}:latest
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
        # Sprawdź czy już nie istnieje
        if f"container_name: {project_name}" in content:
            return "Serwis już istnieje w pliku infra."

        # Dopisanie do sekcji services (uproszczone: doklejamy przed networks)
        # Najlepiej dokleić na koniec pliku, ale przed 'networks:' jeśli jest na końcu.
        # Dla uproszczenia doklejamy po prostu do łańcucha tekstowego przed definicją networks na dole
        # lub po prostu na koniec sekcji services.
        
        # PROSTA METODA: Szukamy 'networks:' na końcu pliku i wstawiamy przed nim
        if "networks:" in content:
            parts = content.split("networks:")
            # parts[0] to wszystko do momentu networks
            # parts[1] to definicja sieci
            new_content = parts[0] + new_service + "\nnetworks:" + parts[1]
        else:
            new_content = content + new_service

        repo.update_file(file.path, f"Add service {project_name}", new_content, file.sha)
        return "Zaktualizowano homelab-infra"
    except Exception as e:
        return f"Błąd infra: {e}"

# --- INTERFEJS UŻYTKOWNIKA ---

with st.form("builder_form"):
    prompt = st.text_area("Co chcesz zbudować?", "Prosta strona w Pythonie wyświetlająca aktualną godzinę i losowy cytat.")
    submitted = st.form_submit_button("🚀 Buduj Aplikację")

if submitted:
    with st.status("🏗️ Pracuję nad Twoim projektem...", expanded=True) as status:
        
        # 1. Generowanie kodu
        st.write("🧠 1. Generuję kod i strukturę (OpenAI)...")
        project_data = generate_project_structure(prompt)
        project_name = project_data['nazwa_projektu']
        st.json(project_data) # Podgląd dla Ciebie
        
        # 2. GitHub Repo
        st.write(f"📂 2. Tworzę repozytorium: {project_name}...")
        repo_url = create_github_repo(project_name, project_data['pliki'])
        
        if repo_url:
            st.write(f"✅ Repo gotowe: {repo_url}")
            
            # 3. GitOps Update
            st.write("🔗 3. Aktualizuję infrastrukturę (homelab-infra)...")
            infra_status = update_infra_stack(project_name)
            st.write(f"ℹ️ Status infra: {infra_status}")
            
            status.update(label="✅ Gotowe! Proces wdrożenia rozpoczęty.", state="complete", expanded=True)
            st.success(f"Aplikacja **{project_name}** została zakolejkowana.")
            st.info(f"Dostępna będzie pod adresem: https://{project_name}.osabosa.pl (za ok. 3-5 min)")
        else:
            status.update(label="❌ Błąd krytyczny.", state="error")
