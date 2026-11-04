import asyncio
import json
import os
from collections import deque
from pathlib import Path

import certifi
from dotenv import load_dotenv

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

load_dotenv()

import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Set DISCORD_TOKEN in environment before running")

CONFIG_PATH = Path(__file__).with_name("config.json")


def load_reaction_role_config():
    if not CONFIG_PATH.exists():
        return None

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as exc:
        raise RuntimeError("config.json must contain valid JSON") from exc

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
            return json.load(file)
    except json.JSONDecodeError:
        return {}


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


def refresh_reaction_role_config():
    global REACTION_ROLE_CONFIG
    try:
        REACTION_ROLE_CONFIG = load_reaction_role_config()
    except RuntimeError as exc:
        print(f"Reaction roles disabled: {exc}")
        REACTION_ROLE_CONFIG = None


try:
    refresh_reaction_role_config()
except RuntimeError as exc:
    print(f"Reaction roles disabled: {exc}")
    REACTION_ROLE_CONFIG = None


intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
bot.remove_command("help")
bot.help_command = None

HELPED_HELP_MESSAGES = set()
HELPED_HELP_QUEUE = deque(maxlen=512)


def is_authorized_user(user):
    return str(user.id) in get_authorized_user_ids()


async def ensure_reaction_management_access(ctx):
    if ctx.guild is None:
        await ctx.send("Эту команду можно использовать только на сервере.")
        return False

    if not is_authorized_user(ctx.author):
        await ctx.send("Доступ запрещён: вы не внесены в список управляющих бота.")
        return False

    if not ctx.guild.me.guild_permissions.manage_roles:
        await ctx.send("Боту нужны права управления ролями.")
        return False

    return True


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    if REACTION_ROLE_CONFIG:
        channel_id, mapping = REACTION_ROLE_CONFIG
        print(f"Reaction roles enabled for channel {channel_id} with {len(mapping)} mapping(s).")
    else:
        print("Reaction roles disabled. Configure a channel and reaction mappings to enable them.")
    print("Bot is ready.")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Неверный формат команды. Проверьте аргументы.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Не удалось распознать один из аргументов команды.")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("Недостаточно прав для выполнения команды.")
    else:
        print(f"Command error: {type(error).__name__}: {error}")


@bot.command(name="help")
async def help_command(ctx):
    message_id = getattr(ctx.message, "id", None)
    if message_id is not None:
        if message_id in HELPED_HELP_MESSAGES:
            return
        HELPED_HELP_MESSAGES.add(message_id)
        HELPED_HELP_QUEUE.append(message_id)
        if len(HELPED_HELP_QUEUE) > HELPED_HELP_QUEUE.maxlen:
            old_id = HELPED_HELP_QUEUE.popleft()
            HELPED_HELP_MESSAGES.discard(old_id)

    config = read_config_data()
    public_help = config.get("HELP_TEXT_PUBLIC") or "Список доступных команд:\n!help"
    admin_help = config.get("HELP_TEXT") or public_help

    help_text = admin_help if is_authorized_user(ctx.author) else public_help
    await ctx.send(help_text)


@bot.command(name="setreactionchannel")
async def setreactionchannel(ctx, channel: discord.TextChannel):
    if not await ensure_reaction_management_access(ctx):
        return

    permissions = channel.permissions_for(ctx.guild.me)
    if not permissions.read_messages or not permissions.send_messages:
        await ctx.send("Боту нужны права на чтение и отправку сообщений в выбранном канале.")
        return

    save_reaction_role_config(channel_id=channel.id)
    refresh_reaction_role_config()
    await ctx.send(f"Канал реакционных ролей установлен: {channel.mention}")


@bot.command(name="addreactionrole")
async def addreactionrole(ctx, emoji: str, role: discord.Role):
    if not await ensure_reaction_management_access(ctx):
        return

    if role >= ctx.guild.me.top_role:
        await ctx.send("Нельзя привязывать роль, которая выше или равна роли бота.")
        return

    config = read_config_data()
    mapping = config.get("REACTION_ROLE_MAP") or {}
    if not isinstance(mapping, dict):
        mapping = {}

    mapping[str(emoji)] = str(role.id)
    save_reaction_role_config(mapping=mapping)
    refresh_reaction_role_config()
    await ctx.send(f"Роль {role.mention} привязана к реакции {emoji}")


