from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    github_client_id: str = ""
    github_client_secret: str = ""
    github_callback_url: str = "http://localhost:8000/auth/github/callback"
    token_encryption_key: str = ""
    database_path: str = "./data/auth.sqlite3"
    archive_database_path: Path = Path("./data/archive/catalogue.sqlite3")
    archive_content_path: Path = Path("./data/archive/content")
    archive_busy_timeout_ms: int = Field(default=5000, ge=1, le=30000)
    archive_github_token: str = ""
    archive_github_api_url: str = "https://api.github.com"
    archive_github_timeout: float = Field(default=10, gt=0, le=30)
    archive_github_attempts: int = Field(default=3, ge=1, le=5)
    archive_github_max_redirects: int = Field(default=3, ge=0, le=5)
    archive_github_metadata_bytes: int = Field(default=524288, ge=1024, le=2097152)
    archive_github_readme_bytes: int = Field(default=262144, ge=1024, le=1048576)
    archive_github_retry_max_wait: float = Field(default=5, gt=0, le=60)
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
    max_github_search_response: int = Field(default=1048576, ge=1024, le=2097152)
    max_readme_chars: int = Field(default=60000, ge=1000)
    max_favourites: int = Field(default=500, ge=1)

    @field_validator("archive_github_api_url")
    @classmethod
    def archive_github_origin(cls, value):
        parsed = urlsplit(value)
        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError(
                "Archive GitHub API URL must be an https origin"
            ) from error
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or port == 0
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Archive GitHub API URL must be an https origin")
        host = parsed.hostname.lower()
        if port in (None, 443):
            return f"https://{host}"
        return f"https://{host}:{port}"

    @field_validator("archive_database_path", "archive_content_path", mode="before")
    @classmethod
    def archive_file_paths(cls, value):
        text = str(value)
        if (
            not text.strip()
            or text != text.strip()
            or text == ":memory:"
            or text.startswith("file:")
        ):
            raise ValueError("Archive paths must be ordinary filesystem paths")
        return value

    @model_validator(mode="after")
    def separate_archive_paths(self):
        auth = Path(self.database_path).expanduser().resolve()
        archive = self.archive_database_path.expanduser().resolve()
        content = self.archive_content_path.expanduser().resolve()
        if not self.archive_database_path.name or archive.is_dir():
            raise ValueError("Archive database path must include a filename")
        if (
            archive == auth
            or archive
            in (Path(str(auth) + suffix) for suffix in ("-wal", "-shm", "-journal"))
            or auth
            in (Path(str(archive) + suffix) for suffix in ("-wal", "-shm", "-journal"))
            or (archive.exists() and auth.exists() and archive.samefile(auth))
            or content == archive
            or content == auth
            or content in archive.parents
            or content in auth.parents
        ):
            raise ValueError(
                "Archive database, content directory and auth database must be separate"
            )
        return self
