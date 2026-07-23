"""
cogs/automod.py — Anti-spam, anti-flood, anti-raid, filtres
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Optional

import discord
from discord.ext import commands, tasks

from config import COLORS, EMOJIS
from utils.embeds import error_embed, warning_embed
from utils.helpers import (
    count_emojis, extract_mentions, extract_urls,
    get_domain, is_discord_invite, log_to_channel,
)

log = logging.getLogger(__name__)


class AutoMod(commands.Cog):
    """AutoMod : anti-spam, anti-flood, anti-raid, filtres."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        # Cache pour l'anti-spam : {(guild_id, user_id): deque[timestamp]}
        self._message_cache: dict[tuple, deque] = defaultdict(lambda: deque())

        # Cache pour l'anti-raid : {guild_id: deque[timestamp]}
        self._join_cache: dict[int, deque] = defaultdict(lambda: deque())

        # Guilds en mode lockdown anti-raid
        self._raid_locked: set[int] = set()

        # Compteur de flood de caractères par auteur : {(guild_id, user_id): (count, reset_time)}
        self._flood_cache: dict[tuple, list] = defaultdict(lambda: [0, 0.0])

        # Nettoyage périodique des caches
        self._cleanup_task.start()

    def cog_unload(self) -> None:
        self._cleanup_task.cancel()

    @property
    def db(self):
        return self.bot.db

    # ─────────────────────────────────────────────────────────────────────
    #  NETTOYAGE CACHE PÉRIODIQUE
    # ─────────────────────────────────────────────────────────────────────

    @tasks.loop(minutes=5)
    async def _cleanup_task(self) -> None:
        now = time.monotonic()
        # Nettoyer les entrées spam vieilles de >60s
        for key in list(self._message_cache.keys()):
            dq = self._message_cache[key]
            while dq and (now - dq[0]) > 60:
                dq.popleft()
            if not dq:
                del self._message_cache[key]
        # Nettoyer les entrées raid vieilles de >60s
        for gid in list(self._join_cache.keys()):
            dq = self._join_cache[gid]
            while dq and (now - dq[0]) > 60:
                dq.popleft()

    # ─────────────────────────────────────────────────────────────────────
    #  VÉRIFICATION WHITELIST
    # ─────────────────────────────────────────────────────────────────────

    async def _is_whitelisted(self, message: discord.Message, cfg: dict) -> bool:
        """Vérifie si le message provient d'un salon/rôle whitelisté."""
        if message.channel.id in cfg.get("whitelisted_channels", []):
            return True
        member_role_ids = {r.id for r in message.author.roles}
        if member_role_ids.intersection(cfg.get("whitelisted_roles", [])):
            return True
        if message.author.guild_permissions.administrator:
            return True
        return False

    # ─────────────────────────────────────────────────────────────────────
    #  EVENT ON_MESSAGE
    # ─────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        cfg = await self.db.get_automod_config(message.guild.id)

        if await self._is_whitelisted(message, cfg):
            return

        # Lancer toutes les vérifications
        checks = [
            self._check_spam(message, cfg),
            self._check_flood(message, cfg),
            self._check_word_filter(message, cfg),
            self._check_link_filter(message, cfg),
            self._check_emoji_spam(message, cfg),
            self._check_mention_spam(message, cfg),
        ]
        results = await asyncio.gather(*checks, return_exceptions=True)

        # Si au moins une infraction détectée, on arrête (déjà géré dans chaque check)
        for r in results:
            if isinstance(r, Exception):
                log.error("AutoMod error: %s", r)

    # ─────────────────────────────────────────────────────────────────────
    #  ANTI-SPAM
    # ─────────────────────────────────────────────────────────────────────

    async def _check_spam(self, message: discord.Message, cfg: dict) -> None:
        if not cfg.get("anti_spam_enabled"):
            return

        max_msgs = cfg.get("anti_spam_messages", 5)
        window   = cfg.get("anti_spam_seconds", 5)
        key      = (message.guild.id, message.author.id)
        now      = time.monotonic()
        dq       = self._message_cache[key]

        dq.append(now)
        # Supprimer les anciens messages hors fenêtre
        while dq and (now - dq[0]) > window:
            dq.popleft()

        if len(dq) >= max_msgs:
            await self._punish(
                message,
                reason=f"Anti-spam : {len(dq)} messages en {window}s",
                delete=True,
                mute_minutes=5,
                warn_points=1,
            )
            dq.clear()

    # ─────────────────────────────────────────────────────────────────────
    #  ANTI-FLOOD (messages longs/répétitifs)
    # ─────────────────────────────────────────────────────────────────────

    async def _check_flood(self, message: discord.Message, cfg: dict) -> None:
        if not cfg.get("anti_flood_enabled"):
            return

        max_chars = cfg.get("anti_flood_chars", 500)
        if len(message.content) > max_chars:
            await self._punish(
                message,
                reason=f"Anti-flood : message trop long ({len(message.content)} caractères)",
                delete=True,
                mute_minutes=2,
                warn_points=1,
            )

    # ─────────────────────────────────────────────────────────────────────
    #  FILTRE DE MOTS
    # ─────────────────────────────────────────────────────────────────────

    async def _check_word_filter(self, message: discord.Message, cfg: dict) -> None:
        if not cfg.get("word_filter_enabled"):
            return

        bad_words = cfg.get("bad_words", [])
        if not bad_words:
            return

        content_lower = message.content.lower()
        for word in bad_words:
            # Cherche le mot (délimiteurs : espace, début/fin)
            pattern = r"(?<![a-zA-Z])" + re.escape(word) + r"(?![a-zA-Z])"
            if re.search(pattern, content_lower):
                await self._punish(
                    message,
                    reason=f"Mot interdit détecté : `{word}`",
                    delete=True,
                    warn_points=1,
                )
                return

    # ─────────────────────────────────────────────────────────────────────
    #  FILTRE DE LIENS
    # ─────────────────────────────────────────────────────────────────────

    async def _check_link_filter(self, message: discord.Message, cfg: dict) -> None:
        # Invitations Discord
        if cfg.get("invite_filter_enabled") and is_discord_invite(message.content):
            await self._punish(
                message,
                reason="Invitation Discord non autorisée",
                delete=True,
                warn_points=1,
            )
            return

        if not cfg.get("link_filter_enabled"):
            return

        blacklist = cfg.get("blacklisted_domains", [])
        if not blacklist:
            return

        urls = extract_urls(message.content)
        for url in urls:
            domain = get_domain(url)
            for bad_domain in blacklist:
                if domain == bad_domain or domain.endswith("." + bad_domain):
                    await self._punish(
                        message,
                        reason=f"Lien interdit : `{domain}`",
                        delete=True,
                        warn_points=2,
                    )
                    return

    # ─────────────────────────────────────────────────────────────────────
    #  ANTI-EMOJI SPAM
    # ─────────────────────────────────────────────────────────────────────

    async def _check_emoji_spam(self, message: discord.Message, cfg: dict) -> None:
        if not cfg.get("emoji_spam_enabled"):
            return

        max_emojis = cfg.get("emoji_spam_max", 15)
        count = count_emojis(message.content)
        if count > max_emojis:
            await self._punish(
                message,
                reason=f"Spam d'emojis : {count} emojis (max {max_emojis})",
                delete=True,
                warn_points=1,
            )

    # ─────────────────────────────────────────────────────────────────────
    #  ANTI-MENTION SPAM
    # ─────────────────────────────────────────────────────────────────────

    async def _check_mention_spam(self, message: discord.Message, cfg: dict) -> None:
        if not cfg.get("mention_spam_enabled"):
            return

        max_mentions = cfg.get("mention_spam_max", 5)
        mentions = len(extract_mentions(message.content))
        if mentions > max_mentions:
            await self._punish(
                message,
                reason=f"Spam de mentions : {mentions} mentions (max {max_mentions})",
                delete=True,
                mute_minutes=10,
                warn_points=2,
            )

    # ─────────────────────────────────────────────────────────────────────
    #  PUNITION AUTOMOD
    # ─────────────────────────────────────────────────────────────────────

    async def _punish(
        self,
        message: discord.Message,
        reason: str,
        delete: bool = True,
        mute_minutes: int = 0,
        warn_points: int = 1,
    ) -> None:
        member = message.author
        guild  = message.guild

        try:
            if delete:
                await message.delete()
        except discord.HTTPException:
            pass

        # Avertissement en MP
        try:
            embed = discord.Embed(
                title=f"⚠️ Avertissement AutoMod — {guild.name}",
                description=f"**Raison :** {reason}",
                color=COLORS["warning"],
            )
            await member.send(embed=embed)
        except discord.Forbidden:
            pass

        # Notifier dans le salon avec suppression automatique
        try:
            notify = await message.channel.send(
                embed=discord.Embed(
                    description=f"⚠️ {member.mention} — {reason}",
                    color=COLORS["warning"],
                ),
                delete_after=5,
            )
        except discord.HTTPException:
            pass

        # Ajouter infraction en DB
        try:
            infraction_id = await self.db.add_infraction(
                guild_id=guild.id,
                user_id=member.id,
                moderator_id=self.bot.user.id,
                infraction_type="warn",
                reason=f"[AutoMod] {reason}",
                points=warn_points,
            )

            # Mute si demandé
            if mute_minutes > 0:
                await member.timeout(
                    timedelta(minutes=mute_minutes),
                    reason=f"[AutoMod] {reason}",
                )
        except discord.HTTPException:
            pass
        except Exception as e:
            log.error("AutoMod punish error: %s", e)

        # Log
        try:
            log_embed = discord.Embed(
                title=f"🤖 AutoMod — Infraction détectée",
                description=f"**Membre :** {member.mention} (`{member}`)\n**Raison :** {reason}",
                color=COLORS["warning"],
            )
            log_embed.add_field(name="📢 Salon", value=message.channel.mention, inline=True)
            log_embed.add_field(name="⚡ Points", value=f"`+{warn_points}`", inline=True)
            await log_to_channel(guild, self.db, log_embed)
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────
    #  ANTI-RAID (on_member_join)
    # ─────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        cfg = await self.db.get_automod_config(guild.id)
        if not cfg.get("anti_raid_enabled"):
            return

        max_joins = cfg.get("anti_raid_joins", 10)
        window    = cfg.get("anti_raid_seconds", 10)
        now       = time.monotonic()
        dq        = self._join_cache[guild.id]

        dq.append(now)
        while dq and (now - dq[0]) > window:
            dq.popleft()

        if len(dq) >= max_joins and guild.id not in self._raid_locked:
            await self._trigger_raid_lockdown(guild, cfg, len(dq), window)

    async def _trigger_raid_lockdown(
        self, guild: discord.Guild, cfg: dict, joins: int, window: int
    ) -> None:
        self._raid_locked.add(guild.id)
        log.warning("RAID détecté sur %s (%d arrivées en %ds) — Lockdown activé", guild.name, joins, window)

        # Log dans le salon de modération
        embed = discord.Embed(
            title=f"🚨 RAID DÉTECTÉ — {guild.name}",
            description=(
                f"**{joins} membres** ont rejoint en **{window} secondes** !\n"
                "Le serveur est en mode lockdown."
            ),
            color=COLORS["ban"],
        )
        await log_to_channel(guild, self.db, embed)

        # Lockdown : désactiver les permissions d'envoi pour @everyone
        if cfg.get("anti_raid_lockdown"):
            for channel in guild.text_channels:
                try:
                    overwrite = channel.overwrites_for(guild.default_role)
                    overwrite.send_messages = False
                    await channel.set_permissions(
                        guild.default_role, overwrite=overwrite,
                        reason="Anti-raid : lockdown automatique",
                    )
                    await asyncio.sleep(0.3)  # Rate limit
                except discord.Forbidden:
                    continue

            # Relever le lockdown après 5 minutes
            await asyncio.sleep(300)
            await self._lift_raid_lockdown(guild)

    async def _lift_raid_lockdown(self, guild: discord.Guild) -> None:
        self._raid_locked.discard(guild.id)
        for channel in guild.text_channels:
            try:
                overwrite = channel.overwrites_for(guild.default_role)
                overwrite.send_messages = None  # Reset à la valeur par défaut
                await channel.set_permissions(
                    guild.default_role, overwrite=overwrite,
                    reason="Anti-raid : levée du lockdown",
                )
                await asyncio.sleep(0.3)
            except discord.Forbidden:
                continue

        embed = discord.Embed(
            title="✅ Lockdown levé",
            description="Le mode lockdown anti-raid a été automatiquement levé.",
            color=COLORS["success"],
        )
        await log_to_channel(guild, self.db, embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoMod(bot))
