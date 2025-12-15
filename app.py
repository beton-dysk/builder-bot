import streamlit as st
from github import Github
import os

# Konfiguracja strony
st.set_page_config(page_title="Builder Bot", page_icon="🤖")
st.title("🤖 Builder Bot V1")

# Pobranie sekretów ze zmiennych środowiskowych
GH_TOKEN = os.getenv("GH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Sprawdzenie konfiguracji
if not GH_TOKEN:
    st.error("Brak tokenu GH_TOKEN! Sprawdź konfigurację Stacka.")
    st.stop()

if not OPENAI_API_KEY:
    st.warning("Brak klucza OPENAI_API_KEY. Generowanie kodu nie zadziała.")

# Połączenie z GitHubem
try:
    g = Github(GH_TOKEN)
    user = g.get_user()
    st.success(f"Zalogowano jako: {user.login}")
    
    # Wyświetl repozytoria (test uprawnień)
    st.subheader("Widzę Twoje repozytoria:")
    repos = user.get_repos()
    repo_list = [repo.name for repo in repos][:5] # Pokaż 5 pierwszych
    st.write(repo_list)

except Exception as e:
    st.error(f"Błąd połączenia z GitHub: {e}")

# Prosty czat (Placeholder)
prompt = st.chat_input("Co chcesz zbudować?")
if prompt:
    st.write(f"Użytkownik napisał: {prompt}")
    st.info("Logika generowania kodu zostanie dodana w V2.")