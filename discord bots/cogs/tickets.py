"""
cogs/tickets.py — Système de tickets complet avec transcripts et boutons
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import COLORS, EMOJIS, MAX_TICKETS_PER_USER, TICKET_CATEGORY_NAME
from utils.checks import is_mod
from utils.embeds import error_embed, success_embed, ticket_open_embed, ticket_panel_embed
from utils.helpers import log_to_channel

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  VUE — Bouton "Ouvrir un ticket"
# ─────────────────────────────────────────────────────────────────────────────

class TicketOpenView(discord.ui.View):
    """Bouton persistant affiché dans le panel de tickets."""

    def __init__(self) -> None:
        super().__init__(timeout=None)  # Persistant entre redémarrages

    @discord.ui.button(
        label="Ouvrir un ticket",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="ticket:open",
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(TicketModal())


class TicketModal(discord.ui.Modal, title="Ouvrir un ticket"):
    """Modal pour recueillir le sujet du ticket."""

    subject = discord.ui.TextInput(
        label="Sujet",
        placeholder="Décrivez brièvement votre problème...",
        max_length=100,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        cog: Tickets = interaction.client.get_cog("Tickets")
        if cog:
            await cog.create_ticket(interaction, subject=str(self.subject))
        else:
            await interaction.response.send_message("❌ Erreur interne.", ephemeral=True)


# ─────────────────────────────────────────────────────────────────────────────
#  VUE — Boutons dans le salon du ticket
# ─────────────────────────────────────────────────────────────────────────────

class TicketControlView(discord.ui.View):
    """Boutons de contrôle dans un salon de ticket ouvert."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Fermer le ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="ticket:close",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        cog: Tickets = interaction.client.get_cog("Tickets")
        if cog:
            await cog.close_ticket_action(interaction)

    @discord.ui.button(
        label="Réclamer",
        style=discord.ButtonStyle.secondary,
        emoji="✋",
        custom_id="ticket:claim",
    )
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        cog: Tickets = interaction.client.get_cog("Tickets")
        if cog:
            await cog.claim_ticket_action(interaction)


# ─────────────────────────────────────────────────────────────────────────────
#  COG TICKETS
# ─────────────────────────────────────────────────────────────────────────────

