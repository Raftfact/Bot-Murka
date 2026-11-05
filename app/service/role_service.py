import discord
from .config_service import load_reaction_role_config


def refresh_reaction_role_config():
    global REACTION_ROLE_CONFIG
    try:
        REACTION_ROLE_CONFIG = load_reaction_role_config()
    except RuntimeError as exc:
        print(f"Reaction roles disabled: {exc}")
        REACTION_ROLE_CONFIG = None
    return REACTION_ROLE_CONFIG


def resolve_role(guild, role_spec):
    try:
        role_id = int(role_spec)
    except ValueError:
        return discord.utils.get(guild.roles, name=role_spec)
    return guild.get_role(role_id)


async def handle_reaction(bot, payload, add_role: bool):
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
        emoji_keys.add(f"<a:{payload.emoji.name}:{payload.emoji.id}>")

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