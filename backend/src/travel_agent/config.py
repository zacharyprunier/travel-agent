"""
Application configuration via pydantic-settings.

pydantic-settings reads values from environment variables and/or a .env file
automatically. Field names map directly to env var names (case-insensitive).

Usage:
    from travel_agent.config import settings
    print(settings.anthropic_model)

To override any value, set the corresponding env var or add it to .env.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Don't raise on extra env vars — avoid noise from system-level vars
        extra="ignore",
    )

    # --- Anthropic ---
    anthropic_api_key: str
    # Swap the model without touching code — useful for cost/speed tradeoffs
    anthropic_model: str = "claude-opus-4-5"
    anthropic_max_tokens: int = 4096

    # --- Duffel ---
    # Test keys start with "duffel_test_" and hit the sandbox automatically
    duffel_api_key: str
    duffel_base_url: str = "https://api.duffel.com"
    # Stays/Hotels API requires sales approval from Duffel before enabling.
    # Set DUFFEL_ACCOMMODATIONS_ENABLED=true only after your account is approved.
    duffel_accommodations_enabled: bool = False
    # Stays/Hotels API requires sales approval from Duffel before use.
    # Set to true only after your account has been granted access.
    duffel_accommodations_enabled: bool = False

    # --- Geoapify ---
    geoapify_api_key: str
    geoapify_base_url: str = "https://api.geoapify.com"

    # --- Auth ---
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    # Path to the JSON file used as the user/revocation store (relative to CWD)
    db_path: str = "data/db.json"

    # --- Deployment ---
    # Controls access to /docs and /openapi.json. Defaults to PROD (most restrictive).
    # Set to DEV to allow unauthenticated access to API docs.
    deployment_type: str = "PROD"

    # --- API server ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_debug: bool = False


# Single shared instance — import this everywhere instead of instantiating Settings()
settings = Settings()
