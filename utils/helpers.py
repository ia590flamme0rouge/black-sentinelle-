"""
utils/helpers.py — Fonctions utilitaires diverses
"""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Optional

import discord


# ─────────────────────────────────────────────────────────────────────────────
#  PARSING DE DURÉE
# ─────────────────────────────────────────────────────────────────────────────

DURATION_REGEX = re.compile(
    r"(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", re.IGNORECASE
)

def parse_duration(s: str) -> Optional[timedelta]:
    """
    Parse une durée humaine : "1d", "2h30m", "1w", "10m", etc.
    Retourne None si invalide.
    """
    s = s.strip().replace(" ", "")
    match = DURATION_REGEX.fullmatch(s)
    if not match or not any(match.groups()):
        return None
    weeks   = int(match.group(1) or 0)
    days    = int(match.group(2) or 0)
    hours   = int(match.group(3) or 0)
    minutes = int(match.group(4) or 0)
    seconds = int(match.group(5) or 0)
    total = timedelta(weeks=weeks, days=days, hours=hours, minutes=minutes, seconds=seconds)
    if total.total_seconds() <= 0:
        return None
    return total


def format_duration(td: timedelta) -> str:
    """Formate un timedelta en chaîne lisible."""
    total_seconds = int(td.total_seconds())
    weeks, remainder = divmod(total_seconds, 604800)
    days, remainder  = divmod(remainder, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if weeks:   parts.append(f"{weeks}s")
    if days:    parts.append(f"{days}j")
    if hours:   parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}min")
    if seconds and not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts) if parts else "0s"


def minutes_to_str(minutes: int) -> str:
    """Convertit des minutes en durée lisible."""
    if minutes <= 0:
        return "Permanent"
    return format_duration(timedelta(minutes=minutes))


# ─────────────────────────────────────────────────────────────────────────────
#  UTILITAIRES DISCORD
# ─────────────────────────────────────────────────────────────────────────────

async def get_or_fetch_user(bot: discord.Client, user_id: int) -> Optional[discord.User]:
    """Récupère un utilisateur depuis le cache ou via l'API."""
    user = bot.get_user(user_id)
    if user is None:
        try:
            user = await bot.fetch_user(user_id)
        except (discord.NotFound, discord.HTTPException):
            return None
    return user


async def get_or_fetch_member(guild: discord.Guild, user_id: int) -> Optional[discord.Member]:
    """Récupère un membre depuis le cache ou via l'API."""
    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except (discord.NotFound, discord.HTTPException):
            return None
    return member


async def get_or_create_log_channel(
    guild: discord.Guild, channel_name: str = "mod-logs"
) -> Optional[discord.TextChannel]:
    """Récupère ou crée le salon de logs."""
    existing = discord.utils.get(guild.text_channels, name=channel_name)
    if existing:
        return existing
    try:
        # Créer avec permissions restreintes (visible seulement par les admins)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, embed_links=True
            ),
        }
        return await guild.create_text_channel(
            channel_name,
            overwrites=overwrites,
            topic="📋 Logs du bot de modération",
        )
    except discord.Forbidden:
        return None


def extract_mentions(text: str) -> list[int]:
    """Extrait les IDs des mentions utilisateur d'un texte."""
    return [int(m) for m in re.findall(r"<@!?(\d+)>", text)]


def count_emojis(text: str) -> int:
    """Compte les emojis dans un texte (unicode + custom Discord)."""
    custom  = len(re.findall(r"<a?:\w+:\d+>", text))
    # Pattern Unicode simplifié pour les emojis courants
    unicode_pattern = re.compile(
        "[\U0001F300-\U0001F9FF\U00002700-\U000027BF\U0001FA00-\U0001FA9F]+",
        flags=re.UNICODE,
    )
    unicode_count = len(unicode_pattern.findall(text))
    return custom + unicode_count


def is_discord_invite(text: str) -> bool:
    """Détecte les liens d'invitation Discord."""
    return bool(
        re.search(r"discord\.gg/\w+|discord\.com/invite/\w+|discordapp\.com/invite/\w+", text, re.I)
    )


def extract_urls(text: str) -> list[str]:
    """Extrait toutes les URLs d'un texte."""
    return re.findall(r"https?://[^\s<>\"]+", text)


def get_domain(url: str) -> str:
    """Extrait le domaine d'une URL."""
    match = re.search(r"https?://([^/?\s]+)", url)
    return match.group(1).lower() if match else ""


async def send_dm(
    user: discord.User | discord.Member, embed: discord.Embed
) -> bool:
    """Tente d'envoyer un DM à un utilisateur. Retourne True si succès."""
    try:
        await user.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


def truncate(text: str, max_len: int = 1024) -> str:
    """Tronque un texte à une longueur maximale."""
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


async def log_to_channel(
    guild: discord.Guild,
    db,
    embed: discord.Embed,
) -> None:
    """Envoie un embed dans le salon de logs configuré."""
    try:
        cfg = await db.get_guild_config(guild.id)
        log_channel_id = cfg.get("log_channel_id")
        if log_channel_id:
            channel = guild.get_channel(log_channel_id)
        else:
            channel = await get_or_create_log_channel(guild)
            if channel:
                await db.set_guild_setting(guild.id, "log_channel_id", channel.id)

        if channel and isinstance(channel, discord.TextChannel):
            await channel.send(embed=embed)
    except Exception:
        pass  # Silencieux — les logs ne doivent pas crash le bot
