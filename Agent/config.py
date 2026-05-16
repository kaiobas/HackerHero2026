"""
HackerHero2026 – Child Protection System
Configurações centrais da aplicação.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- API ---
    app_name: str = "HackerHero Guardian"
    app_version: str = "1.0.0"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    debug: bool = False

    # --- Captura de tela ---
    capture_interval_seconds: int = Field(default=5, ge=1, le=60)
    # Nota: screenshots NÃO são salvos em disco. Processados em memória e descartados.

    # --- OCR ---
    ocr_languages: list[str] = ["pt", "en"]
    ocr_gpu: bool = False                      # True se houver GPU disponível

    # --- Motor de Risco ---
    # Limiares de pontuação (0-100)
    risk_yellow_threshold: int = 40
    risk_red_threshold: int = 70

    # --- Agente de IA (Ollama local) ---
    # Instale em: https://ollama.com/download
    # Execute:    ollama serve  &&  ollama pull qwen2.5:7b
    ollama_model: str = "qwen2.5:7b"
    ollama_url: str = "http://localhost:11434"
    ai_context_window: int = 10               # textos recentes enviados à IA (Camada 2)

    ai_analysis_interval_seconds: int = 30

    # --- Notificações ---
    alert_email: str = ""                     # e-mail dos pais (opcional)
    alert_webhook_url: str = ""              # webhook Slack/Discord/etc (opcional)

    # --- Banco de dados ---
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'guardian.db'}"

    # --- Overlay ---
    blur_strength: int = 20                   # intensidade do desfoque (px)
    overlay_color: str = "#FF0000"           # cor da borda de alerta vermelho
    quarantine_message: str = (
        "⚠️  Atividade suspeita detectada. "
        "Aguarde – um responsável será notificado."
    )


settings = Settings()

# Garante que os diretórios necessários existam
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
(BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)
