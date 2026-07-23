"""
database/models.py — Schéma SQL de la base de données
"""

# ─────────────────────────────────────────────────────────────────────────────
#  Création de toutes les tables SQLite
# ─────────────────────────────────────────────────────────────────────────────

CREATE_TABLES: list[str] = [

    # ── Configuration par serveur ──────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS guilds (
        guild_id        INTEGER PRIMARY KEY,
        prefix          TEXT    DEFAULT '!',
        log_channel_id  INTEGER,
        mod_roles       TEXT    DEFAULT '[]',       -- JSON list of role IDs
        mute_role_id    INTEGER,
        ticket_category INTEGER,
        ticket_log_cat  INTEGER,
        welcome_channel INTEGER,
        welcome_message TEXT    DEFAULT 'Bienvenue {user} sur {guild} !',
        autorole_id     INTEGER,
        created_at      TEXT    DEFAULT (datetime('now'))
    )
    """,

    # ── Configuration AutoMod par serveur ──────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS automod_config (
        guild_id                INTEGER PRIMARY KEY,
        anti_spam_enabled       INTEGER DEFAULT 1,
        anti_spam_messages      INTEGER DEFAULT 5,
        anti_spam_seconds       INTEGER DEFAULT 5,
        anti_flood_enabled      INTEGER DEFAULT 1,
        anti_flood_chars        INTEGER DEFAULT 500,
        anti_raid_enabled       INTEGER DEFAULT 1,
        anti_raid_joins         INTEGER DEFAULT 10,
        anti_raid_seconds       INTEGER DEFAULT 10,
        anti_raid_lockdown      INTEGER DEFAULT 1,
        word_filter_enabled     INTEGER DEFAULT 1,
        bad_words               TEXT    DEFAULT '[]',   -- JSON list
        link_filter_enabled     INTEGER DEFAULT 1,
        blacklisted_domains     TEXT    DEFAULT '[]',   -- JSON list
        invite_filter_enabled   INTEGER DEFAULT 1,
        emoji_spam_enabled      INTEGER DEFAULT 1,
        emoji_spam_max          INTEGER DEFAULT 15,
        mention_spam_enabled    INTEGER DEFAULT 1,
        mention_spam_max        INTEGER DEFAULT 5,
        whitelisted_channels    TEXT    DEFAULT '[]',   -- JSON list channel IDs
        whitelisted_roles       TEXT    DEFAULT '[]'    -- JSON list role IDs
    )
    """,

    # ── Seuils de sanctions progressives ──────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS sanction_thresholds (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id        INTEGER NOT NULL,
        points          INTEGER NOT NULL,
        action          TEXT    NOT NULL,   -- mute | tempban | ban | kick
        duration_min    INTEGER DEFAULT 0,
        reason          TEXT    DEFAULT '',
        UNIQUE(guild_id, points)
    )
    """,

    # ── Infractions (warns, bans, kicks, mutes) ────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS infractions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id        INTEGER NOT NULL,
        user_id         INTEGER NOT NULL,
        moderator_id    INTEGER NOT NULL,
        infraction_type TEXT    NOT NULL,   -- warn | ban | kick | mute | unban | note
        reason          TEXT    DEFAULT 'Aucune raison fournie',
        points          INTEGER DEFAULT 0,
        duration_min    INTEGER DEFAULT 0,  -- 0 = permanent
        active          INTEGER DEFAULT 1,  -- 1 = actif, 0 = révoqué
        expires_at      TEXT,               -- ISO datetime, NULL = permanent
        created_at      TEXT    DEFAULT (datetime('now'))
    )
    """,

    # ── Points d'infraction actifs (avec expiration) ───────────────────────
    """
    CREATE TABLE IF NOT EXISTS infraction_points (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id        INTEGER NOT NULL,
        user_id         INTEGER NOT NULL,
        infraction_id   INTEGER NOT NULL REFERENCES infractions(id),
        points          INTEGER NOT NULL,
        expires_at      TEXT    NOT NULL,   -- ISO datetime
        active          INTEGER DEFAULT 1
    )
    """,

    # ── Tickets ────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS tickets (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id        INTEGER NOT NULL,
        channel_id      INTEGER NOT NULL UNIQUE,
        owner_id        INTEGER NOT NULL,
        subject         TEXT    DEFAULT 'Support',
        status          TEXT    DEFAULT 'open',   -- open | closed | archived
        claimed_by      INTEGER,
        transcript_url  TEXT,
        created_at      TEXT    DEFAULT (datetime('now')),
        closed_at       TEXT
    )
    """,

    # ── Membres des tickets ────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS ticket_members (
        ticket_id   INTEGER NOT NULL REFERENCES tickets(id),
        user_id     INTEGER NOT NULL,
        PRIMARY KEY (ticket_id, user_id)
    )
    """,

    # ── Reaction Roles ─────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS reaction_roles (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id    INTEGER NOT NULL,
        message_id  INTEGER NOT NULL,
        channel_id  INTEGER NOT NULL,
        emoji       TEXT    NOT NULL,
        role_id     INTEGER NOT NULL,
        role_type   TEXT    DEFAULT 'toggle',   -- toggle | add_only | remove_only
        UNIQUE(message_id, emoji)
    )
    """,

    # ── Statistiques d'activité ────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS activity_stats (
        guild_id        INTEGER NOT NULL,
        user_id         INTEGER NOT NULL,
        messages_count  INTEGER DEFAULT 0,
        chars_count     INTEGER DEFAULT 0,
        voice_minutes   INTEGER DEFAULT 0,
        commands_used   INTEGER DEFAULT 0,
        last_active     TEXT    DEFAULT (datetime('now')),
        PRIMARY KEY (guild_id, user_id)
    )
    """,

    # ── Salon de panel tickets (pour retrouver le message bouton) ──────────
    """
    CREATE TABLE IF NOT EXISTS ticket_panels (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id    INTEGER NOT NULL,
        channel_id  INTEGER NOT NULL,
        message_id  INTEGER NOT NULL,
        UNIQUE(guild_id, channel_id)
    )
    """,

    # ── Index de performance ───────────────────────────────────────────────
    "CREATE INDEX IF NOT EXISTS idx_infractions_guild_user ON infractions(guild_id, user_id)",
    "CREATE INDEX IF NOT EXISTS idx_points_guild_user ON infraction_points(guild_id, user_id, active)",
    "CREATE INDEX IF NOT EXISTS idx_tickets_guild ON tickets(guild_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_stats_guild ON activity_stats(guild_id, messages_count DESC)",
]
