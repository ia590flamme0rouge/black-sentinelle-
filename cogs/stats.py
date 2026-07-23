"""
cogs/stats.py — Statistiques d'activité et leaderboards
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import COLORS, EMOJIS
from utils.checks import is_mod
from utils.helpers import get_or_fetch_user, minutes_to_str

log = logging.getLogger(__name__)


class Stats(commands.Cog):
    """Statistiques d'activité, leaderboards et informations du serveur."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Suivi des sessions vocales : {(guild_id, user_id): join_timestamp}
        self._voice_sessions: dict[tuple, datetime] = {}
        self._flush_voice.start()

    def cog_unload(self) -> None:
        self._flush_voice.cancel()

    @property
    def db(self):
        return self.bot.db

    # ─────────────────────────────────────────────────────────────────────
    #  COMPTAGE DES MESSAGES
    # ─────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        await self.db.increment_messages(
            message.guild.id, message.author.id, len(message.content)
        )

    # ─────────────────────────────────────────────────────────────────────
    #  SUIVI VOCAL
    # ─────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        key = (member.guild.id, member.id)

        if before.channel is None and after.channel is not None:
            # Rejoint un salon vocal
            self._voice_sessions[key] = datetime.utcnow()

        elif before.channel is not None and after.channel is None:
            # Quitte un salon vocal
            if key in self._voice_sessions:
                joined_at = self._voice_sessions.pop(key)
                minutes = int((datetime.utcnow() - joined_at).total_seconds() / 60)
                if minutes > 0:
                    await self.db.increment_voice(member.guild.id, member.id, minutes)

    @tasks.loop(minutes=10)
    async def _flush_voice(self) -> None:
        """Enregistre les sessions vocales en cours toutes les 10min."""
        now = datetime.utcnow()
        for (guild_id, user_id), joined_at in list(self._voice_sessions.items()):
            minutes = int((now - joined_at).total_seconds() / 60)
            if minutes > 0:
                await self.db.increment_voice(guild_id, user_id, minutes)
                # Remettre à maintenant pour éviter le double-comptage
                self._voice_sessions[(guild_id, user_id)] = now

    # ─────────────────────────────────────────────────────────────────────
    #  /stats user
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="stats", description="Statistiques d'activité d'un membre")
    @app_commands.describe(member="Membre à inspecter (défaut : vous-même)")
    async def stats(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        target = member or interaction.user
        data = await self.db.get_user_stats(interaction.guild.id, target.id)
        infractions = await self.db.get_infractions(interaction.guild.id, target.id)
        total_points = await self.db.get_active_points(interaction.guild.id, target.id)

        embed = discord.Embed(
            title=f"📊 Statistiques — {target.display_name}",
            color=COLORS["stats"],
            timestamp=datetime.utcnow(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        if data:
            embed.add_field(name="💬 Messages",      value=f"`{data['messages_count']:,}`",  inline=True)
            embed.add_field(name="🎙️ Temps vocal",   value=f"`{minutes_to_str(data['voice_minutes'])}`", inline=True)
            embed.add_field(name="📝 Caractères",    value=f"`{data['chars_count']:,}`",     inline=True)
            embed.add_field(name="🕐 Dernière activité",
                            value=data["last_active"][:16] if data.get("last_active") else "Inconnu",
                            inline=True)
        else:
            embed.description = "Aucune activité enregistrée pour ce membre."

        embed.add_field(name="⚡ Points d'infraction", value=f"`{total_points}`",        inline=True)
        embed.add_field(name="📋 Total infractions",   value=f"`{len(infractions)}`",    inline=True)

        # Rôles
        roles = [r.mention for r in target.roles[1:]]
        if roles:
            roles_str = ", ".join(roles[:10])
            if len(roles) > 10:
                roles_str += f" +{len(roles) - 10}"
            embed.add_field(name="🎭 Rôles", value=roles_str, inline=False)

        # Infos générales
        created = discord.utils.format_dt(target.created_at, style="R")
        joined  = discord.utils.format_dt(target.joined_at, style="R") if target.joined_at else "Inconnu"
        embed.add_field(name="📅 Compte créé", value=created, inline=True)
        embed.add_field(name="📥 A rejoint",   value=joined,  inline=True)

        await interaction.response.send_message(embed=embed)

    # ─────────────────────────────────────────────────────────────────────
    #  /leaderboard
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="leaderboard", description="Classement d'activité du serveur")
    @app_commands.describe(category="Catégorie du classement")
    @app_commands.choices(category=[
        app_commands.Choice(name="💬 Messages",        value="messages_count"),
        app_commands.Choice(name="🎙️ Temps vocal",     value="voice_minutes"),
        app_commands.Choice(name="📋 Infractions",     value="infractions"),
    ])
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        category: str = "messages_count",
    ) -> None:
        await interaction.response.defer()

        if category == "infractions":
            data = await self.db.get_infraction_leaderboard(interaction.guild.id, limit=10)
        else:
            data = await self.db.get_leaderboard(interaction.guild.id, column=category, limit=10)

        title_map = {
            "messages_count": "💬 Top Messageurs",
            "voice_minutes":  "🎙️ Top Temps Vocal",
            "infractions":    "📋 Top Infractions",
        }
        embed = discord.Embed(
            title=f"🏆 {title_map.get(category, 'Classement')} — {interaction.guild.name}",
            color=COLORS["stats"],
            timestamp=datetime.utcnow(),
        )

        if not data:
            embed.description = "Aucune donnée disponible."
            await interaction.followup.send(embed=embed)
            return

        medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
        lines = []

        for i, row in enumerate(data):
            user = await get_or_fetch_user(self.bot, row["user_id"])
            name = user.display_name if user else f"ID:{row['user_id']}"
            medal = medals[i] if i < len(medals) else f"`{i+1}.`"

            if category == "infractions":
                value = f"{row['total_infractions']} infraction(s) • {row['total_points']} pts"
            elif category == "voice_minutes":
                value = minutes_to_str(row.get("voice_minutes", 0))
            else:
                value = f"{row.get('messages_count', 0):,} messages"

            lines.append(f"{medal} **{name}** — {value}")

        embed.description = "\n".join(lines)
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────
    #  /serverstats
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="serverstats", description="Statistiques globales du serveur")
    async def serverstats(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        await interaction.response.defer()

        total_members  = guild.member_count
        bots           = sum(1 for m in guild.members if m.bot)
        humans         = total_members - bots
        online         = sum(1 for m in guild.members if m.status != discord.Status.offline)
        text_channels  = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories     = len(guild.categories)
        roles          = len(guild.roles)
        boost_level    = guild.premium_tier
        boosts         = guild.premium_subscription_count

        embed = discord.Embed(
            title=f"🏠 Statistiques — {guild.name}",
            color=COLORS["stats"],
            timestamp=datetime.utcnow(),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="👥 Membres total",   value=f"`{total_members:,}`",  inline=True)
        embed.add_field(name="👤 Humains",         value=f"`{humans:,}`",          inline=True)
        embed.add_field(name="🤖 Bots",            value=f"`{bots:,}`",            inline=True)
        embed.add_field(name="🟢 En ligne",        value=f"`{online:,}`",          inline=True)
        embed.add_field(name="💬 Salons texte",    value=f"`{text_channels}`",     inline=True)
        embed.add_field(name="🎙️ Salons vocaux",   value=f"`{voice_channels}`",    inline=True)
        embed.add_field(name="📁 Catégories",      value=f"`{categories}`",        inline=True)
        embed.add_field(name="🎭 Rôles",           value=f"`{roles}`",             inline=True)
        embed.add_field(name="🚀 Niveau boost",    value=f"`{boost_level}` ({boosts} boosts)", inline=True)

        created = discord.utils.format_dt(guild.created_at, style="R")
        embed.add_field(name="📅 Créé",            value=created,                 inline=True)
        embed.add_field(name="👑 Propriétaire",    value=guild.owner.mention if guild.owner else "Inconnu", inline=True)
        embed.add_field(name="🆔 ID",              value=f"`{guild.id}`",         inline=True)

        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────
    #  /userinfo
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="userinfo", description="Informations détaillées sur un membre")
    @app_commands.describe(member="Membre à inspecter")
    async def userinfo(
        self, interaction: discord.Interaction, member: Optional[discord.Member] = None
    ) -> None:
        target = member or interaction.user
        created = discord.utils.format_dt(target.created_at, style="F")
        joined  = discord.utils.format_dt(target.joined_at, style="F") if target.joined_at else "Inconnu"

        embed = discord.Embed(
            title=f"👤 {target}",
            color=target.color if target.color.value else COLORS["info"],
            timestamp=datetime.utcnow(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="🆔 ID",              value=f"`{target.id}`",   inline=True)
        embed.add_field(name="🤖 Bot",             value="Oui" if target.bot else "Non", inline=True)
        embed.add_field(name="📅 Compte créé",     value=created,            inline=False)
        embed.add_field(name="📥 A rejoint",       value=joined,             inline=False)

        roles = [r.mention for r in target.roles[1:]]
        if roles:
            roles_str = ", ".join(roles[:15])
            if len(roles) > 15:
                roles_str += f" +{len(roles) - 15}"
            embed.add_field(name=f"🎭 Rôles ({len(roles)})", value=roles_str, inline=False)

        badges = []
        if target.public_flags.staff:           badges.append("🛡️ Staff Discord")
        if target.public_flags.partner:         badges.append("🤝 Partenaire")
        if target.public_flags.bug_hunter:      badges.append("🐛 Bug Hunter")
        if target.public_flags.early_supporter: badges.append("⭐ Early Supporter")
        if target.public_flags.verified_bot_developer: badges.append("🔧 Dev Bot")
        if badges:
            embed.add_field(name="🏅 Badges", value=" • ".join(badges), inline=False)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Stats(bot))
