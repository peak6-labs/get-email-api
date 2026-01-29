from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    apollo_api_key: str
    port: int = 8000
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
