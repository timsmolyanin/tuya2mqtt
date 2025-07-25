import tomllib
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "settings" / "config.toml"


def load_settings(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    """Load service configuration from TOML file."""
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}
