from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API Keys (all optional - providers without keys are disabled)
    apollo_api_key: str = ""
    rocketreach_api_key: str = ""
    lusha_api_key: str = ""
    prospeo_api_key: str = ""
    snov_api_key: str = ""

    # Provider order (comma-separated, e.g., "apollo,rocketreach,prospeo")
    provider_order: str = "apollo,rocketreach,prospeo,snov"

    # Server config
    port: int = 8000
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def get_provider_order(self) -> List[str]:
        """Return list of enabled providers in order."""
        return [p.strip() for p in self.provider_order.split(",") if p.strip()]

    def is_provider_enabled(self, provider: str) -> bool:
        """Check if provider is in the order list and has an API key."""
        if provider not in self.get_provider_order():
            return False
        key_map = {
            "apollo": self.apollo_api_key,
            "rocketreach": self.rocketreach_api_key,
            "lusha": self.lusha_api_key,
            "prospeo": self.prospeo_api_key,
            "snov": self.snov_api_key,
        }
        return bool(key_map.get(provider, ""))


settings = Settings()
