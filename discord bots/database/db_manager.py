"""
database/db_manager.py — Gestionnaire de base de données SQLite asynchrone
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import aiosqlite

from config import DB_PATH, DEFAULT_MOD_ROLES, DEFAULT_SANCTION_THRESHOLDS, INFRACTION_POINT_EXPIRY_DAYS
from database.models import CREATE_TABLES

log = logging.getLogger(__name__)


class DatabaseManager:
    """Singleton gérant toutes les interactions avec la base de données SQLite."""

    _instance: Optional["DatabaseManager"] = None

    def __init__(self) -> None:
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = cls()
            await cls._instance.connect()
        return cls._instance

    # ─────────────────────────────────────────────────────────────────────
    #  CONNEXION / INITIALISATION
    # ─────────────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(DB_PATH)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._create_tables()
        log.info("Base de données connectée : %s", DB_PATH)

    async def _create_tables(self) -> None:
        async with self._lock:
            for stmt in CREATE_TABLES:
                await self._db.execute(stmt)
            await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            log.info("Base de données fermée.")

    # ─────────────────────────────────────────────────────────────────────
    #  HELPERS INTERNES
    # ─────────────────────────────────────────────────────────────────────

    async def _fetchone(self, query: str, params: tuple = ()) -> Optional[aiosqlite.Row]:
        async with self._lock:
            async with self._db.execute(query, params) as cur:
                return await cur.fetchone()

    async def _fetchall(self, query: str, params: tuple = ()) -> list[aiosqlite.Row]:
        async with self._lock:
            async with self._db.execute(query, params) as cur:
                return await cur.fetchall()

    async def _execute(self, query: str, params: tuple = ()) -> int:
        async with self._lock:
            cur = await self._db.execute(query, params)
            await self._db.commit()
            return cur.lastrowid

    # ─────────────────────────────────────────────────────────────────────
    #  GUILDS — Configuration serveur
    # ─────────────────────────────────────────────────────────────────────

    async def ensure_guild(self, guild_id: int) -> None:
        """Crée la config du serveur si elle n'existe pas."""
        await self._execute(
            "INSERT OR IGNORE INTO guilds (guild_id) VALUES (?)", (guild_id,)
        )
        await self._execute(
            "INSERT OR IGNORE INTO automod_config (guild_id) VALUES (?)", (guild_id,)
        )
        # Insérer les seuils par défaut si absents
        existing = await self._fetchall(
            "SELECT points FROM sanction_thresholds WHERE guild_id=?", (guild_id,)
        )
        existing_pts = {row["points"] for row in existing}
        for thr in DEFAULT_SANCTION_THRESHOLDS:
            if thr["points"] not in existing_pts:
                await self._execute(
                    """INSERT OR IGNORE INTO sanction_thresholds
                       (guild_id, points, action, duration_min, reason)
                       VALUES (?,?,?,?,?)""",
                    (guild_id, thr["points"], thr["action"],
                     thr["duration_minutes"], thr["reason"]),
                )

    async def get_guild_config(self, guild_id: int) -> dict:
        row = await self._fetchone("SELECT * FROM guilds WHERE guild_id=?", (guild_id,))
        if row is None:
            await self.ensure_guild(guild_id)
            row = await self._fetchone("SELECT * FROM guilds WHERE guild_id=?", (guild_id,))
        d = dict(row)
        d["mod_roles"] = json.loads(d.get("mod_roles") or "[]")
        return d

    async def set_guild_setting(self, guild_id: int, key: str, value: Any) -> None:
        await self.ensure_guild(guild_id)
        if isinstance(value, (list, dict)):
            value = json.dumps(value)
        await self._execute(
            f"UPDATE guilds SET {key}=? WHERE guild_id=?", (value, guild_id)
        )

    async def get_mod_roles(self, guild_id: int) -> list[int]:
        cfg = await self.get_guild_config(guild_id)
        return cfg.get("mod_roles") or []

    async def set_mod_roles(self, guild_id: int, role_ids: list[int]) -> None:
        await self.set_guild_setting(guild_id, "mod_roles", role_ids)

    # ─────────────────────────────────────────────────────────────────────
    #  AUTOMOD — Configuration
    # ─────────────────────────────────────────────────────────────────────

    async def get_automod_config(self, guild_id: int) -> dict:
        await self.ensure_guild(guild_id)
        row = await self._fetchone(
            "SELECT * FROM automod_config WHERE guild_id=?", (guild_id,)
        )
        d = dict(row)
        d["bad_words"] = json.loads(d.get("bad_words") or "[]")
        d["blacklisted_domains"] = json.loads(d.get("blacklisted_domains") or "[]")
        d["whitelisted_channels"] = json.loads(d.get("whitelisted_channels") or "[]")
        d["whitelisted_roles"] = json.loads(d.get("whitelisted_roles") or "[]")
        return d

    async def set_automod_setting(self, guild_id: int, key: str, value: Any) -> None:
        await self.ensure_guild(guild_id)
        if isinstance(value, (list, dict)):
            value = json.dumps(value)
        await self._execute(
            f"UPDATE automod_config SET {key}=? WHERE guild_id=?", (value, guild_id)
        )

    async def add_bad_word(self, guild_id: int, word: str) -> None:
        cfg = await self.get_automod_config(guild_id)
        words = cfg["bad_words"]
        if word.lower() not in words:
            words.append(word.lower())
            await self.set_automod_setting(guild_id, "bad_words", words)

    async def remove_bad_word(self, guild_id: int, word: str) -> bool:
        cfg = await self.get_automod_config(guild_id)
        words = cfg["bad_words"]
        if word.lower() in words:
            words.remove(word.lower())
            await self.set_automod_setting(guild_id, "bad_words", words)
            return True
        return False

    # ─────────────────────────────────────────────────────────────────────
    #  INFRACTIONS
    # ─────────────────────────────────────────────────────────────────────

    async def add_infraction(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        infraction_type: str,
        reason: str = "Aucune raison fournie",
        points: int = 0,
        duration_min: int = 0,
    ) -> int:
        expires_at = None
        if duration_min > 0:
            expires_at = (datetime.utcnow() + timedelta(minutes=duration_min)).isoformat()

        infraction_id = await self._execute(
            """INSERT INTO infractions
               (guild_id, user_id, moderator_id, infraction_type, reason, points, duration_min, expires_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (guild_id, user_id, moderator_id, infraction_type, reason, points, duration_min, expires_at),
        )

        # Ajouter les points d'infraction
        if points > 0:
            pt_expires = (
                datetime.utcnow() + timedelta(days=INFRACTION_POINT_EXPIRY_DAYS)
            ).isoformat()
            await self._execute(
                """INSERT INTO infraction_points
                   (guild_id, user_id, infraction_id, points, expires_at)
                   VALUES (?,?,?,?,?)""",
                (guild_id, user_id, infraction_id, points, pt_expires),
            )
        return infraction_id

    async def get_infractions(self, guild_id: int, user_id: int) -> list[dict]:
        rows = await self._fetchall(
            """SELECT * FROM infractions
               WHERE guild_id=? AND user_id=? AND active=1
               ORDER BY created_at DESC""",
            (guild_id, user_id),
        )
        return [dict(r) for r in rows]

    async def get_infraction_by_id(self, infraction_id: int) -> Optional[dict]:
        row = await self._fetchone("SELECT * FROM infractions WHERE id=?", (infraction_id,))
        return dict(row) if row else None

    async def revoke_infraction(self, infraction_id: int) -> bool:
        await self._execute(
            "UPDATE infractions SET active=0 WHERE id=?", (infraction_id,)
        )
        await self._execute(
            "UPDATE infraction_points SET active=0 WHERE infraction_id=?", (infraction_id,)
        )
        return True

    async def get_active_points(self, guild_id: int, user_id: int) -> int:
        """Retourne le total de points actifs non-expirés."""
        await self._execute(
            """UPDATE infraction_points SET active=0
               WHERE guild_id=? AND user_id=? AND expires_at < datetime('now')""",
            (guild_id, user_id),
        )
        row = await self._fetchone(
            """SELECT COALESCE(SUM(points), 0) as total
               FROM infraction_points
               WHERE guild_id=? AND user_id=? AND active=1""",
            (guild_id, user_id),
        )
        return row["total"] if row else 0

    async def get_sanction_thresholds(self, guild_id: int) -> list[dict]:
        rows = await self._fetchall(
            "SELECT * FROM sanction_thresholds WHERE guild_id=? ORDER BY points",
            (guild_id,),
        )
        return [dict(r) for r in rows]

    async def set_sanction_threshold(
        self, guild_id: int, points: int, action: str, duration_min: int, reason: str
    ) -> None:
        await self._execute(
            """INSERT INTO sanction_thresholds (guild_id, points, action, duration_min, reason)
               VALUES (?,?,?,?,?)
               ON CONFLICT(guild_id, points) DO UPDATE
               SET action=excluded.action, duration_min=excluded.duration_min, reason=excluded.reason""",
            (guild_id, points, action, duration_min, reason),
        )

    async def delete_sanction_threshold(self, guild_id: int, points: int) -> None:
        await self._execute(
            "DELETE FROM sanction_thresholds WHERE guild_id=? AND points=?",
            (guild_id, points),
        )

    # ─────────────────────────────────────────────────────────────────────
    #  TICKETS
    # ─────────────────────────────────────────────────────────────────────

    async def create_ticket(
        self, guild_id: int, channel_id: int, owner_id: int, subject: str = "Support"
    ) -> int:
        return await self._execute(
            "INSERT INTO tickets (guild_id, channel_id, owner_id, subject) VALUES (?,?,?,?)",
            (guild_id, channel_id, owner_id, subject),
        )

    async def get_ticket_by_channel(self, channel_id: int) -> Optional[dict]:
        row = await self._fetchone(
            "SELECT * FROM tickets WHERE channel_id=?", (channel_id,)
        )
        return dict(row) if row else None

    async def get_user_open_tickets(self, guild_id: int, user_id: int) -> list[dict]:
        rows = await self._fetchall(
            "SELECT * FROM tickets WHERE guild_id=? AND owner_id=? AND status='open'",
            (guild_id, user_id),
        )
        return [dict(r) for r in rows]

    async def close_ticket(self, channel_id: int, transcript_url: str = None) -> None:
        await self._execute(
            """UPDATE tickets SET status='closed', closed_at=datetime('now'), transcript_url=?
               WHERE channel_id=?""",
            (transcript_url, channel_id),
        )

    async def add_ticket_member(self, ticket_id: int, user_id: int) -> None:
        await self._execute(
            "INSERT OR IGNORE INTO ticket_members (ticket_id, user_id) VALUES (?,?)",
            (ticket_id, user_id),
        )

    async def remove_ticket_member(self, ticket_id: int, user_id: int) -> None:
        await self._execute(
            "DELETE FROM ticket_members WHERE ticket_id=? AND user_id=?",
            (ticket_id, user_id),
        )

    async def save_ticket_panel(self, guild_id: int, channel_id: int, message_id: int) -> None:
        await self._execute(
            """INSERT INTO ticket_panels (guild_id, channel_id, message_id)
               VALUES (?,?,?)
               ON CONFLICT(guild_id, channel_id) DO UPDATE SET message_id=excluded.message_id""",
            (guild_id, channel_id, message_id),
        )

    # ─────────────────────────────────────────────────────────────────────
    #  REACTION ROLES
    # ─────────────────────────────────────────────────────────────────────

    async def add_reaction_role(
        self, guild_id: int, message_id: int, channel_id: int, emoji: str, role_id: int, role_type: str = "toggle"
    ) -> None:
        await self._execute(
            """INSERT INTO reaction_roles (guild_id, message_id, channel_id, emoji, role_id, role_type)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(message_id, emoji) DO UPDATE SET role_id=excluded.role_id""",
            (guild_id, message_id, channel_id, emoji, role_id, role_type),
        )

    async def get_reaction_role(self, message_id: int, emoji: str) -> Optional[dict]:
        row = await self._fetchone(
            "SELECT * FROM reaction_roles WHERE message_id=? AND emoji=?",
            (message_id, emoji),
        )
        return dict(row) if row else None

    async def get_reaction_roles_for_message(self, message_id: int) -> list[dict]:
        rows = await self._fetchall(
            "SELECT * FROM reaction_roles WHERE message_id=?", (message_id,)
        )
        return [dict(r) for r in rows]

    async def remove_reaction_role(self, message_id: int, emoji: str) -> None:
        await self._execute(
            "DELETE FROM reaction_roles WHERE message_id=? AND emoji=?",
            (message_id, emoji),
        )

    # ─────────────────────────────────────────────────────────────────────
    #  STATISTIQUES
    # ─────────────────────────────────────────────────────────────────────

    async def increment_messages(self, guild_id: int, user_id: int, chars: int) -> None:
        await self._execute(
            """INSERT INTO activity_stats (guild_id, user_id, messages_count, chars_count, last_active)
               VALUES (?,?,1,?,datetime('now'))
               ON CONFLICT(guild_id, user_id) DO UPDATE
               SET messages_count=messages_count+1,
                   chars_count=chars_count+?,
                   last_active=datetime('now')""",
            (guild_id, user_id, chars, chars),
        )

    async def increment_voice(self, guild_id: int, user_id: int, minutes: int) -> None:
        await self._execute(
            """INSERT INTO activity_stats (guild_id, user_id, voice_minutes)
               VALUES (?,?,?)
               ON CONFLICT(guild_id, user_id) DO UPDATE
               SET voice_minutes=voice_minutes+?""",
            (guild_id, user_id, minutes, minutes),
        )

    async def get_user_stats(self, guild_id: int, user_id: int) -> Optional[dict]:
        row = await self._fetchone(
            "SELECT * FROM activity_stats WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        )
        return dict(row) if row else None

    async def get_leaderboard(self, guild_id: int, column: str = "messages_count", limit: int = 10) -> list[dict]:
        allowed = {"messages_count", "chars_count", "voice_minutes"}
        if column not in allowed:
            column = "messages_count"
        rows = await self._fetchall(
            f"SELECT * FROM activity_stats WHERE guild_id=? ORDER BY {column} DESC LIMIT ?",
            (guild_id, limit),
        )
        return [dict(r) for r in rows]

    async def get_infraction_leaderboard(self, guild_id: int, limit: int = 10) -> list[dict]:
        rows = await self._fetchall(
            """SELECT user_id, COUNT(*) as total_infractions, SUM(points) as total_points
               FROM infractions WHERE guild_id=? AND active=1
               GROUP BY user_id ORDER BY total_infractions DESC LIMIT ?""",
            (guild_id, limit),
        )
        return [dict(r) for r in rows]
