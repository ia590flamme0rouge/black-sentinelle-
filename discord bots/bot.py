"""
bot.py — Point d'entrée principal du bot Discord de modération
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv

from config import DB_PATH
from database.db_manager import DatabaseManager

# ─────────────────────────────────────────────────────────────────────────────
#  CHARGEMENT DES VARIABLES D'ENVIRONNEMENT
# ─────────────────────────────────────────────────────────────────────────────

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()

TOKEN      = os.getenv("BOT_TOKEN", "")
TEST_GUILD = os.getenv("TEST_GUILD_ID", "")
LOG_LEVEL  = os.getenv("LOG_LEVEL", "INFO").upper()
PREFIX     = os.getenv("PREFIX", "!")

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION DES LOGS PYTHON
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("modbot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("modbot")

# Réduire le niveau de logs de discord.py
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("discord.http").setLevel(logging.WARNING)

# ─────────────────────────────────────────────────────────────────────────────
#  LISTE DES COGS À CHARGER
# ─────────────────────────────────────────────────────────────────────────────

COGS: list[str] = [
    "cogs.moderation",
    "cogs.automod",
    "cogs.logs",
    "cogs.tickets",
    "cogs.roles",
    "cogs.stats",
    "cogs.config_cog",
]

# ─────────────────────────────────────────────────────────────────────────────
#  BOT
# ─────────────────────────────────────────────────────────────────────────────

class ModerationBot(commands.Bot):
    """Bot de modération Discord — Multi-serveurs, commandes slash."""

    def __init__(self) -> None:
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=PREFIX,
            intents=intents,
            help_command=None,   # On utilise les slash commands
            case_insensitive=True,
        )
        self.db: Optional[DatabaseManager] = None
        self._test_guild = discord.Object(id=int(TEST_GUILD)) if TEST_GUILD else None

    # ─────────────────────────────────────────────────────────────────────
    #  SETUP HOOK — s'exécute avant la connexion
    # ─────────────────────────────────────────────────────────────────────

    async def setup_hook(self) -> None:
        # Initialiser la base de données
        self.db = await DatabaseManager.get_instance()
        log.info("Base de données initialisée.")

        # Charger tous les cogs
        failed: list[str] = []
        for cog in COGS:
            try:
                await self.load_extension(cog)
                log.info("✅ Cog chargé : %s", cog)
            except Exception as e:
                log.error("❌ Erreur chargement cog %s : %s", cog, e, exc_info=True)
                failed.append(cog)

        if failed:
            log.warning("Cogs en échec : %s", ", ".join(failed))

        # Synchroniser les commandes slash
        if self._test_guild:
            # Sync rapide sur le serveur de test
            self.tree.copy_global_to(guild=self._test_guild)
            synced = await self.tree.sync(guild=self._test_guild)
            log.info("Commandes slash synchronisées (guild) : %d", len(synced))
        else:
            # Sync globale (peut prendre jusqu'à 1h pour se propager)
            synced = await self.tree.sync()
            log.info("Commandes slash synchronisées (global) : %d", len(synced))

    # ─────────────────────────────────────────────────────────────────────
    #  ÉVÉNEMENTS
    # ─────────────────────────────────────────────────────────────────────

    async def on_ready(self) -> None:
        log.info("=" * 60)
        log.info("🤖 Bot connecté : %s (ID: %d)", self.user, self.user.id)
        log.info("📊 Serveurs     : %d", len(self.guilds))
        log.info("👥 Membres      : %d", sum(g.member_count or 0 for g in self.guilds))
        log.info("=" * 60)

        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} serveur(s) | /help",
            ),
            status=discord.Status.online,
        )

        # Initialiser les configs des serveurs existants
        for guild in self.guilds:
            try:
                await self.db.ensure_guild(guild.id)
            except Exception as e:
                log.error("Erreur ensure_guild pour %s : %s", guild.name, e)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Initialiser la config quand le bot rejoint un serveur."""
        await self.db.ensure_guild(guild.id)
        log.info("Rejoint le serveur : %s (ID: %d, membres: %d)",
                 guild.name, guild.id, guild.member_count or 0)

        # Trouver le premier salon où envoyer un message de bienvenue
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                embed = discord.Embed(
                    title="👋 Merci de m'avoir invité !",
                    description=(
                        "Bonjour ! Je suis votre bot de modération.\n\n"
                        "**Pour commencer :**\n"
                        "• `/config modrole-add @role` — Définir un rôle modérateur\n"
                        "• `/config logs #salon` — Définir le salon de logs\n"
                        "• `/config overview` — Voir la configuration\n"
                        "• `/ticket panel` — Déployer le panel de tickets\n\n"
                        "*Seuls les administrateurs peuvent configurer le bot au départ.*"
                    ),
                    color=0x5865F2,
                )
                await channel.send(embed=embed)
                break

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        log.info("Quitté le serveur : %s (ID: %d)", guild.name, guild.id)

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """Gestion globale des erreurs de commandes préfixées."""
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("❌ Permissions insuffisantes.", delete_after=10)
            return
        log.error("Erreur commande préfixée : %s", error, exc_info=error)

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        """Gestion globale des erreurs de commandes slash."""
        if isinstance(error, discord.app_commands.CheckFailure):
            return  # Géré par les checks individuels
        msg = f"❌ Erreur : `{str(error)[:200]}`"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass
        log.error("Erreur app command : %s", error, exc_info=error)

    async def close(self) -> None:
        """Fermeture propre du bot."""
        log.info("Arrêt du bot...")
        if self.db:
            await self.db.close()
        await super().close()


