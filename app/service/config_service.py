import json
from pathlib import Path
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"


def load_reaction_role_config():
    if not CONFIG_PATH.exists():
        return None

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as exc:
        raise RuntimeError("config.json must contain valid JSON") from exc

    if not isinstance(config, dict):
        raise RuntimeError("config.json must contain a JSON object")

    channel_id = config.get("REACTION_ROLE_CHANNEL_ID")
    mapping = config.get("REACTION_ROLE_MAP")

    if not channel_id or not mapping:
        return None

    try:
        channel_id = int(channel_id)
    except ValueError as exc:
        raise RuntimeError("REACTION_ROLE_CHANNEL_ID must be a numeric channel ID") from exc

    if not isinstance(mapping, dict):
        raise RuntimeError("REACTION_ROLE_MAP must be a JSON object of emoji -> role")

    return channel_id, {str(emoji): str(role_spec) for emoji, role_spec in mapping.items()}


def read_config_data():
    if not CONFIG_PATH.exists():
        return {}

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as exc:
        raise RuntimeError("config.json must contain valid JSON") from exc

    if not isinstance(config, dict):
        raise RuntimeError("config.json must contain a JSON object")
    return config


def write_config_data(config):
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
        file.write("\n")


def save_reaction_role_config(channel_id=None, mapping=None):
    config = read_config_data()
    if channel_id is not None:
        config["REACTION_ROLE_CHANNEL_ID"] = channel_id
    if mapping is not None:
        config["REACTION_ROLE_MAP"] = mapping
    write_config_data(config)
    return config


def get_authorized_user_ids():
    config = read_config_data()
    authorized_ids = config.get("AUTHORIZED_USER_IDS", [])
    if isinstance(authorized_ids, list):
        return [str(user_id) for user_id in authorized_ids if str(user_id).strip()]
    return []
