from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    agent_model: str = "claude-sonnet-4-6"
    router_model: str = "claude-haiku-4-5-20251001"
    embedding_model: str = "text-embedding-3-small"

    whatsapp_provider: str = "gupshup"
    whatsapp_api_key: str = ""
    whatsapp_app_name: str = ""

    staff_alert_webhook: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