# ─────────────────────────────────────────────────────────────────────────────
#  COMMANDES PRÉFIXÉES DE BASE
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    bot = ModerationBot()

    # Commandes préfixées utilitaires (admin seulement)
    @bot.command(name="sync")
    @commands.is_owner()
    async def sync_commands(ctx: commands.Context, scope: str = "global") -> None:
        """Synchroniser les slash commands (owner seulement)."""
        if scope == "guild" and ctx.guild:
            bot.tree.copy_global_to(guild=ctx.guild)
            synced = await bot.tree.sync(guild=ctx.guild)
            await ctx.reply(f"✅ {len(synced)} commandes synchronisées sur ce serveur.")
        else:
            synced = await bot.tree.sync()
            await ctx.reply(f"✅ {len(synced)} commandes synchronisées globalement.")

    @bot.command(name="reload")
    @commands.is_owner()
    async def reload_cog(ctx: commands.Context, cog_name: str) -> None:
        """Recharger un cog (owner seulement)."""
        try:
            await bot.reload_extension(f"cogs.{cog_name}")
            await ctx.reply(f"✅ Cog `{cog_name}` rechargé.")
        except Exception as e:
            await ctx.reply(f"❌ Erreur : `{e}`")

    @bot.command(name="status")
    @commands.is_owner()
    async def bot_status(ctx: commands.Context) -> None:
        """Afficher l'état du bot."""
        embed = discord.Embed(title="📊 Statut du Bot", color=0x5865F2)
        embed.add_field(name="🏓 Latence",   value=f"`{round(bot.latency * 1000)}ms`", inline=True)
        embed.add_field(name="🌐 Serveurs",  value=f"`{len(bot.guilds)}`",              inline=True)
        embed.add_field(name="👥 Membres",   value=f"`{sum(g.member_count or 0 for g in bot.guilds)}`", inline=True)
        cogs_list = ", ".join(f"`{c}`" for c in bot.cogs)
        embed.add_field(name="🔧 Cogs actifs", value=cogs_list or "*Aucun*", inline=False)
        await ctx.reply(embed=embed)

    # Vérification du token
    if not TOKEN or TOKEN == "your_token_here":
        log.error("❌ ERREUR : BOT_TOKEN non défini dans le fichier .env !")
        log.error("   Éditez le fichier .env et ajoutez votre token Discord.")
        sys.exit(1)

    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Arrêt par l'utilisateur (Ctrl+C).")
    except Exception as e:
        log.critical("Erreur fatale : %s", e, exc_info=True)
        sys.exit(1)
