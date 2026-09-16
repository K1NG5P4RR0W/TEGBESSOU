from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # Base de données
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "tegbessou"
    postgres_user: str = "tegbessou_app"
    postgres_password: str = ""
    redis_url: str = "redis://redis:6379/0"

    # Chiffrement (Credential Vault) — base64 de 32 octets
    master_key: str = Field(default="", validation_alias="TEGBESSOU_MASTER_KEY")

    # JWT (Ed25519). PEM de la clé privée ; si vide, clé éphémère générée au démarrage.
    jwt_private_key: str = Field(default="", validation_alias="JWT_PRIVATE_KEY")
    access_ttl_seconds: int = 900  # 15 min
    refresh_ttl_seconds: int = 604800  # 7 jours

    # MFA TOTP : désactivée par défaut (usage local). À activer sur toute instance exposée.
    require_mfa: bool = False

    # Coffre de fichiers (autorisations) — répertoire du volume + limite de taille
    file_vault_dir: str = Field(default="/data/authorizations", validation_alias="FILE_VAULT_DIR")
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 Mo

    @property
    def async_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_dsn(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