@bot.command(name="delreactionrole")
async def delreactionrole(ctx, emoji: str):
    if not await ensure_reaction_management_access(ctx):
        return

    config = read_config_data()
    mapping = config.get("REACTION_ROLE_MAP") or {}
    if not isinstance(mapping, dict):
        mapping = {}

    if str(emoji) not in mapping:
        await ctx.send(f"Для реакции {emoji} нет привязки к роли.")
        return

    mapping.pop(str(emoji), None)
    save_reaction_role_config(mapping=mapping)
    refresh_reaction_role_config()
    await ctx.send(f"Привязка для реакции {emoji} удалена.")


@bot.command(name="reactionroles")
async def reactionroles(ctx):
    if not await ensure_reaction_management_access(ctx):
        return

    if not REACTION_ROLE_CONFIG:
        await ctx.send("Реакционные роли пока не настроены.")
        return

    channel_id, mapping = REACTION_ROLE_CONFIG
    channel = ctx.guild.get_channel(channel_id)
    channel_name = channel.mention if channel else f"ID: {channel_id}"
    lines = [f"Канал: {channel_name}", "Сопоставления:"]
    for emoji, role_spec in mapping.items():
        role = resolve_role(ctx.guild, role_spec)
        role_name = role.name if role else role_spec
        lines.append(f"- {emoji} -> {role_name}")
    await ctx.send("\n".join(lines))


@bot.command(name="addbotuser")
async def addbotuser(ctx, user: discord.User):
    if not await ensure_reaction_management_access(ctx):
        return

    config = read_config_data()
    authorized_ids = config.get("AUTHORIZED_USER_IDS", [])
    if not isinstance(authorized_ids, list):
        authorized_ids = []

    user_id = str(user.id)
    if user_id in authorized_ids:
        await ctx.send(f"Пользователь {user.mention} уже добавлен в список управляющих.")
        return

    authorized_ids.append(user_id)
    config["AUTHORIZED_USER_IDS"] = authorized_ids
    write_config_data(config)
    await ctx.send(f"Пользователь {user.mention} добавлен в список управляющих бота.")


@bot.command(name="delbotuser")
async def delbotuser(ctx, user: discord.User):
    if not await ensure_reaction_management_access(ctx):
        return

    config = read_config_data()
    authorized_ids = config.get("AUTHORIZED_USER_IDS", [])
    if not isinstance(authorized_ids, list):
        authorized_ids = []

    user_id = str(user.id)
    if user_id not in authorized_ids:
        await ctx.send(f"Пользователь {user.mention} не найден в списке управляющих.")
        return

    authorized_ids.remove(user_id)
    config["AUTHORIZED_USER_IDS"] = authorized_ids
    write_config_data(config)
    await ctx.send(f"Пользователь {user.mention} удалён из списка управляющих бота.")


@bot.command(name="setvoicetextchannel")
async def setvoicetextchannel(ctx, channel: discord.TextChannel):
    if ctx.guild is None:
        await ctx.send("Эту команду можно использовать только на сервере.")
        return

    if not is_authorized_user(ctx.author):
        await ctx.send("Доступ запрещён: вы не внесены в список управляющих бота.")
        return

    set_temp_voice_default_text_channel_id(ctx.guild.id, channel.id)
    await ctx.send(f"Текстовый канал для приветствий временных голосовых комнат установлен: {channel.mention}")


