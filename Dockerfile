FROM gcr.io/consultoria-bess-mme136/monitoria-base:latest

WORKDIR /app

# Copia o código fonte (incluindo a pasta frontend/dist que foi compilada localmente)
COPY . .

# Expõe a porta que o Cloud Run usa por padrão (8080)
EXPOSE 8080

# Força o encoding utf-8 para evitar problemas de Unicode no log (emoji do Whisper)
ENV PYTHONIOENCODING=utf-8

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]
