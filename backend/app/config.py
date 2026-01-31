import os

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Google Cloud
    project_id: str = Field(..., env="PROJECT_ID")
    location: str = Field(..., env="LOCATION")
    modal_token_id: str = Field(..., env="MODAL_TOKEN_ID")
    modal_token_secret: str = Field(..., env="MODAL_TOKEN_SECRET")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()


def get_settings():
    return settings