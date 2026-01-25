import os

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Google Cloud
    project_id: str = Field(..., env="PROJECT_ID")
    location: str = Field(..., env="LOCATION")
    queue_name: str = Field(..., env="QUEUE_NAME")
    gen_worker_url: str = Field(..., env="GEN_WORKER_URL")
    invoker_sa_email: str = Field(..., env="INVOKER_SA_EMAIL")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()


def get_settings():
    return settings