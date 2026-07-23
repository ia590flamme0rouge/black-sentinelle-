"""
cogs/logs.py — Système de logs automatiques complet
"""
from __future__ import annotations

import logging
from datetime import datetime

import discord
from discord.ext import commands

from config import COLORS, EMOJIS
from utils.embeds import (
    log_embed, member_join_embed, member_leave_embed,
    message_delete_embed, message_edit_embed,
)
from utils.helpers import log_to_channel, truncate

log = logging.getLogger(__name__)


class Logs(commands.Cog):
    """Capture et journalise tous les événements Discord importants."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ─────────────────────────────────────────────────────────────────────
    #  MESSAGES
    # ─────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        embed = message_delete_embed(message)
        await log_to_channel(message.guild, self.db, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not before.guild or before.author.bot:
            return
        if before.content == after.content:
            return  # Édition sans changement de texte (embed ajouté, etc.)
        embed = message_edit_embed(before, after)
        await log_to_channel(before.guild, self.db, embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]) -> None:
        if not messages:
            return
        guild = messages[0].guild
        if not guild:
            return
        embed = discord.Embed(
            title=f"{EMOJIS['trash']} Suppression en masse",
            description=f"**{len(messages)}** messages supprimés dans {messages[0].channel.mention}",
            color=COLORS["error"],
            timestamp=datetime.utcnow(),
        )
        await log_to_channel(guild, self.db, embed)

    # ─────────────────────────────────────────────────────────────────────
    #  MEMBRES
    # ─────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        embed = member_join_embed(member)
        await log_to_channel(member.guild, self.db, embed)

        # Message de bienvenue dans le salon configuré
        try:
            cfg = await self.db.get_guild_config(member.guild.id)
            welcome_channel_id = cfg.get("welcome_channel")
            welcome_msg = cfg.get("welcome_message", "Bienvenue {user} sur {guild} !")

            if welcome_channel_id:
                channel = member.guild.get_channel(welcome_channel_id)
                if channel:
                    formatted = welcome_msg.replace("{user}", member.mention) \
                                           .replace("{guild}", member.guild.name) \
                                           .replace("{count}", str(member.guild.member_count))
                    w_embed = discord.Embed(
                        description=formatted,
                        color=COLORS["join"],
                    )
                    w_embed.set_thumbnail(url=member.display_avatar.url)
                    await channel.send(embed=w_embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        embed = member_leave_embed(member)
        await log_to_channel(member.guild, self.db, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Logge les changements de rôles et de pseudonyme."""
        guild = before.guild

        # Changement de rôles
        added_roles   = [r for r in after.roles  if r not in before.roles]
        removed_roles = [r for r in before.roles if r not in after.roles]

        if added_roles or removed_roles:
            embed = discord.Embed(
                title="🎭 Rôles modifiés",
                color=COLORS["info"],
                timestamp=datetime.utcnow(),
            )
            embed.add_field(
                name="👤 Membre",
                value=f"{after.mention} (`{after}`)",
                inline=False,
            )
            if added_roles:
                embed.add_field(
                    name="✅ Rôles ajoutés",
                    value=", ".join(r.mention for r in added_roles),
                    inline=True,
                )
            if removed_roles:
                embed.add_field(
                    name="❌ Rôles retirés",
                    value=", ".join(r.mention for r in removed_roles),
                    inline=True,
                )
            embed.set_thumbnail(url=after.display_avatar.url)
            await log_to_channel(guild, self.db, embed)

        # Changement de pseudonyme
        if before.nick != after.nick:
            embed = discord.Embed(
                title="✏️ Pseudonyme modifié",
                color=COLORS["info"],
                timestamp=datetime.utcnow(),
            )
            embed.add_field(name="👤 Membre",  value=f"{after.mention}", inline=False)
            embed.add_field(name="📝 Avant",   value=before.nick or "*Aucun*",  inline=True)
            embed.add_field(name="📝 Après",   value=after.nick  or "*Aucun*",  inline=True)
            embed.set_thumbnail(url=after.display_avatar.url)
            await log_to_channel(guild, self.db, embed)

    # ─────────────────────────────────────────────────────────────────────
    #  SANCTIONS (bans/unbans via audit log)
    # ─────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        embed = discord.Embed(
            title=f"{EMOJIS['ban']} Membre banni",
            color=COLORS["ban"],
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="👤 Membre", value=f"{user.mention} (`{user}` | ID: `{user.id}`)", inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)

        # Tenter de récupérer la raison depuis l'audit log
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=1):
                if entry.target.id == user.id:
                    embed.add_field(name="👮 Modérateur", value=f"{entry.user.mention}", inline=True)
                    embed.add_field(name="📋 Raison",     value=entry.reason or "Aucune raison", inline=True)
                    break
        except discord.Forbidden:
            pass

        await log_to_channel(guild, self.db, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        embed = discord.Embed(
            title=f"{EMOJIS['unban']} Membre débanni",
            color=COLORS["unban"],
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="👤 Membre", value=f"{user.mention} (`{user}` | ID: `{user.id}`)", inline=False)
        embed.set_thumbnail(url=user.display_avatar.url)
        await log_to_channel(guild, self.db, embed)

    # ─────────────────────────────────────────────────────────────────────
    #  SALONS
    # ─────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        embed = discord.Embed(
            title="📢 Salon créé",
            description=f"**{channel.mention}** (`{channel.name}`) — type : `{channel.type}`",
            color=COLORS["success"],
            timestamp=datetime.utcnow(),
        )
        if channel.category:
            embed.add_field(name="📁 Catégorie", value=channel.category.name, inline=True)
        await log_to_channel(channel.guild, self.db, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        embed = discord.Embed(
            title=f"{EMOJIS['trash']} Salon supprimé",
            description=f"**#{channel.name}** (`{channel.id}`)",
            color=COLORS["error"],
            timestamp=datetime.utcnow(),
        )
        await log_to_channel(channel.guild, self.db, embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> None:
        changes = []
        if before.name != after.name:
            changes.append(f"**Nom :** `{before.name}` → `{after.name}`")
        if hasattr(before, "topic") and before.topic != after.topic:
            changes.append(f"**Sujet :** `{before.topic or 'Aucun'}` → `{after.topic or 'Aucun'}`")

        if not changes:
            return

        embed = discord.Embed(
            title="✏️ Salon modifié",
            description="\n".join(changes),
            color=COLORS["info"],
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="📢 Salon", value=after.mention if hasattr(after, "mention") else after.name, inline=True)
        await log_to_channel(after.guild, self.db, embed)

    # ─────────────────────────────────────────────────────────────────────
    #  RÔLES
    # ─────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        embed = discord.Embed(
            title="🎭 Rôle créé",
            description=f"**{role.mention}** (`{role.name}` | ID: `{role.id}`)",
            color=role.color.value or COLORS["success"],
            timestamp=datetime.utcnow(),
        )
        await log_to_channel(role.guild, self.db, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        embed = discord.Embed(
            title="🗑️ Rôle supprimé",
            description=f"**@{role.name}** (ID: `{role.id}`)",
            color=COLORS["error"],
            timestamp=datetime.utcnow(),
        )
        await log_to_channel(role.guild, self.db, embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        changes = []
        if before.name != after.name:
            changes.append(f"**Nom :** `{before.name}` → `{after.name}`")
        if before.color != after.color:
            changes.append(f"**Couleur :** `{before.color}` → `{after.color}`")
        if before.permissions != after.permissions:
            changes.append("**Permissions modifiées**")

        if not changes:
            return

        embed = discord.Embed(
            title="✏️ Rôle modifié",
            description="\n".join(changes),
            color=after.color.value or COLORS["info"],
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="🎭 Rôle", value=after.mention, inline=True)
        await log_to_channel(after.guild, self.db, embed)

    # ─────────────────────────────────────────────────────────────────────
    #  SERVEUR
    # ─────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        changes = []
        if before.name != after.name:
            changes.append(f"**Nom :** `{before.name}` → `{after.name}`")
        if before.verification_level != after.verification_level:
            changes.append(f"**Niveau vérification :** `{before.verification_level}` → `{after.verification_level}`")

        if not changes:
            return

        embed = discord.Embed(
            title="🏠 Serveur modifié",
            description="\n".join(changes),
            color=COLORS["info"],
            timestamp=datetime.utcnow(),
        )
        await log_to_channel(after, self.db, embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Logs(bot))
