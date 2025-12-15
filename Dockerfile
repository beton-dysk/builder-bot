FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Streamlit domyślnie działa na porcie 8501
EXPOSE 8501

# Komenda startowa
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]