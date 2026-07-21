"""
utils/embeds.py — Générateurs d'embeds Discord réutilisables
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import discord

from config import COLORS, EMOJIS


def _base_embed(
    title: str,
    description: str = "",
    color: int = COLORS["info"],
    timestamp: bool = True,
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.utcnow() if timestamp else None,
    )
    return embed


# ─────────────────────────────────────────────────────────────────────────────
#  EMBEDS DE MODÉRATION
# ─────────────────────────────────────────────────────────────────────────────

def mod_action_embed(
    action: str,
    target: discord.Member,
    moderator: discord.Member,
    reason: str,
    duration: Optional[str] = None,
    infraction_id: Optional[int] = None,
    points: Optional[int] = None,
    total_points: Optional[int] = None,
) -> discord.Embed:
    color_map = {
        "Ban": COLORS["ban"],
        "Kick": COLORS["kick"],
        "Mute": COLORS["mute"],
        "Warn": COLORS["warn"],
        "Unban": COLORS["unban"],
        "Unwarn": COLORS["success"],
        "Softban": COLORS["ban"],
        "TempBan": COLORS["ban"],
    }
    emoji_map = {
        "Ban": EMOJIS["ban"],
        "Kick": EMOJIS["kick"],
        "Mute": EMOJIS["mute"],
        "Warn": EMOJIS["warn"],
        "Unban": EMOJIS["unban"],
        "Unwarn": EMOJIS["success"],
        "Softban": EMOJIS["ban"],
        "TempBan": EMOJIS["ban"],
    }

    color = color_map.get(action, COLORS["info"])
    emoji = emoji_map.get(action, EMOJIS["shield"])

    embed = _base_embed(
        title=f"{emoji} {action}",
        color=color,
    )
    embed.add_field(name="👤 Membre", value=f"{target.mention} (`{target}` | ID: `{target.id}`)", inline=False)
    embed.add_field(name="👮 Modérateur", value=f"{moderator.mention}", inline=True)
    embed.add_field(name="📋 Raison", value=reason or "Aucune raison fournie", inline=False)

    if duration:
        embed.add_field(name="⏱️ Durée", value=duration, inline=True)
    if infraction_id:
        embed.add_field(name="🆔 ID Infraction", value=f"`#{infraction_id}`", inline=True)
    if points is not None:
        embed.add_field(name="⚡ Points ajoutés", value=f"`+{points}`", inline=True)
    if total_points is not None:
        embed.add_field(name="📊 Total points", value=f"`{total_points}`", inline=True)

    embed.set_thumbnail(url=target.display_avatar.url)
    return embed


def success_embed(title: str, description: str = "") -> discord.Embed:
    return _base_embed(f"{EMOJIS['success']} {title}", description, COLORS["success"])


def error_embed(title: str, description: str = "") -> discord.Embed:
    return _base_embed(f"{EMOJIS['error']} {title}", description, COLORS["error"])


def warning_embed(title: str, description: str = "") -> discord.Embed:
    return _base_embed(f"{EMOJIS['warning']} {title}", description, COLORS["warning"])


def info_embed(title: str, description: str = "") -> discord.Embed:
    return _base_embed(title, description, COLORS["info"])


# ─────────────────────────────────────────────────────────────────────────────
#  EMBEDS DE LOGS
# ─────────────────────────────────────────────────────────────────────────────

def log_embed(
    event: str,
    description: str = "",
    color: int = COLORS["log"],
    fields: Optional[list[tuple[str, str, bool]]] = None,
    thumbnail_url: Optional[str] = None,
) -> discord.Embed:
    embed = _base_embed(f"📋 {event}", description, color)
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    return embed


def message_delete_embed(message: discord.Message) -> discord.Embed:
    content = message.content or "*[Aucun texte — média/embed]*"
    if len(content) > 1024:
        content = content[:1021] + "..."
    embed = _base_embed(
        f"{EMOJIS['trash']} Message supprimé",
        color=COLORS["error"],
    )
    embed.add_field(name="👤 Auteur", value=f"{message.author.mention} (`{message.author}`)", inline=True)
    embed.add_field(name="📢 Salon", value=message.channel.mention, inline=True)
    embed.add_field(name="💬 Contenu", value=content, inline=False)
    embed.set_thumbnail(url=message.author.display_avatar.url)
    return embed


def message_edit_embed(before: discord.Message, after: discord.Message) -> discord.Embed:
    before_content = before.content or "*[vide]*"
    after_content  = after.content  or "*[vide]*"
    if len(before_content) > 512:
        before_content = before_content[:509] + "..."
    if len(after_content) > 512:
        after_content  = after_content[:509]  + "..."
    embed = _base_embed("✏️ Message modifié", color=COLORS["warning"])
    embed.add_field(name="👤 Auteur", value=f"{before.author.mention} (`{before.author}`)", inline=True)
    embed.add_field(name="📢 Salon",  value=before.channel.mention, inline=True)
    embed.add_field(name="📝 Avant",  value=before_content, inline=False)
    embed.add_field(name="📝 Après",  value=after_content,  inline=False)
    embed.add_field(name="🔗 Lien",   value=f"[Aller au message]({after.jump_url})", inline=False)
    embed.set_thumbnail(url=before.author.display_avatar.url)
    return embed


def member_join_embed(member: discord.Member) -> discord.Embed:
    created_at = discord.utils.format_dt(member.created_at, style="R")
    embed = _base_embed(
        f"{EMOJIS['join']} Nouveau membre",
        color=COLORS["join"],
    )
    embed.add_field(name="👤 Membre",   value=f"{member.mention} (`{member}`)", inline=False)
    embed.add_field(name="🆔 ID",       value=f"`{member.id}`", inline=True)
    embed.add_field(name="📅 Compte créé", value=created_at, inline=True)
    embed.add_field(name="📊 Membres", value=f"`{member.guild.member_count}`", inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    return embed


def member_leave_embed(member: discord.Member) -> discord.Embed:
    roles = [r.mention for r in member.roles[1:]]  # Exclure @everyone
    roles_str = ", ".join(roles) if roles else "*Aucun*"
    if len(roles_str) > 512:
        roles_str = roles_str[:509] + "..."
    embed = _base_embed(
        f"{EMOJIS['leave']} Membre parti",
        color=COLORS["leave"],
    )
    embed.add_field(name="👤 Membre",  value=f"{member.mention} (`{member}`)", inline=False)
    embed.add_field(name="🆔 ID",      value=f"`{member.id}`", inline=True)
    embed.add_field(name="📊 Membres", value=f"`{member.guild.member_count}`", inline=True)
    embed.add_field(name="🎭 Rôles",   value=roles_str, inline=False)
    embed.set_thumbnail(url=member.display_avatar.url)
    return embed


# ─────────────────────────────────────────────────────────────────────────────
#  EMBEDS TICKETS
# ─────────────────────────────────────────────────────────────────────────────

def ticket_open_embed(ticket_id: int, subject: str, owner: discord.Member) -> discord.Embed:
    embed = _base_embed(
        f"{EMOJIS['ticket']} Ticket #{ticket_id} — {subject}",
        description=(
            "Bienvenue dans votre ticket ! Décrivez votre problème et un modérateur vous répondra dès que possible.\n\n"
            "• Utilisez `/ticket close` pour fermer ce ticket.\n"
            "• Utilisez `/ticket add @membre` pour ajouter quelqu'un."
        ),
        color=COLORS["ticket"],
    )
    embed.add_field(name="👤 Ouvert par", value=owner.mention, inline=True)
    embed.add_field(name="📋 Sujet",      value=subject,        inline=True)
    embed.set_thumbnail(url=owner.display_avatar.url)
    return embed


def ticket_panel_embed(guild: discord.Guild) -> discord.Embed:
    embed = _base_embed(
        f"{EMOJIS['ticket']} Support — {guild.name}",
        description=(
            "Besoin d'aide ? Cliquez sur le bouton ci-dessous pour ouvrir un ticket.\n\n"
            "Un membre de l'équipe vous répondra dans les meilleurs délais."
        ),
        color=COLORS["ticket"],
        timestamp=False,
    )
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    return embed


# ─────────────────────────────────────────────────────────────────────────────
#  EMBEDS INFRACTIONS
# ─────────────────────────────────────────────────────────────────────────────

def infractions_list_embed(
    target: discord.User | discord.Member,
    infractions: list[dict],
    total_points: int,
) -> discord.Embed:
    embed = _base_embed(
        f"📋 Infractions de {target}",
        color=COLORS["warn"] if infractions else COLORS["success"],
    )
    embed.add_field(name="🆔 ID", value=f"`{target.id}`", inline=True)
    embed.add_field(name="⚡ Points actifs", value=f"`{total_points}`", inline=True)
    embed.add_field(name="📊 Total infractions", value=f"`{len(infractions)}`", inline=True)

    if not infractions:
        embed.description = "✅ Aucune infraction active pour ce membre."
    else:
        for i, inf in enumerate(infractions[:10], 1):
            value = (
                f"**Type:** {inf['infraction_type']}\n"
                f"**Raison:** {inf['reason']}\n"
                f"**Points:** `{inf['points']}`\n"
                f"**Date:** {inf['created_at'][:10]}"
            )
            embed.add_field(
                name=f"#{inf['id']} — {inf['infraction_type'].upper()}",
                value=value,
                inline=True,
            )
        if len(infractions) > 10:
            embed.set_footer(text=f"+{len(infractions) - 10} infractions supplémentaires")

    embed.set_thumbnail(url=target.display_avatar.url)
    return embed
