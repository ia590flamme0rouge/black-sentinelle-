"""
cogs/moderation.py — Commandes de modération complètes
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import COLORS, EMOJIS
from utils.checks import is_mod, requires_permission, check_hierarchy
from utils.embeds import mod_action_embed, success_embed, error_embed, infractions_list_embed
from utils.helpers import (
    parse_duration, format_duration, minutes_to_str,
    get_or_fetch_user, send_dm, log_to_channel,
)

log = logging.getLogger(__name__)


class Moderation(commands.Cog):
    """Commandes de modération : ban, kick, mute, warn, etc."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ─────────────────────────────────────────────────────────────────────
    #  /warn
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="warn", description="Avertir un membre")
    @app_commands.describe(
        member="Le membre à avertir",
        reason="Raison de l'avertissement",
        points="Points d'infraction à attribuer (défaut: 1)",
    )
    @is_mod()
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Aucune raison fournie",
        points: app_commands.Range[int, 1, 10] = 1,
    ) -> None:
        if not await check_hierarchy(interaction, member):
            return

        infraction_id = await self.db.add_infraction(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            infraction_type="warn",
            reason=reason,
            points=points,
        )
        total_points = await self.db.get_active_points(interaction.guild.id, member.id)

        embed = mod_action_embed(
            "Warn", member, interaction.user, reason,
            infraction_id=infraction_id, points=points, total_points=total_points,
        )
        await interaction.response.send_message(embed=embed)

        # DM à l'utilisateur
        dm_embed = error_embed(
            f"Avertissement — {interaction.guild.name}",
            f"Tu as reçu un avertissement.\n**Raison :** {reason}\n**Points totaux :** `{total_points}`",
        )
        await send_dm(member, dm_embed)

        # Log
        await log_to_channel(interaction.guild, self.db, embed)

        # Vérifier sanctions progressives
        await self._check_progressive_sanctions(interaction, member, total_points)

    async def _check_progressive_sanctions(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        total_points: int,
    ) -> None:
        """Applique les sanctions progressives selon les points accumulés."""
        thresholds = await self.db.get_sanction_thresholds(interaction.guild.id)
        # Prendre le seuil le plus élevé dont les points sont dépassés
        applicable = [t for t in thresholds if total_points >= t["points"]]
        if not applicable:
            return
        threshold = max(applicable, key=lambda t: t["points"])
        action = threshold["action"]
        duration = threshold["duration_min"]
        reason = threshold["reason"]

        if action == "mute" and duration > 0:
            try:
                td = timedelta(minutes=duration)
                await member.timeout(td, reason=reason)
                auto_embed = mod_action_embed(
                    "Mute", member, interaction.guild.me, reason,
                    duration=format_duration(td),
                )
                await interaction.followup.send(
                    f"⚡ **Sanction progressive déclenchée :** {member.mention} a été muté automatiquement.",
                    embed=auto_embed,
                )
                await log_to_channel(interaction.guild, self.db, auto_embed)
            except discord.HTTPException:
                pass

        elif action in ("ban", "tempban"):
            try:
                td = timedelta(minutes=duration) if duration > 0 else None
                await member.ban(reason=reason, delete_message_days=0)
                auto_embed = mod_action_embed(
                    "Ban", member, interaction.guild.me, reason,
                    duration=format_duration(td) if td else "Permanent",
                )
                await interaction.followup.send(
                    f"⚡ **Sanction progressive déclenchée :** {member.mention} a été banni automatiquement.",
                    embed=auto_embed,
                )
                await log_to_channel(interaction.guild, self.db, auto_embed)
                if td:
                    # Planifier le unban (stocké en DB pour redémarrage)
                    await self.db.add_infraction(
                        guild_id=interaction.guild.id,
                        user_id=member.id,
                        moderator_id=self.bot.user.id,
                        infraction_type="ban",
                        reason=reason,
                        duration_min=duration,
                    )
            except discord.HTTPException:
                pass

        elif action == "kick":
            try:
                await member.kick(reason=reason)
                auto_embed = mod_action_embed("Kick", member, interaction.guild.me, reason)
                await interaction.followup.send(
                    f"⚡ **Sanction progressive déclenchée :** {member.mention} a été expulsé automatiquement.",
                    embed=auto_embed,
                )
                await log_to_channel(interaction.guild, self.db, auto_embed)
            except discord.HTTPException:
                pass

    # ─────────────────────────────────────────────────────────────────────
    #  /unwarn
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="unwarn", description="Révoquer un avertissement")
    @app_commands.describe(
        infraction_id="ID de l'infraction à révoquer",
        reason="Raison de la révocation",
    )
    @is_mod()
    async def unwarn(
        self,
        interaction: discord.Interaction,
        infraction_id: int,
        reason: str = "Révoqué par un modérateur",
    ) -> None:
        infraction = await self.db.get_infraction_by_id(infraction_id)
        if not infraction or infraction["guild_id"] != interaction.guild.id:
            await interaction.response.send_message(
                embed=error_embed("Infraction introuvable", f"L'infraction `#{infraction_id}` n'existe pas."),
                ephemeral=True,
            )
            return
        if not infraction["active"]:
            await interaction.response.send_message(
                embed=error_embed("Déjà révoquée", "Cette infraction a déjà été révoquée."),
                ephemeral=True,
            )
            return

        await self.db.revoke_infraction(infraction_id)
        target = await get_or_fetch_user(self.bot, infraction["user_id"])
        embed = success_embed(
            "Infraction révoquée",
            f"L'infraction `#{infraction_id}` a été révoquée.\n**Raison :** {reason}",
        )
        if target:
            embed.add_field(name="👤 Membre", value=f"{target.mention}", inline=True)
        await interaction.response.send_message(embed=embed)
        await log_to_channel(interaction.guild, self.db, embed)

    # ─────────────────────────────────────────────────────────────────────
    #  /warnings
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="warnings", description="Afficher les infractions d'un membre")
    @app_commands.describe(member="Le membre à inspecter")
    @is_mod()
    async def warnings(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        infractions = await self.db.get_infractions(interaction.guild.id, member.id)
        total_points = await self.db.get_active_points(interaction.guild.id, member.id)
        embed = infractions_list_embed(member, infractions, total_points)
        await interaction.response.send_message(embed=embed, ephemeral=False)

    # ─────────────────────────────────────────────────────────────────────
    #  /kick
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="kick", description="Expulser un membre du serveur")
    @app_commands.describe(member="Le membre à expulser", reason="Raison de l'expulsion")
    @is_mod()
    @requires_permission("kick_members")
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Aucune raison fournie",
    ) -> None:
        if not await check_hierarchy(interaction, member):
            return

        dm_embed = error_embed(
            f"Expulsion — {interaction.guild.name}",
            f"Tu as été expulsé du serveur.\n**Raison :** {reason}",
        )
        await send_dm(member, dm_embed)

        await member.kick(reason=f"[{interaction.user}] {reason}")

        infraction_id = await self.db.add_infraction(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            infraction_type="kick",
            reason=reason,
            points=2,
        )
        embed = mod_action_embed("Kick", member, interaction.user, reason, infraction_id=infraction_id)
        await interaction.response.send_message(embed=embed)
        await log_to_channel(interaction.guild, self.db, embed)

    # ─────────────────────────────────────────────────────────────────────
    #  /ban
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="ban", description="Bannir un membre du serveur")
    @app_commands.describe(
        member="Le membre à bannir",
        reason="Raison du bannissement",
        duration="Durée du ban (ex: 1d, 12h, permanent si vide)",
        delete_days="Jours de messages à supprimer (0-7)",
    )
    @is_mod()
    @requires_permission("ban_members")
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Aucune raison fournie",
        duration: Optional[str] = None,
        delete_days: app_commands.Range[int, 0, 7] = 0,
    ) -> None:
        if not await check_hierarchy(interaction, member):
            return

        td = parse_duration(duration) if duration else None
        duration_str = format_duration(td) if td else "Permanent"
        duration_min = int(td.total_seconds() / 60) if td else 0

        dm_embed = error_embed(
            f"Bannissement — {interaction.guild.name}",
            f"Tu as été banni du serveur.\n**Raison :** {reason}\n**Durée :** {duration_str}",
        )
        await send_dm(member, dm_embed)

        await member.ban(reason=f"[{interaction.user}] {reason}", delete_message_days=delete_days)

        infraction_id = await self.db.add_infraction(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            infraction_type="ban",
            reason=reason,
            points=5,
            duration_min=duration_min,
        )
        embed = mod_action_embed(
            "Ban", member, interaction.user, reason,
            duration=duration_str, infraction_id=infraction_id,
        )
        await interaction.response.send_message(embed=embed)
        await log_to_channel(interaction.guild, self.db, embed)

    # ─────────────────────────────────────────────────────────────────────
    #  /unban
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="unban", description="Débannir un utilisateur")
    @app_commands.describe(user_id="ID de l'utilisateur à débannir", reason="Raison")
    @is_mod()
    @requires_permission("ban_members")
    async def unban(
        self,
        interaction: discord.Interaction,
        user_id: str,
        reason: str = "Aucune raison fournie",
    ) -> None:
        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("ID invalide", "Fournir un ID utilisateur valide."),
                ephemeral=True,
            )
            return

        try:
            ban_entry = await interaction.guild.fetch_ban(discord.Object(id=uid))
        except discord.NotFound:
            await interaction.response.send_message(
                embed=error_embed("Introuvable", "Cet utilisateur n'est pas banni."),
                ephemeral=True,
            )
            return

        await interaction.guild.unban(ban_entry.user, reason=f"[{interaction.user}] {reason}")
        await self.db.add_infraction(
            guild_id=interaction.guild.id,
            user_id=uid,
            moderator_id=interaction.user.id,
            infraction_type="unban",
            reason=reason,
        )
        embed = mod_action_embed("Unban", ban_entry.user, interaction.user, reason)
        await interaction.response.send_message(embed=embed)
        await log_to_channel(interaction.guild, self.db, embed)

    # ─────────────────────────────────────────────────────────────────────
    #  /softban
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="softban", description="Softban : ban + unban immédiat (purge messages)")
    @app_commands.describe(
        member="Le membre à softban",
        reason="Raison",
        delete_days="Jours de messages à supprimer (1-7)",
    )
    @is_mod()
    @requires_permission("ban_members")
    async def softban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Aucune raison fournie",
        delete_days: app_commands.Range[int, 1, 7] = 1,
    ) -> None:
        if not await check_hierarchy(interaction, member):
            return

        dm_embed = error_embed(
            f"Softban — {interaction.guild.name}",
            f"Tu as été softbanni (messages supprimés, tu peux revenir).\n**Raison :** {reason}",
        )
        await send_dm(member, dm_embed)

        await member.ban(reason=f"[Softban][{interaction.user}] {reason}", delete_message_days=delete_days)
        await interaction.guild.unban(member, reason="Softban — unban automatique")

        infraction_id = await self.db.add_infraction(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            infraction_type="kick",
            reason=f"Softban: {reason}",
            points=2,
        )
        embed = mod_action_embed("Softban", member, interaction.user, reason, infraction_id=infraction_id)
        await interaction.response.send_message(embed=embed)
        await log_to_channel(interaction.guild, self.db, embed)

    # ─────────────────────────────────────────────────────────────────────
    #  /mute
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="mute", description="Mettre un membre en timeout (silence)")
    @app_commands.describe(
        member="Le membre à mettre en silence",
        duration="Durée du mute (ex: 10m, 1h, 1d)",
        reason="Raison du mute",
    )
    @is_mod()
    @requires_permission("moderate_members")
    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str = "1h",
        reason: str = "Aucune raison fournie",
    ) -> None:
        if not await check_hierarchy(interaction, member):
            return

        td = parse_duration(duration)
        if not td:
            await interaction.response.send_message(
                embed=error_embed("Durée invalide", "Exemples valides : `10m`, `1h`, `1d`, `1h30m`"),
                ephemeral=True,
            )
            return

        # Discord timeout max = 28 jours
        if td.total_seconds() > 2419200:
            td = timedelta(days=28)

        await member.timeout(td, reason=f"[{interaction.user}] {reason}")

        duration_min = int(td.total_seconds() / 60)
        infraction_id = await self.db.add_infraction(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            infraction_type="mute",
            reason=reason,
            points=1,
            duration_min=duration_min,
        )
        embed = mod_action_embed(
            "Mute", member, interaction.user, reason,
            duration=format_duration(td), infraction_id=infraction_id,
        )
        await interaction.response.send_message(embed=embed)

        dm_embed = error_embed(
            f"Mute — {interaction.guild.name}",
            f"Tu as été mis en silence pour {format_duration(td)}.\n**Raison :** {reason}",
        )
        await send_dm(member, dm_embed)
        await log_to_channel(interaction.guild, self.db, embed)

    # ─────────────────────────────────────────────────────────────────────
    #  /unmute
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="unmute", description="Retirer le silence d'un membre")
    @app_commands.describe(member="Le membre à démuter", reason="Raison")
    @is_mod()
    @requires_permission("moderate_members")
    async def unmute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Mute levé",
    ) -> None:
        if member.timed_out_until is None:
            await interaction.response.send_message(
                embed=error_embed("Pas muté", "Ce membre n'est pas actuellement en timeout."),
                ephemeral=True,
            )
            return

        await member.timeout(None, reason=f"[{interaction.user}] {reason}")
        embed = mod_action_embed("Unban", member, interaction.user, reason)
        embed.title = f"{EMOJIS['success']} Démute"
        embed.color = COLORS["success"]
        await interaction.response.send_message(embed=embed)
        await log_to_channel(interaction.guild, self.db, embed)

    # ─────────────────────────────────────────────────────────────────────
    #  /purge
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="purge", description="Supprimer des messages en masse")
    @app_commands.describe(
        amount="Nombre de messages à supprimer (1-100)",
        member="Filtrer par membre (optionnel)",
    )
    @is_mod()
    @requires_permission("manage_messages")
    async def purge(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100],
        member: Optional[discord.Member] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        def check(msg: discord.Message) -> bool:
            return member is None or msg.author == member

        deleted = await interaction.channel.purge(limit=amount, check=check)
        count = len(deleted)

        embed = discord.Embed(
            title=f"{EMOJIS['trash']} Purge effectuée",
            description=f"`{count}` message(s) supprimé(s)" + (f" de **{member}**" if member else ""),
            color=COLORS["success"],
        )
        embed.add_field(name="👮 Modérateur", value=interaction.user.mention, inline=True)
        embed.add_field(name="📢 Salon", value=interaction.channel.mention, inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_to_channel(interaction.guild, self.db, embed)

    # ─────────────────────────────────────────────────────────────────────
    #  /slowmode
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="slowmode", description="Activer/désactiver le mode lent sur un salon")
    @app_commands.describe(
        seconds="Délai en secondes (0 = désactiver)",
        channel="Salon cible (défaut: salon actuel)",
    )
    @is_mod()
    @requires_permission("manage_channels")
    async def slowmode(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, 21600] = 0,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        target = channel or interaction.channel
        await target.edit(slowmode_delay=seconds)
        msg = f"Mode lent **désactivé** sur {target.mention}" if seconds == 0 \
              else f"Mode lent réglé à **{seconds}s** sur {target.mention}"
        embed = discord.Embed(description=f"🐢 {msg}", color=COLORS["info"])
        await interaction.response.send_message(embed=embed)

    # ─────────────────────────────────────────────────────────────────────
    #  /lock & /unlock
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="lock", description="Verrouiller un salon")
    @app_commands.describe(
        channel="Salon à verrouiller (défaut: actuel)",
        reason="Raison",
    )
    @is_mod()
    @requires_permission("manage_channels")
    async def lock(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        reason: str = "Verrouillage par un modérateur",
    ) -> None:
        target = channel or interaction.channel
        overwrite = target.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await target.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)

        embed = discord.Embed(
            description=f"🔒 **{target.mention} a été verrouillé.**\n**Raison :** {reason}",
            color=COLORS["mute"],
        )
        await interaction.response.send_message(embed=embed)
        await log_to_channel(interaction.guild, self.db, embed)

    @app_commands.command(name="unlock", description="Déverrouiller un salon")
    @app_commands.describe(
        channel="Salon à déverrouiller (défaut: actuel)",
        reason="Raison",
    )
    @is_mod()
    @requires_permission("manage_channels")
    async def unlock(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        reason: str = "Déverrouillage par un modérateur",
    ) -> None:
        target = channel or interaction.channel
        overwrite = target.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await target.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)

        embed = discord.Embed(
            description=f"🔓 **{target.mention} a été déverrouillé.**\n**Raison :** {reason}",
            color=COLORS["success"],
        )
        await interaction.response.send_message(embed=embed)
        await log_to_channel(interaction.guild, self.db, embed)

    # ─────────────────────────────────────────────────────────────────────
    #  /note
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="note", description="Ajouter une note interne sur un membre")
    @app_commands.describe(member="Le membre", note="La note à enregistrer")
    @is_mod()
    async def note(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        note: str,
    ) -> None:
        infraction_id = await self.db.add_infraction(
            guild_id=interaction.guild.id,
            user_id=member.id,
            moderator_id=interaction.user.id,
            infraction_type="note",
            reason=note,
            points=0,
        )
        embed = discord.Embed(
            title="📝 Note ajoutée",
            description=f"**Membre :** {member.mention}\n**Note :** {note}\n**ID :** `#{infraction_id}`",
            color=COLORS["info"],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ─────────────────────────────────────────────────────────────────────
    #  GESTION ERREURS
    # ─────────────────────────────────────────────────────────────────────

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if interaction.response.is_done():
            send = interaction.followup.send
        else:
            send = interaction.response.send_message

        if isinstance(error, app_commands.CheckFailure):
            return  # Géré par les checks eux-mêmes

        embed = error_embed("Erreur", f"Une erreur est survenue : `{error}`")
        await send(embed=embed, ephemeral=True)
        log.error("Erreur dans la commande de modération : %s", error, exc_info=error)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
