import asyncio
import discord
from dotenv import load_dotenv
from .config_service import read_config_data, write_config_data


def get_temp_voice_config(guild_id):
    config = read_config_data()
    temp_voice_config = config.get("TEMP_VOICE_CONFIG", {})
    if not isinstance(temp_voice_config, dict):
        temp_voice_config = {}
    return temp_voice_config.get(str(guild_id), {})


def save_temp_voice_config(guild_id, guild_config):
    config = read_config_data()
    temp_voice_config = config.get("TEMP_VOICE_CONFIG", {})
    if not isinstance(temp_voice_config, dict):
        temp_voice_config = {}
    temp_voice_config[str(guild_id)] = guild_config
    config["TEMP_VOICE_CONFIG"] = temp_voice_config
    write_config_data(config)


def get_temp_voice_owned_channels(guild_id):
    guild_config = get_temp_voice_config(guild_id)
    owned_channels = guild_config.get("owned_channels", {})
    if not isinstance(owned_channels, dict):
        owned_channels = {}
    return {str(channel_id): str(owner_id) for channel_id, owner_id in owned_channels.items()}


def update_temp_voice_owned_channel(guild_id, channel_id, owner_id):
    guild_config = get_temp_voice_config(guild_id)
    owned_channels = guild_config.get("owned_channels", {})
    if not isinstance(owned_channels, dict):
        owned_channels = {}
    owned_channels[str(channel_id)] = str(owner_id)
    guild_config["owned_channels"] = owned_channels
    save_temp_voice_config(guild_id, guild_config)


def get_temp_voice_owner_for_channel(guild_id, channel_id):
    return get_temp_voice_owned_channels(guild_id).get(str(channel_id))


def get_temp_voice_default_text_channel_id(guild_id):
    guild_config = get_temp_voice_config(guild_id)
    text_channel_id = guild_config.get("text_channel_id")
    if text_channel_id is None:
        return None
    try:
        return int(text_channel_id)
    except (TypeError, ValueError):
        return None


def set_temp_voice_default_text_channel_id(guild_id, text_channel_id):
    guild_config = get_temp_voice_config(guild_id)
    guild_config["text_channel_id"] = str(text_channel_id)
    save_temp_voice_config(guild_id, guild_config)


def get_temp_voice_text_channel_id(guild_id, channel_id):
    guild_config = get_temp_voice_config(guild_id)
    text_channels = guild_config.get("text_channels", {})
    if not isinstance(text_channels, dict):
        text_channels = {}
    return text_channels.get(str(channel_id))


def set_temp_voice_text_channel_id(guild_id, channel_id, text_channel_id):
    guild_config = get_temp_voice_config(guild_id)
    text_channels = guild_config.get("text_channels", {})
    if not isinstance(text_channels, dict):
        text_channels = {}
    text_channels[str(channel_id)] = str(text_channel_id)
    guild_config["text_channels"] = text_channels
    save_temp_voice_config(guild_id, guild_config)


def remove_temp_voice_text_channel_id(guild_id, channel_id):
    guild_config = get_temp_voice_config(guild_id)
    text_channels = guild_config.get("text_channels", {})
    if not isinstance(text_channels, dict):
        text_channels = {}
    text_channels.pop(str(channel_id), None)
    guild_config["text_channels"] = text_channels
    save_temp_voice_config(guild_id, guild_config)


def is_temp_voice_managed_channel(guild_id, channel_id):
    return str(channel_id) in get_temp_voice_owned_channels(guild_id)


def remove_temp_voice_owned_channel(guild_id, channel_id):
    guild_config = get_temp_voice_config(guild_id)
    owned_channels = guild_config.get("owned_channels", {})
    if not isinstance(owned_channels, dict):
        owned_channels = {}
    owned_channels.pop(str(channel_id), None)
    guild_config["owned_channels"] = owned_channels
    text_channels = guild_config.get("text_channels", {})
    if isinstance(text_channels, dict):
        text_channels.pop(str(channel_id), None)
        guild_config["text_channels"] = text_channels
    save_temp_voice_config(guild_id, guild_config)


def get_temp_voice_cleanup_timeout():
    config = read_config_data()
    timeout = config.get("TEMP_VOICE_CLEANUP_TIMEOUT_SECONDS", 300)
    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        timeout = 300
    return max(1, timeout)


def build_temp_voice_help_message(owner_mention):
    owner_mention = owner_mention or "владелец канала"
    return (
        f"{owner_mention}, команды для управления голосовым каналом:\n"
        "!renamevoice <имя> — переименовать канал\n"
        "!setvoiceuserlimit <число> — задать лимит участников\n"
        "!voiceinfo — показать параметры канала"
    )


def normalize_channel_name(name):
    if not name:
        return ""
    return "".join(ch for ch in name.lower() if ch.isalnum())


async def send_temp_voice_help_message(guild, voice_channel, owner, text_channel_id=None):
    if guild is None or voice_channel is None or owner is None:
        return None

    if text_channel_id is None:
        tracked_text_channel_id = get_temp_voice_text_channel_id(guild.id, voice_channel.id)
        if tracked_text_channel_id is None:
            tracked_text_channel_id = get_temp_voice_default_text_channel_id(guild.id)
        text_channel_id = tracked_text_channel_id

    if text_channel_id is None:
        return None

    text_channel = guild.get_channel(int(text_channel_id))
    if text_channel is None:
        return None

    owner_mention = owner.mention if hasattr(owner, "mention") else f"<@{owner.id}>"
    try:
        await text_channel.send(build_temp_voice_help_message(owner_mention))
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"Unable to send temporary voice help message: {exc}")
        return None

    return text_channel