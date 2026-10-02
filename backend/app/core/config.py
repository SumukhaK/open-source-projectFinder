from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    github_client_id: str = ""
    github_client_secret: str = ""
    github_callback_url: str = "http://localhost:8000/auth/github/callback"
    token_encryption_key: str = ""
    database_path: str = "./data/auth.sqlite3"
    allowed_redirects: list[str] = ["reporadar://auth/callback"]
    cors_origins: list[str] = []
    rate_limit: int = Field(default=20, ge=1)
    rate_window: int = Field(default=60, ge=1)
    transaction_ttl: int = Field(default=600, ge=1)
    handoff_ttl: int = Field(default=60, ge=1)
    session_ttl: int = Field(default=28800, ge=1)
    github_timeout: float = Field(default=10, gt=0, le=30)
    github_attempts: int = Field(default=3, ge=1, le=5)
    retry_base_delay: float = Field(default=0.5, gt=0)
    retry_jitter: float = Field(default=0.2, ge=0)
    retry_max_delay: float = Field(default=5, gt=0, le=10)
    max_auth_body: int = Field(default=4096, ge=1024, le=65536)
    discovery_rate_limit: int = Field(default=30, ge=1)
    search_page_size: int = Field(default=20, ge=1, le=50)
    max_github_response: int = Field(default=524288, ge=1024, le=2097152)
    max_readme_chars: int = Field(default=60000, ge=1000)
    max_favourites: int = Field(default=500, ge=1)
