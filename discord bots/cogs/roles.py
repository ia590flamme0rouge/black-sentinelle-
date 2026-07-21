"""
cogs/roles.py — Rôles automatiques et reaction roles
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import COLORS, EMOJIS
from utils.checks import is_mod
from utils.embeds import error_embed, success_embed

log = logging.getLogger(__name__)


class Roles(commands.Cog):
    """Gestion des rôles automatiques, bienvenue et reaction roles."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ─────────────────────────────────────────────────────────────────────
    #  AUTO-RÔLE À L'ARRIVÉE
    # ─────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Attribue automatiquement un rôle à l'arrivée si configuré."""
        try:
            cfg = await self.db.get_guild_config(member.guild.id)
            autorole_id = cfg.get("autorole_id")
            if autorole_id:
                role = member.guild.get_role(autorole_id)
                if role:
                    await member.add_roles(role, reason="Rôle automatique à l'arrivée")
        except Exception as e:
            log.error("Erreur autorole: %s", e)

    # ─────────────────────────────────────────────────────────────────────
    #  REACTION ROLES — Événements
    # ─────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self._handle_reaction(payload, add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self._handle_reaction(payload, add=False)

    async def _handle_reaction(
        self, payload: discord.RawReactionActionEvent, add: bool
    ) -> None:
        if payload.user_id == self.bot.user.id:
            return
        if not payload.guild_id:
            return

        emoji_str = str(payload.emoji)
        rr = await self.db.get_reaction_role(payload.message_id, emoji_str)
        if not rr:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member:
            return

        role = guild.get_role(rr["role_id"])
        if not role:
            return

        try:
            role_type = rr.get("role_type", "toggle")
            if add and role_type in ("toggle", "add_only"):
                await member.add_roles(role, reason="Reaction role")
            elif not add and role_type in ("toggle", "remove_only"):
                await member.remove_roles(role, reason="Reaction role retiré")
        except discord.HTTPException as e:
            log.error("Erreur reaction role: %s", e)

    # ─────────────────────────────────────────────────────────────────────
    #  COMMANDES SLASH — Autorole
    # ─────────────────────────────────────────────────────────────────────

    autorole_group = app_commands.Group(name="autorole", description="Gestion du rôle automatique")

    @autorole_group.command(name="set", description="Définir le rôle automatique à l'arrivée")
    @app_commands.describe(role="Rôle à attribuer automatiquement")
    @is_mod()
    async def autorole_set(self, interaction: discord.Interaction, role: discord.Role) -> None:
        await self.db.set_guild_setting(interaction.guild.id, "autorole_id", role.id)
        await interaction.response.send_message(
            embed=success_embed("Autorole défini", f"{role.mention} sera attribué à chaque nouveau membre.")
        )

    @autorole_group.command(name="remove", description="Supprimer le rôle automatique")
    @is_mod()
    async def autorole_remove(self, interaction: discord.Interaction) -> None:
        await self.db.set_guild_setting(interaction.guild.id, "autorole_id", None)
        await interaction.response.send_message(
            embed=success_embed("Autorole supprimé", "Aucun rôle ne sera plus attribué automatiquement.")
        )

    @autorole_group.command(name="status", description="Afficher le rôle automatique actuel")
    @is_mod()
    async def autorole_status(self, interaction: discord.Interaction) -> None:
        cfg = await self.db.get_guild_config(interaction.guild.id)
        role_id = cfg.get("autorole_id")
        if role_id:
            role = interaction.guild.get_role(role_id)
            desc = f"Rôle actuel : {role.mention if role else f'ID `{role_id}` (rôle introuvable)'}"
        else:
            desc = "Aucun rôle automatique configuré."
        await interaction.response.send_message(embed=success_embed("Autorole", desc), ephemeral=True)

    # ─────────────────────────────────────────────────────────────────────
    #  COMMANDES SLASH — Reaction Roles
    # ─────────────────────────────────────────────────────────────────────

    rr_group = app_commands.Group(name="reactionrole", description="Gestion des reaction roles")

    @rr_group.command(name="add", description="Ajouter un reaction role")
    @app_commands.describe(
        message_id="ID du message cible",
        channel="Salon contenant le message",
        emoji="Emoji de réaction (unicode ou :name:)",
        role="Rôle à attribuer",
        role_type="Type de reaction role",
    )
    @app_commands.choices(role_type=[
        app_commands.Choice(name="Toggle (ajouter/retirer)", value="toggle"),
        app_commands.Choice(name="Ajouter seulement",        value="add_only"),
        app_commands.Choice(name="Retirer seulement",        value="remove_only"),
    ])
    @is_mod()
    async def rr_add(
        self,
        interaction: discord.Interaction,
        message_id: str,
        channel: discord.TextChannel,
        emoji: str,
        role: discord.Role,
        role_type: str = "toggle",
    ) -> None:
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("ID invalide", "L'ID du message doit être un nombre."),
                ephemeral=True,
            )
            return

        # Vérifier que le message existe
        try:
            message = await channel.fetch_message(msg_id)
        except (discord.NotFound, discord.HTTPException):
            await interaction.response.send_message(
                embed=error_embed("Message introuvable", "Le message n'existe pas dans ce salon."),
                ephemeral=True,
            )
            return

        await self.db.add_reaction_role(
            interaction.guild.id, msg_id, channel.id, emoji, role.id, role_type
        )

        # Ajouter la réaction sur le message
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            pass

        await interaction.response.send_message(
            embed=success_embed(
                "Reaction Role ajouté",
                f"Réaction **{emoji}** → {role.mention} sur le [message]({message.jump_url}) ({role_type})",
            )
        )

    @rr_group.command(name="remove", description="Supprimer un reaction role")
    @app_commands.describe(
        message_id="ID du message",
        emoji="Emoji de la réaction à supprimer",
    )
    @is_mod()
    async def rr_remove(
        self,
        interaction: discord.Interaction,
        message_id: str,
        emoji: str,
    ) -> None:
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("ID invalide", "ID invalide."),
                ephemeral=True,
            )
            return

        await self.db.remove_reaction_role(msg_id, emoji)
        await interaction.response.send_message(
            embed=success_embed("Reaction Role supprimé", f"La réaction **{emoji}** a été supprimée.")
        )

    @rr_group.command(name="list", description="Lister les reaction roles d'un message")
    @app_commands.describe(message_id="ID du message")
    @is_mod()
    async def rr_list(self, interaction: discord.Interaction, message_id: str) -> None:
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.response.send_message(embed=error_embed("ID invalide", "ID invalide."), ephemeral=True)
            return

        rrs = await self.db.get_reaction_roles_for_message(msg_id)
        if not rrs:
            await interaction.response.send_message(
                embed=error_embed("Aucun", "Aucun reaction role pour ce message."),
                ephemeral=True,
            )
            return

        lines = []
        for rr in rrs:
            role = interaction.guild.get_role(rr["role_id"])
            role_display = role.mention if role else f"ID:{rr['role_id']}"
            lines.append(f"{rr['emoji']} → {role_display} ({rr['role_type']})")

        embed = discord.Embed(
            title=f"🎭 Reaction Roles — Message {msg_id}",
            description="\n".join(lines),
            color=COLORS["info"],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ─────────────────────────────────────────────────────────────────────
    #  /giverole — Attribution manuelle
    # ─────────────────────────────────────────────────────────────────────

    @app_commands.command(name="giverole", description="Attribuer un rôle à un membre")
    @app_commands.describe(member="Membre cible", role="Rôle à attribuer", reason="Raison")
    @is_mod()
    async def giverole(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
        reason: str = "Attribution manuelle",
    ) -> None:
        if role in member.roles:
            await interaction.response.send_message(
                embed=error_embed("Déjà attribué", f"{member.mention} possède déjà {role.mention}."),
                ephemeral=True,
            )
            return
        await member.add_roles(role, reason=f"[{interaction.user}] {reason}")
        await interaction.response.send_message(
            embed=success_embed("Rôle attribué", f"{role.mention} a été donné à {member.mention}.")
        )

    @app_commands.command(name="removerole", description="Retirer un rôle d'un membre")
    @app_commands.describe(member="Membre cible", role="Rôle à retirer", reason="Raison")
    @is_mod()
    async def removerole(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
        reason: str = "Retrait manuel",
    ) -> None:
        if role not in member.roles:
            await interaction.response.send_message(
                embed=error_embed("Non possédé", f"{member.mention} n'a pas {role.mention}."),
                ephemeral=True,
            )
            return
        await member.remove_roles(role, reason=f"[{interaction.user}] {reason}")
        await interaction.response.send_message(
            embed=success_embed("Rôle retiré", f"{role.mention} a été retiré à {member.mention}.")
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roles(bot))
