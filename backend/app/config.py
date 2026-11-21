import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://radar:radar@127.0.0.1:5432/radar"
    )
    JSON_AS_ASCII = False

    OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    LLM_MODEL = os.environ.get("LLM_MODEL", "hf.co/Remek/basal-2.0-4.5B-GGUF:Q8_0")
    EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3")
    # Jeden rozmiar kontekstu we wszystkich wywołaniach: inny rozmiar zmusza Ollamę do przeładowania modelu.
    LLM_NUM_CTX = int(os.environ.get("LLM_NUM_CTX", "4096"))
    BASAL_URL = os.environ.get("BASAL_URL", "")


# Wymiar wektora bge-m3. Zmiana modelu embeddingów wymaga `make db-reset`.
EMBED_DIM = 1024
