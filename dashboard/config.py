"""Environment configuration using Pydantic BaseSettings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    DATABASE_URL: str
    OPENWEBUI_BASE_URL: str = "http://openwebui:8080"
    DEBUG: bool = False

    # Default weekly budget when user has no budget_id assigned in LiteLLM
    # Should match litellm_settings.max_end_user_budget in litellm/config.yaml
    DEFAULT_WEEKLY_BUDGET: float = 5.0

    # OpenWebUI database (for chat history analysis in coaching feature)
    OPENWEBUI_DATABASE_URL: str = ""

    # LiteLLM API for AI coaching calls (uses dedicated virtual key)
    LITELLM_API_URL: str = "http://litellm:4000"
    COACHING_API_KEY: str = ""
    COACHING_SUMMARIZE_MODEL: str = "chatgpt-5-nano"
    COACHING_ANALYSIS_MODEL: str = "chatgpt-5.4-thinking"

    # SMTP / Feedback
    SMTP_HOST: str = ""
    SMTP_PORT: int = 25
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = False
    FEEDBACK_FROM_EMAIL: str = "noreply@example.edu"
    FEEDBACK_RECIPIENTS: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
