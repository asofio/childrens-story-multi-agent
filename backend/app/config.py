from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    foundry_project_endpoint: str = ""
    foundry_model_deployment_name: str = "gpt-4o"
    foundry_image_model_deployment_name: str = "gpt-image-1"

    # Azure Speech Service (TTS)
    azure_speech_region: str = ""
    azure_speech_resource_id: str = ""   # /subscriptions/.../resourceGroups/.../providers/Microsoft.CognitiveServices/accounts/<name>
    azure_speech_endpoint: str = ""       # optional custom endpoint override

    # Feature flags
    skip_story_reviewer: bool = False  # set to True to auto-approve every story (skips LLM review)

    # CORS origin for the React dev server
    cors_origin: str = "http://localhost:5173"


settings = Settings()