@bot.command(name="setupvoicechannel")
async def setupvoicechannel(ctx):
    if ctx.guild is None:
        await ctx.send("Эту команду можно использовать только на сервере.")
        return

    if not is_authorized_user(ctx.author):
        await ctx.send("Доступ запрещён: вы не внесены в список управляющих бота.")
        return

    if not ctx.guild.me.guild_permissions.manage_channels:
        await ctx.send("Боту нужны права управления каналами.")
        return

    guild_config = get_temp_voice_config(ctx.guild.id)
    existing_channel_id = guild_config.get("monitor_channel_id")
    if existing_channel_id:
        existing_channel = ctx.guild.get_channel(int(existing_channel_id))
        if existing_channel is not None:
            await ctx.send(f"Канал для временных голосовых комнат уже настроен: {existing_channel.mention}")
            return

    category = ctx.channel.category
    created_channel = await ctx.guild.create_voice_channel(
        name="➕ Создать канал",
        category=category,
        reason=f"Temporary voice channel setup by {ctx.author}",
    )

    guild_config["monitor_channel_id"] = str(created_channel.id)
    guild_config["owned_channels"] = guild_config.get("owned_channels", {})
    save_temp_voice_config(ctx.guild.id, guild_config)

    await ctx.send(f"Канал для создания временных голосовых комнат создан: {created_channel.mention}")


@bot.command(name="renamevoice")
async def renamevoice(ctx, *, new_name: str):
    if ctx.guild is None:
        await ctx.send("Эту команду можно использовать только на сервере.")
        return

    if not new_name.strip():
        await ctx.send("Введите новое имя канала.")
        return

    if ctx.author.voice is None or ctx.author.voice.channel is None:
        await ctx.send("Вы должны быть в голосовом канале, чтобы переименовать его.")
        return

    channel = ctx.author.voice.channel
    owner_id = get_temp_voice_owner_for_channel(ctx.guild.id, channel.id)
    if owner_id != str(ctx.author.id):
        await ctx.send("Эту команду можно использовать только для канала, который вы создали.")
        return

    if not ctx.guild.me.guild_permissions.manage_channels:
        await ctx.send("Боту нужны права управления каналами.")
        return

    await channel.edit(name=new_name[:100])
    await ctx.send(f"Канал переименован в: {new_name[:100]}")


@bot.command(name="setvoiceuserlimit")
async def setvoiceuserlimit(ctx, limit: int):
    if ctx.guild is None:
        await ctx.send("Эту команду можно использовать только на сервере.")
        return

    if ctx.author.voice is None or ctx.author.voice.channel is None:
        await ctx.send("Вы должны быть в голосовом канале, чтобы изменить его лимит.")
        return

    if not 0 <= limit <= 99:
        await ctx.send("Лимит участников должен быть от 0 до 99, где 0 — без ограничений.")
        return

    channel = ctx.author.voice.channel
    owner_id = get_temp_voice_owner_for_channel(ctx.guild.id, channel.id)
    if owner_id != str(ctx.author.id):
        await ctx.send("Эту команду можно использовать только для канала, который вы создали.")
        return

    if not ctx.guild.me.guild_permissions.manage_channels:
        await ctx.send("Боту нужны права управления каналами.")
        return

    await channel.edit(user_limit=limit)
    if limit == 0:
        await ctx.send("Лимит участников снят.")
    else:
        await ctx.send(f"Лимит участников установлен: {limit}")


@bot.command(name="voiceinfo")
async def voiceinfo(ctx):
    if ctx.guild is None:
        await ctx.send("Эту команду можно использовать только на сервере.")
        return

    if ctx.author.voice is None or ctx.author.voice.channel is None:
        await ctx.send("Вы должны быть в голосовом канале, чтобы посмотреть его параметры.")
        return

    channel = ctx.author.voice.channel
    owner_id = get_temp_voice_owner_for_channel(ctx.guild.id, channel.id)
    if owner_id != str(ctx.author.id):
        await ctx.send("Эту команду можно использовать только для канала, который вы создали.")
        return

    limit_text = "без ограничений" if channel.user_limit == 0 else str(channel.user_limit)
    await ctx.send(
        f"Канал: {channel.mention}\n"
        f"Лимит участников: {limit_text}\n"
        f"Битрейт: {channel.bitrate // 1000} kbps"
    )


def resolve_role(guild, role_spec):
    try:
        role_id = int(role_spec)
    except ValueError:
        return discord.utils.get(guild.roles, name=role_spec)
    return guild.get_role(role_id)