class Tickets(commands.Cog):
    """Système de tickets de support."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Ajouter les vues persistantes
        bot.add_view(TicketOpenView())
        bot.add_view(TicketControlView())

    @property
    def db(self):
        return self.bot.db

    # ─────────────────────────────────────────────────────────────────────
    #  CRÉER UN TICKET
    # ─────────────────────────────────────────────────────────────────────

    async def create_ticket(
        self, interaction: discord.Interaction, subject: str = "Support"
    ) -> None:
        guild = interaction.guild
        member = interaction.user

        # Vérifier le nombre de tickets ouverts
        open_tickets = await self.db.get_user_open_tickets(guild.id, member.id)
        if len(open_tickets) >= MAX_TICKETS_PER_USER:
            await interaction.response.send_message(
                embed=error_embed(
                    "Trop de tickets",
                    f"Tu as déjà {len(open_tickets)} ticket(s) ouvert(s). Ferme-en un avant d'en ouvrir un nouveau.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Obtenir ou créer la catégorie
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if category is None:
            try:
                category = await guild.create_category(
                    TICKET_CATEGORY_NAME,
                    reason="Catégorie de tickets créée automatiquement",
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    embed=error_embed("Erreur", "Je n'ai pas la permission de créer des catégories."),
                    ephemeral=True,
                )
                return

        # Compter les tickets pour le numéro
        all_tickets = await self.db.get_user_open_tickets(guild.id, member.id)
        ticket_num = len(open_tickets) + 1

        # Créer le salon du ticket
        channel_name = f"ticket-{member.name}-{ticket_num}"
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True,
                manage_messages=True, read_message_history=True,
            ),
        }

        # Ajouter les rôles modérateurs
        mod_role_ids = await self.db.get_mod_roles(guild.id)
        for role_id in mod_role_ids:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True,
                    manage_messages=True,
                )

        try:
            channel = await category.create_text_channel(
                channel_name,
                overwrites=overwrites,
                topic=f"Ticket de {member} — Sujet: {subject}",
                reason=f"Ticket créé par {member}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed("Erreur", "Je n'ai pas la permission de créer des salons."),
                ephemeral=True,
            )
            return

        # Enregistrer en DB
        ticket_id = await self.db.create_ticket(guild.id, channel.id, member.id, subject)

        # Envoyer l'embed de bienvenue dans le ticket
        embed = ticket_open_embed(ticket_id, subject, member)
        await channel.send(
            content=f"{member.mention} — Votre ticket a été créé.",
            embed=embed,
            view=TicketControlView(),
        )

        await interaction.followup.send(
            embed=success_embed("Ticket créé !", f"Ton ticket a été créé : {channel.mention}"),
            ephemeral=True,
        )

        # Log
        log_embed = discord.Embed(
            title=f"{EMOJIS['ticket']} Ticket ouvert",
            description=f"**Membre :** {member.mention}\n**Salon :** {channel.mention}\n**Sujet :** {subject}",
            color=COLORS["ticket"],
            timestamp=datetime.utcnow(),
        )
        await log_to_channel(guild, self.db, log_embed)

    # ─────────────────────────────────────────────────────────────────────
    #  FERMER UN TICKET (bouton)
    # ─────────────────────────────────────────────────────────────────────

    async def close_ticket_action(self, interaction: discord.Interaction) -> None:
        ticket = await self.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message(
                embed=error_embed("Erreur", "Ce salon n'est pas un ticket."),
                ephemeral=True,
            )
            return

        if ticket["status"] != "open":
            await interaction.response.send_message(
                embed=error_embed("Ticket déjà fermé", "Ce ticket est déjà fermé."),
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        # Générer le transcript
        transcript = await self._generate_transcript(interaction.channel)

        # Fermer en DB
        await self.db.close_ticket(interaction.channel.id)

        # Notifier
        await interaction.channel.send(
            embed=discord.Embed(
                description="🔒 Ticket fermé. Ce salon sera supprimé dans 10 secondes.",
                color=COLORS["error"],
            )
        )

        # Log avec transcript
        owner = interaction.guild.get_member(ticket["owner_id"])
        owner_display = owner.mention if owner else f"ID:{ticket['owner_id']}"
        log_embed = discord.Embed(
            title=f"🔒 Ticket fermé",
            description=(
                f"**Propriétaire :** {owner_display}\n"
                f"**Fermé par :** {interaction.user.mention}\n"
                f"**Sujet :** {ticket['subject']}\n"
                f"**Créé le :** {ticket['created_at'][:10]}"
            ),
            color=COLORS["error"],
            timestamp=datetime.utcnow(),
        )
        if transcript:
            log_embed.add_field(name="📄 Transcript", value=f"```\n{transcript[:500]}\n```", inline=False)

        await log_to_channel(interaction.guild, self.db, log_embed)

        await asyncio.sleep(10)
        try:
            await interaction.channel.delete(reason=f"Ticket fermé par {interaction.user}")
        except discord.HTTPException:
            pass

    async def claim_ticket_action(self, interaction: discord.Interaction) -> None:
        """Un modérateur réclame un ticket."""
        ticket = await self.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message(embed=error_embed("Erreur", "Pas un ticket."), ephemeral=True)
            return

        # Vérifier que c'est un modérateur
        db = self.db
        from utils.checks import _user_has_mod_role
        if not await _user_has_mod_role(interaction.user, db):
            await interaction.response.send_message(
                embed=error_embed("Accès refusé", "Seuls les modérateurs peuvent réclamer un ticket."),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            description=f"✋ **{interaction.user.mention}** a pris en charge ce ticket.",
            color=COLORS["ticket"],
        )
        await interaction.response.send_message(embed=embed)

    async def _generate_transcript(self, channel: discord.TextChannel) -> str:
        """Génère un transcript texte simple des messages du ticket."""
        lines = []
        try:
            async for msg in channel.history(limit=500, oldest_first=True):
                if msg.author.bot and not msg.embeds:
                    continue
                ts = msg.created_at.strftime("%Y-%m-%d %H:%M")
                content = msg.content or "[embed/media]"
                lines.append(f"[{ts}] {msg.author}: {content}")
        except discord.HTTPException:
            pass
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    #  COMMANDES SLASH
    # ─────────────────────────────────────────────────────────────────────

    ticket_group = app_commands.Group(name="ticket", description="Gestion des tickets")

    @ticket_group.command(name="create", description="Créer un nouveau ticket de support")
    @app_commands.describe(subject="Sujet de votre ticket")
    async def ticket_create(self, interaction: discord.Interaction, subject: str = "Support") -> None:
        await self.create_ticket(interaction, subject=subject)

    @ticket_group.command(name="close", description="Fermer ce ticket")
    async def ticket_close(self, interaction: discord.Interaction) -> None:
        await self.close_ticket_action(interaction)

    @ticket_group.command(name="add", description="Ajouter un membre à ce ticket")
    @app_commands.describe(member="Membre à ajouter")
    @is_mod()
    async def ticket_add(self, interaction: discord.Interaction, member: discord.Member) -> None:
        ticket = await self.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message(
                embed=error_embed("Erreur", "Ce salon n'est pas un ticket."),
                ephemeral=True,
            )
            return

        await interaction.channel.set_permissions(
            member,
            view_channel=True, send_messages=True, read_message_history=True,
            reason=f"Ajouté au ticket par {interaction.user}",
        )
        await self.db.add_ticket_member(ticket["id"], member.id)
        await interaction.response.send_message(
            embed=success_embed("Membre ajouté", f"{member.mention} a été ajouté à ce ticket.")
        )

    @ticket_group.command(name="remove", description="Retirer un membre de ce ticket")
    @app_commands.describe(member="Membre à retirer")
    @is_mod()
    async def ticket_remove(self, interaction: discord.Interaction, member: discord.Member) -> None:
        ticket = await self.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message(
                embed=error_embed("Erreur", "Ce salon n'est pas un ticket."),
                ephemeral=True,
            )
            return

        await interaction.channel.set_permissions(member, overwrite=None, reason="Retiré du ticket")
        await self.db.remove_ticket_member(ticket["id"], member.id)
        await interaction.response.send_message(
            embed=success_embed("Membre retiré", f"{member.mention} a été retiré de ce ticket.")
        )

    @ticket_group.command(name="panel", description="Afficher le panel d'ouverture de tickets")
    @app_commands.describe(channel="Salon où afficher le panel")
    @is_mod()
    async def ticket_panel(
        self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None
    ) -> None:
        target = channel or interaction.channel
        embed = ticket_panel_embed(interaction.guild)
        msg = await target.send(embed=embed, view=TicketOpenView())
        await self.db.save_ticket_panel(interaction.guild.id, target.id, msg.id)
        await interaction.response.send_message(
            embed=success_embed("Panel créé !", f"Panel de tickets affiché dans {target.mention}"),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tickets(bot))
