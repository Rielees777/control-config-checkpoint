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

    # --- Splunk API ---
    SPLUNK_URL: str
    SPLUNK_TOKEN: str
    SPLUNK_PORT: int = 8088
    SPLUNK_INDEX: str = "itcontrol_net"

    # --- Active Directory (LDAP) ---
    AD_LOGIN: str
    AD_PASSWORD: str
    AD_SSH_GROUP_NAME: str = ""


def splunk_creds():
    return {
        "url": settings.SPLUNK_URL,
        "token": settings.SPLUNK_TOKEN,
        "port": settings.SPLUNK_PORT,
        "index": settings.SPLUNK_INDEX,
    }


settings = Settings()