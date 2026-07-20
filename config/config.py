from pydantic_settings import BaseSettings


class Settings(BaseSettings):
        # --- NetBox ---
    NETBOX_URL:   str
    NETBOX_TOKEN: str
    NETBOX_CERT:  str

    # --- Checkpoint ssh ---
    CHP_LOGIN:   str
    CHP_PASSWORD: str
    CHP_EXPERT: str

    # --- Pyrus ---
    PYRUS_LOGIN:      str
    PYRUS_SECRET_KEY: str


settings = Settings()