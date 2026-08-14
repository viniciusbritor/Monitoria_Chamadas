FROM python:3.11-slim

WORKDIR /app

# Dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Instala todas as deps Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o projeto (incluindo frontend/dist compilado)
COPY . .

EXPOSE 8080
ENV PYTHONIOENCODING=utf-8

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]
