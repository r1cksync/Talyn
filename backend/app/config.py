import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="TALYN_")
    environment: str = "development"
    mode: str = "demo"
    database_url: str = "sqlite:///./.local/talyn.db"
    checkpoint_url: str = ""
    database_secret_arn: str = ""
    database_host: str = ""
    region: str = "ap-south-1"
    public_url: str = "http://localhost:3000"
    session_secret: str = "demo-only-change-this-32-character-secret"
    cognito_pool_id: str = ""
    cognito_client_id: str = ""
    bucket: str = ""
    queue_url: str = ""
    event_queue_url: str = ""
    kms_key_id: str = ""
    bedrock_model_id: str = "apac.amazon.nova-lite-v1:0"
    sender_email: str = ""
    ses_configuration_set: str = ""
    email_allowlist: str = "success@simulator.amazonses.com"
    live_email: bool = False
    data_dir: Path = Path(".local")
    max_document_bytes: int = 10 * 1024 * 1024
    max_recording_bytes: int = 20 * 1024 * 1024
    max_concurrent: int = 10
    max_monthly_minutes: int = 3000
    max_model_calls: int = 12
    retention_days: int = 30
    frame_interval_seconds: int = 30
    silence_seconds: int = 8
    max_textract_pages: int = 10
    run_demo_worker: bool = True

    @model_validator(mode="after")
    def validate_deployment(self):
        if self.mode not in {"demo", "aws"}:
            raise ValueError("TALYN_MODE must be demo or aws")
        if self.environment == "production" and self.mode != "aws":
            raise ValueError("Production refuses mock/demo adapters")
        if self.mode == "aws":
            if not self.public_url.startswith("https://"):
                raise ValueError("AWS mode requires HTTPS")
            if self.session_secret.startswith("demo-") or len(self.session_secret) < 32:
                raise ValueError("AWS mode requires a random session secret")
            if not all([self.cognito_pool_id, self.cognito_client_id, self.bucket, self.queue_url]):
                raise ValueError("AWS resource configuration is incomplete")
            if self.database_url.startswith("sqlite") and not self.database_secret_arn:
                raise ValueError("AWS mode requires PostgreSQL")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self

    def resolve_database(self) -> str:
        if not self.database_secret_arn:
            return self.database_url
        import boto3
        secret = json.loads(boto3.client("secretsmanager", region_name=self.region).get_secret_value(
            SecretId=self.database_secret_arn)["SecretString"])
        return (f"postgresql+psycopg://{quote(secret['username'])}:{quote(secret['password'], safe='')}"
                f"@{self.database_host}:5432/talyn?sslmode=require")


@lru_cache
def settings() -> Settings:
    return Settings()
