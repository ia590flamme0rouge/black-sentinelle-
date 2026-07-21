"""
utils/checks.py — Décorateurs et vérifications de permissions
"""
from __future__ import annotations

import logging
from functools import wraps
from typing import Callable

import discord
from discord import app_commands
from discord.ext import commands

from config import DEFAULT_MOD_ROLES, BOT_DEVELOPERS

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Vérification du rôle de modération (base de données + fallback config)
# ─────────────────────────────────────────────────────────────────────────────

async def _user_has_mod_role(member: discord.Member, db) -> bool:
    """Vérifie si un membre possède un rôle de modération ou est le développeur du bot."""
    # Développeurs du bot (Super-Admin permanent)
    if member.name.lower() in [dev.lower() for dev in BOT_DEVELOPERS]:
        return True

    if member.guild_permissions.administrator:
        return True  # Les admins ont toujours accès

    # Récupérer les rôle IDs depuis la base de données
    mod_role_ids = await db.get_mod_roles(member.guild.id)

    if mod_role_ids:
        member_role_ids = {r.id for r in member.roles}
        if member_role_ids.intersection(mod_role_ids):
            return True

    # Fallback : vérifier les noms de rôles par défaut
    member_role_names = {r.name for r in member.roles}
    for default_name in DEFAULT_MOD_ROLES:
        if default_name in member_role_names:
            return True

    return False


def is_mod():
    """
    Décorateur pour commandes slash — vérifie le rôle de modération.
    Utilise le gestionnaire de base de données attaché au bot.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        db = interaction.client.db
        has_role = await _user_has_mod_role(interaction.user, db)
        if not has_role:
            await interaction.response.send_message(
                "❌ **Accès refusé.** Tu n'as pas les permissions nécessaires pour utiliser cette commande.\n"
                "*Contacte un administrateur si tu penses que c'est une erreur.*",
                ephemeral=True,
            )
            return False
        return True

    return app_commands.check(predicate)


def is_mod_prefix():
    """
    Décorateur pour commandes avec préfixe — vérifie le rôle de modération.
    """
    async def predicate(ctx: commands.Context) -> bool:
        db = ctx.bot.db
        has_role = await _user_has_mod_role(ctx.author, db)
        if not has_role:
            await ctx.reply(
                "❌ **Accès refusé.** Tu n'as pas les permissions nécessaires pour utiliser cette commande.",
                delete_after=10,
            )
            return False
        return True

    return commands.check(predicate)


def requires_permission(*perms: str):
    """
    Décorateur supplémentaire pour vérifier les permissions Discord natives.
    Doit être combiné avec is_mod() pour les commandes sensibles.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        missing = []
        for perm in perms:
            if not getattr(interaction.user.guild_permissions, perm, False):
                missing.append(perm)
        if missing:
            perm_names = ", ".join(f"`{p}`" for p in missing)
            await interaction.response.send_message(
                f"❌ **Permissions Discord manquantes :** {perm_names}",
                ephemeral=True,
            )
            return False
        return True

    return app_commands.check(predicate)


def can_moderate_member():
    """
    Vérifie que le bot peut modérer la cible (hiérarchie des rôles).
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        # La cible est passée via les options de l'interaction
        # Cette vérification est faite manuellement dans les commandes
        return True

    return app_commands.check(predicate)


async def check_hierarchy(
    interaction: discord.Interaction, target: discord.Member
) -> bool:
    """
    Vérifie que l'auteur et le bot ont une hiérarchie suffisante pour modérer la cible.
    Envoie un message d'erreur si non.
    """
    guild = interaction.guild
    bot_member = guild.me

    # Le bot doit avoir un rôle plus haut que la cible
    if target.top_role >= bot_member.top_role:
        await interaction.response.send_message(
            f"❌ Je ne peux pas modérer **{target}** car son rôle est aussi haut ou plus haut que le mien.",
            ephemeral=True,
        )
        return False

    # L'auteur doit avoir un rôle plus haut que la cible (sauf admins)
    if (
        not interaction.user.guild_permissions.administrator
        and target.top_role >= interaction.user.top_role
    ):
        await interaction.response.send_message(
            f"❌ Tu ne peux pas modérer **{target}** car son rôle est aussi haut ou plus haut que le tien.",
            ephemeral=True,
        )
        return False

    # Ne pas modérer le propriétaire du serveur
    if target == guild.owner:
        await interaction.response.send_message(
            "❌ Impossible de modérer le propriétaire du serveur.",
            ephemeral=True,
        )
        return False

    # Ne pas se modérer soi-même
    if target == interaction.user:
        await interaction.response.send_message(
            "❌ Tu ne peux pas te modérer toi-même.",
            ephemeral=True,
        )
        return False

    return True