async def handle_reaction(payload, add_role: bool):
    if not REACTION_ROLE_CONFIG:
        return

    channel_id, mapping = REACTION_ROLE_CONFIG
    if payload.channel_id != channel_id:
        return

    if payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    try:
        member = await guild.fetch_member(payload.user_id)
    except discord.NotFound:
        return

    emoji_keys = {payload.emoji.name}
    if getattr(payload.emoji, "id", None) is not None:
        emoji_keys.add(str(payload.emoji.id))
        emoji_keys.add(f"<:{payload.emoji.name}:{payload.emoji.id}>")

    role_spec = None
    for emoji_key in emoji_keys:
        if emoji_key in mapping:
            role_spec = mapping[emoji_key]
            break

    if not role_spec:
        return

    role = resolve_role(guild, role_spec)
    if role is None:
        print(f"Role not found for spec: {role_spec}")
        return

    if not guild.me.guild_permissions.manage_roles:
        print("Bot lacks permission to manage roles")
        return

    if role >= guild.me.top_role:
        print(f"Cannot manage role {role.name}: it is above the bot's highest role")
        return

    try:
        if add_role:
            await member.add_roles(role, reason="Reaction role")
        else:
            await member.remove_roles(role, reason="Reaction role")
    except discord.Forbidden as exc:
        print(f"Cannot {'assign' if add_role else 'remove'} role {role.name}: {exc}")


@bot.event
async def on_raw_reaction_add(payload):
    await handle_reaction(payload, add_role=True)


@bot.event
async def on_raw_reaction_remove(payload):
    await handle_reaction(payload, add_role=False)


@bot.event
async def cleanup_empty_temp_voice_channel(guild, channel):
    if guild is None or channel is None:
        return

    if not is_temp_voice_managed_channel(guild.id, channel.id):
        return

    try:
        if len(channel.members) > 0:
            return
    except Exception:
        return

    try:
        await channel.delete(reason="Empty temporary voice channel")
        remove_temp_voice_owned_channel(guild.id, channel.id)
    except discord.NotFound:
        remove_temp_voice_owned_channel(guild.id, channel.id)
        return
    except discord.Forbidden:
        return


async def schedule_temp_voice_cleanup(guild, channel):
    await asyncio.sleep(get_temp_voice_cleanup_timeout())
    await cleanup_empty_temp_voice_channel(guild, channel)


@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot or before.channel == after.channel:
        return

    guild = member.guild
    if guild is None:
        return

    guild_config = get_temp_voice_config(guild.id)
    monitor_channel_id = guild_config.get("monitor_channel_id")
    if not monitor_channel_id:
        return

    try:
        monitor_channel_id = int(monitor_channel_id)
    except (TypeError, ValueError):
        return

    if after.channel is not None and after.channel.id == monitor_channel_id:
        if not guild.me.guild_permissions.manage_channels:
            return

        category = after.channel.category
        channel_name = f"🎧 {member.display_name}"
        if len(channel_name) > 100:
            channel_name = channel_name[:100]

        created_channel = await guild.create_voice_channel(
            name=channel_name,
            category=category,
            reason=f"Temporary voice channel for {member}",
        )

        update_temp_voice_owned_channel(guild.id, created_channel.id, member.id)
        default_text_channel_id = get_temp_voice_default_text_channel_id(guild.id)
        if default_text_channel_id is not None:
            set_temp_voice_text_channel_id(guild.id, created_channel.id, default_text_channel_id)
        await member.move_to(created_channel, reason="Temporary voice channel")
        await send_temp_voice_help_message(guild, created_channel, member)
        asyncio.create_task(schedule_temp_voice_cleanup(guild, created_channel))
        return

    if before.channel is None:
        return

    if before.channel.id == monitor_channel_id:
        return

    if not is_temp_voice_managed_channel(guild.id, before.channel.id):
        return

    owner_id = get_temp_voice_owner_for_channel(guild.id, before.channel.id)
    if owner_id is None:
        return

    if len(before.channel.members) == 0:
        asyncio.create_task(schedule_temp_voice_cleanup(guild, before.channel))


if __name__ == "__main__":
    bot.run(TOKEN)
