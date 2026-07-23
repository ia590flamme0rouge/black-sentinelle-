"""
cogs/config_cog.py — Commandes de configuration du bot par serveur
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import COLORS, DEFAULT_SANCTION_THRESHOLDS, INFRACTION_POINT_EXPIRY_DAYS
from utils.checks import is_mod, requires_permission
from utils.embeds import error_embed, success_embed, info_embed
from utils.helpers import parse_duration, minutes_to_str

log = logging.getLogger(__name__)


class Config(commands.Cog):
    """Commandes de configuration du bot de modération."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ─────────────────────────────────────────────────────────────────────
    #  /config — Groupe principal
    # ─────────────────────────────────────────────────────────────────────

    config_group = app_commands.Group(
        name="config", description="Configuration du bot de modération"
    )

    # ── Logs ──────────────────────────────────────────────────────────────

    @config_group.command(name="logs", description="Définir le salon de logs")
    @app_commands.describe(channel="Salon où envoyer les logs")
    @is_mod()
    @requires_permission("manage_guild")
    async def config_logs(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        await self.db.set_guild_setting(interaction.guild.id, "log_channel_id", channel.id)
        await interaction.response.send_message(
            embed=success_embed(
                "Logs configurés",
                f"Les logs seront envoyés dans {channel.mention}.",
            )
        )

    # ── Rôles modérateur ──────────────────────────────────────────────────

    modrole_group = app_commands.Group(
        name="modrole",
        description="Gestion des rôles de modération",
        parent=None,
    )

    @config_group.command(name="modrole-add", description="Ajouter un rôle de modération")
    @app_commands.describe(role="Rôle à ajouter comme rôle modérateur")
    @is_mod()
    @requires_permission("manage_guild")
    async def config_modrole_add(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        current = await self.db.get_mod_roles(interaction.guild.id)
        if role.id in current:
            await interaction.response.send_message(
                embed=error_embed("Déjà ajouté", f"{role.mention} est déjà un rôle de modération."),
                ephemeral=True,
            )
            return
        current.append(role.id)
        await self.db.set_mod_roles(interaction.guild.id, current)
        await interaction.response.send_message(
            embed=success_embed("Rôle ajouté", f"{role.mention} peut maintenant utiliser le bot.")
        )

    @config_group.command(name="modrole-remove", description="Retirer un rôle de modération")
    @app_commands.describe(role="Rôle à retirer")
    @is_mod()
    @requires_permission("manage_guild")
    async def config_modrole_remove(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        current = await self.db.get_mod_roles(interaction.guild.id)
        if role.id not in current:
            await interaction.response.send_message(
                embed=error_embed("Introuvable", f"{role.mention} n'est pas un rôle de modération."),
                ephemeral=True,
            )
            return
        current.remove(role.id)
        await self.db.set_mod_roles(interaction.guild.id, current)
        await interaction.response.send_message(
            embed=success_embed("Rôle retiré", f"{role.mention} ne peut plus utiliser le bot.")
        )

    @config_group.command(name="modrole-list", description="Lister les rôles de modération")
    @is_mod()
    async def config_modrole_list(self, interaction: discord.Interaction) -> None:
        role_ids = await self.db.get_mod_roles(interaction.guild.id)
        if not role_ids:
            desc = "Aucun rôle configuré. Utilise les noms par défaut (Bot Manager, Modérateur, Admin)."
        else:
            roles = [interaction.guild.get_role(rid) for rid in role_ids]
            desc = "\n".join(r.mention if r else f"ID:{rid}" for r, rid in zip(roles, role_ids))

        await interaction.response.send_message(
            embed=info_embed("🛡️ Rôles de modération", desc),
            ephemeral=True,
        )

    # ── Bienvenue ──────────────────────────────────────────────────────────

    @config_group.command(name="welcome", description="Configurer le message de bienvenue")
    @app_commands.describe(
        channel="Salon de bienvenue",
        message="Message (variables : {user}, {guild}, {count})",
    )
    @is_mod()
    @requires_permission("manage_guild")
    async def config_welcome(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str = "Bienvenue {user} sur {guild} ! Vous êtes le membre n°{count} 🎉",
    ) -> None:
        await self.db.set_guild_setting(interaction.guild.id, "welcome_channel", channel.id)
        await self.db.set_guild_setting(interaction.guild.id, "welcome_message", message)
        await interaction.response.send_message(
            embed=success_embed(
                "Bienvenue configuré",
                f"Salon : {channel.mention}\nMessage : `{message}`",
            )
        )

    # ── AutoMod ────────────────────────────────────────────────────────────

    automod_group = app_commands.Group(
        name="automod", description="Configuration de l'automod", parent=None
    )

    @config_group.command(name="automod-spam", description="Configurer l'anti-spam")
    @app_commands.describe(
        enabled="Activer/désactiver",
        messages="Nombre de messages maximum",
        seconds="Fenêtre de temps en secondes",
    )
    @is_mod()
    @requires_permission("manage_guild")
    async def config_automod_spam(
        self,
        interaction: discord.Interaction,
        enabled: bool = True,
        messages: app_commands.Range[int, 2, 20] = 5,
        seconds: app_commands.Range[int, 1, 30] = 5,
    ) -> None:
        await self.db.set_automod_setting(interaction.guild.id, "anti_spam_enabled", int(enabled))
        await self.db.set_automod_setting(interaction.guild.id, "anti_spam_messages", messages)
        await self.db.set_automod_setting(interaction.guild.id, "anti_spam_seconds", seconds)
        await interaction.response.send_message(
            embed=success_embed(
                "Anti-spam configuré",
                f"{'✅ Activé' if enabled else '❌ Désactivé'} — Max **{messages}** messages en **{seconds}s**",
            )
        )

    @config_group.command(name="automod-raid", description="Configurer l'anti-raid")
    @app_commands.describe(
        enabled="Activer/désactiver",
        joins="Nombre d'arrivées déclenchant le lockdown",
        seconds="Fenêtre de temps en secondes",
        lockdown="Verrouiller le serveur automatiquement",
    )
    @is_mod()
    @requires_permission("manage_guild")
    async def config_automod_raid(
        self,
        interaction: discord.Interaction,
        enabled: bool = True,
        joins: app_commands.Range[int, 3, 50] = 10,
        seconds: app_commands.Range[int, 5, 60] = 10,
        lockdown: bool = True,
    ) -> None:
        await self.db.set_automod_setting(interaction.guild.id, "anti_raid_enabled", int(enabled))
        await self.db.set_automod_setting(interaction.guild.id, "anti_raid_joins", joins)
        await self.db.set_automod_setting(interaction.guild.id, "anti_raid_seconds", seconds)
        await self.db.set_automod_setting(interaction.guild.id, "anti_raid_lockdown", int(lockdown))
        await interaction.response.send_message(
            embed=success_embed(
                "Anti-raid configuré",
                f"{'✅ Activé' if enabled else '❌ Désactivé'} — **{joins}** arrivées en **{seconds}s** "
                f"{'→ Lockdown' if lockdown else '→ Log seulement'}",
            )
        )

    @config_group.command(name="automod-status", description="Afficher la configuration automod")
    @is_mod()
    async def config_automod_status(self, interaction: discord.Interaction) -> None:
        cfg = await self.db.get_automod_config(interaction.guild.id)

        def status(val: int) -> str:
            return "✅" if val else "❌"

        embed = discord.Embed(
            title="🤖 Configuration AutoMod",
            color=COLORS["info"],
        )
        embed.add_field(
            name="🔄 Anti-Spam",
            value=f"{status(cfg['anti_spam_enabled'])} {cfg['anti_spam_messages']} msgs/{cfg['anti_spam_seconds']}s",
            inline=True,
        )
        embed.add_field(
            name="🌊 Anti-Flood",
            value=f"{status(cfg['anti_flood_enabled'])} max {cfg['anti_flood_chars']} chars",
            inline=True,
        )
        embed.add_field(
            name="🚨 Anti-Raid",
            value=f"{status(cfg['anti_raid_enabled'])} {cfg['anti_raid_joins']} joins/{cfg['anti_raid_seconds']}s",
            inline=True,
        )
        embed.add_field(name="🔤 Filtre mots",    value=status(cfg["word_filter_enabled"]),    inline=True)
        embed.add_field(name="🔗 Filtre liens",   value=status(cfg["link_filter_enabled"]),    inline=True)
        embed.add_field(name="📨 Anti-invitations", value=status(cfg["invite_filter_enabled"]), inline=True)
        embed.add_field(name="😂 Anti-emoji spam", value=f"{status(cfg['emoji_spam_enabled'])} max {cfg['emoji_spam_max']}", inline=True)
        embed.add_field(name="@️ Anti-mention",   value=f"{status(cfg['mention_spam_enabled'])} max {cfg['mention_spam_max']}", inline=True)

        bad_words = cfg.get("bad_words", [])
        embed.add_field(
            name=f"🚫 Mots interdits ({len(bad_words)})",
            value=", ".join(f"`{w}`" for w in bad_words[:10]) or "*Aucun*",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Mots interdits ─────────────────────────────────────────────────────

    @config_group.command(name="badword-add", description="Ajouter un mot interdit")
    @app_commands.describe(word="Mot à interdire")
    @is_mod()
    @requires_permission("manage_guild")
    async def config_badword_add(self, interaction: discord.Interaction, word: str) -> None:
        await self.db.add_bad_word(interaction.guild.id, word.lower())
        await interaction.response.send_message(
            embed=success_embed("Mot ajouté", f"`{word}` a été ajouté à la liste noire."),
            ephemeral=True,
        )

    @config_group.command(name="badword-remove", description="Retirer un mot interdit")
    @app_commands.describe(word="Mot à retirer")
    @is_mod()
    @requires_permission("manage_guild")
    async def config_badword_remove(self, interaction: discord.Interaction, word: str) -> None:
        removed = await self.db.remove_bad_word(interaction.guild.id, word.lower())
        if removed:
            await interaction.response.send_message(
                embed=success_embed("Mot retiré", f"`{word}` a été retiré de la liste noire."),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=error_embed("Introuvable", f"`{word}` n'est pas dans la liste noire."),
                ephemeral=True,
            )

    # ── Sanctions progressives ──────────────────────────────────────────────

    sanction_group = app_commands.Group(
        name="sanctions", description="Configuration des sanctions progressives", parent=None
    )

    @config_group.command(name="sanctions-list", description="Afficher les seuils de sanctions")
    @is_mod()
    async def config_sanctions_list(self, interaction: discord.Interaction) -> None:
        thresholds = await self.db.get_sanction_thresholds(interaction.guild.id)
        embed = discord.Embed(
            title="⚡ Sanctions progressives",
            description=f"*Points expirent après {INFRACTION_POINT_EXPIRY_DAYS} jours*",
            color=COLORS["warn"],
        )
        if not thresholds:
            embed.description += "\n\nAucun seuil configuré."
        else:
            for t in thresholds:
                duration = minutes_to_str(t["duration_min"]) if t["duration_min"] > 0 else "Permanent"
                embed.add_field(
                    name=f"≥ {t['points']} points → {t['action'].upper()}",
                    value=f"Durée : **{duration}**\nRaison : {t['reason']}",
                    inline=True,
                )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config_group.command(name="sanctions-set", description="Définir un seuil de sanction")
    @app_commands.describe(
        points="Points déclenchant la sanction",
        action="Type de sanction",
        duration="Durée (ex: 1h, 1d) ou vide pour permanent",
        reason="Raison automatique",
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Mute (timeout)",    value="mute"),
        app_commands.Choice(name="Kick",              value="kick"),
        app_commands.Choice(name="Ban temporaire",    value="tempban"),
        app_commands.Choice(name="Ban permanent",     value="ban"),
    ])
    @is_mod()
    @requires_permission("manage_guild")
    async def config_sanctions_set(
        self,
        interaction: discord.Interaction,
        points: app_commands.Range[int, 1, 100],
        action: str,
        duration: Optional[str] = None,
        reason: str = "Seuil de sanctions atteint",
    ) -> None:
        td = parse_duration(duration) if duration else None
        duration_min = int(td.total_seconds() / 60) if td else 0

        await self.db.set_sanction_threshold(
            interaction.guild.id, points, action, duration_min, reason
        )
        duration_str = minutes_to_str(duration_min)
        await interaction.response.send_message(
            embed=success_embed(
                "Seuil configuré",
                f"**{points}+ points** → `{action.upper()}` ({duration_str})",
            )
        )

    @config_group.command(name="sanctions-delete", description="Supprimer un seuil de sanction")
    @app_commands.describe(points="Points du seuil à supprimer")
    @is_mod()
    @requires_permission("manage_guild")
    async def config_sanctions_delete(
        self, interaction: discord.Interaction, points: int
    ) -> None:
        await self.db.delete_sanction_threshold(interaction.guild.id, points)
        await interaction.response.send_message(
            embed=success_embed("Seuil supprimé", f"Le seuil à **{points} points** a été supprimé.")
        )

    # ── Whitelist AutoMod ───────────────────────────────────────────────────

    @config_group.command(name="whitelist-channel", description="Exclure un salon de l'automod")
    @app_commands.describe(channel="Salon à exclure", add="Ajouter ou retirer")
    @is_mod()
    @requires_permission("manage_guild")
    async def config_whitelist_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        add: bool = True,
    ) -> None:
        cfg = await self.db.get_automod_config(interaction.guild.id)
        wl = cfg.get("whitelisted_channels", [])
        if add:
            if channel.id not in wl:
                wl.append(channel.id)
            action = "ajouté à"
        else:
            wl = [c for c in wl if c != channel.id]
            action = "retiré de"
        await self.db.set_automod_setting(interaction.guild.id, "whitelisted_channels", wl)
        await interaction.response.send_message(
            embed=success_embed(
                "Whitelist mise à jour",
                f"{channel.mention} a été {action} la whitelist automod.",
            ),
            ephemeral=True,
        )

    # ── Vue d'ensemble config ───────────────────────────────────────────────

    @config_group.command(name="overview", description="Voir toute la configuration du serveur")
    @is_mod()
    async def config_overview(self, interaction: discord.Interaction) -> None:
        cfg = await self.db.get_guild_config(interaction.guild.id)

        log_ch = interaction.guild.get_channel(cfg.get("log_channel_id") or 0)
        welcome_ch = interaction.guild.get_channel(cfg.get("welcome_channel") or 0)
        autorole = interaction.guild.get_role(cfg.get("autorole_id") or 0)
        mod_roles = cfg.get("mod_roles", [])

        embed = discord.Embed(
            title=f"⚙️ Configuration — {interaction.guild.name}",
            color=COLORS["info"],
        )
        embed.add_field(name="📋 Salon logs",    value=log_ch.mention     if log_ch     else "*Non défini*", inline=True)
        embed.add_field(name="👋 Bienvenue",     value=welcome_ch.mention if welcome_ch else "*Non défini*", inline=True)
        embed.add_field(name="🎭 Autorole",      value=autorole.mention   if autorole   else "*Non défini*", inline=True)
        embed.add_field(
            name=f"🛡️ Rôles mod ({len(mod_roles)})",
            value="\n".join(
                r.mention for rid in mod_roles
                if (r := interaction.guild.get_role(rid))
            ) or "*Défaut (noms)*",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Config(bot))
