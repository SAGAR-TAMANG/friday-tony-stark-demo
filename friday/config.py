"""
Configuration — load environment variables and app-wide settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Server identity
    SERVER_NAME: str = os.getenv("SERVER_NAME", "Friday")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # External API keys (add as needed)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    SEARCH_API_KEY: str = os.getenv("SEARCH_API_KEY", "")
    ODYSSEUS_BASE_URL: str = os.getenv("ODYSSEUS_BASE_URL", "http://127.0.0.1:7870")
    ODYSSEUS_BRIDGE_TOKEN: str = os.getenv("ODYSSEUS_BRIDGE_TOKEN", "")

    # Persistent memory — Obsidian vault on disk.
    OBSIDIAN_VAULT_PATH: str = os.getenv(
        "OBSIDIAN_VAULT_PATH",
        str(Path.home() / "FridayVault"),
    )
    MEMORY_FOLDER: str = os.getenv("MEMORY_FOLDER", "Memory")

    # Computer-access sandbox roots used by imported memory/computer helpers.
    WORKSPACE_ROOTS: list[str] = [
        p.strip()
        for chunk in os.getenv("WORKSPACE_ROOTS", str(Path.home())).split(os.pathsep)
        for p in chunk.split(",")
        if p.strip()
    ]


config = Config()
