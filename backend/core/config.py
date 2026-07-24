"""
Application settings loaded from environment variables.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = ""

    # Auth
    NEXTAUTH_SECRET: str = ""
    NEXTAUTH_URL: str = "http://localhost:3000"

    # Groq
    GROQ_API_KEY: str
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # OCR
    OCR_PROVIDER: str = "mistral"          # mistral | tesseract
    MISTRAL_API_KEY: str = ""

    # Embedding
    EMBEDDING_PROVIDER: str = "ollama"     # ollama | openai
    OLLAMA_ENDPOINT: str = "http://localhost:11434"
    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIM: int = 768

    # Query tuning
    MIN_SIMILARITY_SCORE: float = 0.72
    MAX_CHUNKS: int = 8
    MAX_CONTEXT_TOKENS: int = 6000

    # Memory
    MEMORY_WINDOW: int = 10
    MEMORY_SUMMARY_AFTER_DAYS: int = 7

    # File storage
    UPLOAD_DIR: str = "./uploads"

    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]

    # Backend
    BACKEND_URL: str = "http://localhost:8000"


settings = Settings()
