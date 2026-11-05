import asyncio
import os
from collections import deque
import discord
from discord.ext import commands
import certifi
from dotenv import load_dotenv
from service.config_service import get_authorized_user_ids, read_config_data, save_reaction_role_config, write_config_data
from service.role_service import handle_reaction, resolve_role, refresh_reaction_role_config
from service.voice_service import get_temp_voice_cleanup_timeout, set_temp_voice_default_text_channel_id, get_temp_voice_config, save_temp_voice_config, get_temp_voice_default_text_channel_id, get_temp_voice_owner_for_channel, remove_temp_voice_owned_channel, update_temp_voice_owned_channel, set_temp_voice_text_channel_id, send_temp_voice_help_message, is_temp_voice_managed_channel


os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Set DISCORD_TOKEN in environment before running")


REACTION_ROLE_CONFIG = refresh_reaction_role_config()


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
        if len(HELPED_HELP_QUEUE) == HELPED_HELP_QUEUE.maxlen:
            old_id = HELPED_HELP_QUEUE.popleft()
            HELPED_HELP_MESSAGES.discard(old_id)
        HELPED_HELP_MESSAGES.add(message_id)
        HELPED_HELP_QUEUE.append(message_id)

    config = read_config_data()
    public_help = config.get("HELP_TEXT_PUBLIC") or "Список доступных команд:\n!help"
    admin_help = config.get("HELP_TEXT") or public_help

    help_text = admin_help if is_authorized_user(ctx.author) else public_help
    await ctx.send(help_text)


@bot.command(name="setreactionchannel")
async def setreactionchannel(ctx, channel: discord.TextChannel):
    global REACTION_ROLE_CONFIG

    if not await ensure_reaction_management_access(ctx):
        return

    permissions = channel.permissions_for(ctx.guild.me)
    if not permissions.read_messages or not permissions.send_messages:
        await ctx.send("Боту нужны права на чтение и отправку сообщений в выбранном канале.")
        return

    save_reaction_role_config(channel_id=channel.id)
    REACTION_ROLE_CONFIG = refresh_reaction_role_config()
    await ctx.send(f"Канал реакционных ролей установлен: {channel.mention}")


@bot.command(name="addreactionrole")
async def addreactionrole(ctx, emoji: str, role: discord.Role):
    global REACTION_ROLE_CONFIG

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
    REACTION_ROLE_CONFIG = refresh_reaction_role_config()
    await ctx.send(f"Роль {role.mention} привязана к реакции {emoji}")


@bot.command(name="delreactionrole")
async def delreactionrole(ctx, emoji: str):
    global REACTION_ROLE_CONFIG

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
    REACTION_ROLE_CONFIG = refresh_reaction_role_config()
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


@bot.event
async def on_raw_reaction_add(payload):
    await handle_reaction(bot, payload, add_role=True)


@bot.event
async def on_raw_reaction_remove(payload):
    await handle_reaction(bot, payload, add_role=False)


@bot.event
async def cleanup_empty_temp_voice_channel(guild, channel):
    if guild is None or channel is None:
        return

    if not is_temp_voice_managed_channel(guild.id, channel.id):
        return

    if channel.members:
        return

    try:
        await channel.delete(reason="Empty temporary voice channel")
        remove_temp_voice_owned_channel(guild.id, channel.id)
    except discord.NotFound:
        remove_temp_voice_owned_channel(guild.id, channel.id)
        return
    except discord.Forbidden as exc:
        print(f"Cannot delete empty temporary voice channel {channel.id}: {exc}")
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
        if not guild.me.guild_permissions.move_members:
            print("Bot lacks permission to move members into temporary voice channels")
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
        asyncio.create_task(schedule_temp_voice_cleanup(guild, created_channel))
        default_text_channel_id = get_temp_voice_default_text_channel_id(guild.id)
        if default_text_channel_id is not None:
            set_temp_voice_text_channel_id(guild.id, created_channel.id, default_text_channel_id)
        await member.move_to(created_channel, reason="Temporary voice channel")
        await send_temp_voice_help_message(guild, created_channel, member)
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
