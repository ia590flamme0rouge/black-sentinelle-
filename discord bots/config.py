"""
config.py — Configuration globale du bot de modération Discord
"""
from __future__ import annotations

# ─────────────────────────────────────────────
#  DÉVELOPPEURS & PROPRIÉTAIRES DU BOT (Super-Admin permanent)
# ─────────────────────────────────────────────
BOT_DEVELOPERS: list[str] = ["lyrox7__", "lyrox__", "lyrox"]

# ─────────────────────────────────────────────
#  NOMS DE RÔLES AUTORISÉS (par défaut)
#  Chaque serveur peut surcharger via /config modrole
# ─────────────────────────────────────────────
DEFAULT_MOD_ROLES: list[str] = ["Bot Manager", "Modérateur", "Admin", "Moderator"]

# ─────────────────────────────────────────────
#  SANCTIONS PROGRESSIVES (par défaut)
#  Chaque serveur peut surcharger via /config sanctions
# ─────────────────────────────────────────────
DEFAULT_SANCTION_THRESHOLDS: list[dict] = [
    {"points": 3,  "action": "mute",    "duration_minutes": 60,   "reason": "3 avertissements accumulés"},
    {"points": 5,  "action": "mute",    "duration_minutes": 1440, "reason": "5 avertissements accumulés (mute 24h)"},
    {"points": 7,  "action": "tempban", "duration_minutes": 4320, "reason": "7 avertissements accumulés (ban 3 jours)"},
    {"points": 10, "action": "ban",     "duration_minutes": 0,    "reason": "10 avertissements — ban permanent"},
]

# Durée d'expiration des points d'infraction (en jours)
INFRACTION_POINT_EXPIRY_DAYS: int = 30

# ─────────────────────────────────────────────
#  AUTOMOD — Valeurs par défaut
# ─────────────────────────────────────────────
AUTOMOD_DEFAULTS: dict = {
    "anti_spam_enabled":      True,
    "anti_spam_messages":     5,       # nb messages
    "anti_spam_seconds":      5,       # dans ce délai
    "anti_flood_enabled":     True,
    "anti_flood_chars":       500,     # caractères max par message
    "anti_raid_enabled":      True,
    "anti_raid_joins":        10,      # nb arrivées
    "anti_raid_seconds":      10,      # dans ce délai
    "anti_raid_lockdown":     True,    # verrouiller serveur
    "word_filter_enabled":    True,
    "link_filter_enabled":    True,
    "invite_filter_enabled":  True,    # bloquer invitations Discord
    "emoji_spam_enabled":     True,
    "emoji_spam_max":         15,      # emojis max par message
    "mention_spam_enabled":   True,
    "mention_spam_max":       5,       # mentions max par message
}

# Mots interdits par défaut (peut être étendu via /config badwords)
DEFAULT_BAD_WORDS: list[str] = []

# Domaines blacklistés par défaut
DEFAULT_BLACKLISTED_DOMAINS: list[str] = [
    "grabify.link", "iplogger.org", "blasze.tk",
]

# ─────────────────────────────────────────────
#  TICKETS
# ─────────────────────────────────────────────
TICKET_CATEGORY_NAME: str  = "🎫 Tickets"
TICKET_LOG_CATEGORY:  str  = "📋 Tickets Archivés"
MAX_TICKETS_PER_USER: int  = 3

# ─────────────────────────────────────────────
#  LOGS
# ─────────────────────────────────────────────
DEFAULT_LOG_CHANNEL_NAME: str = "mod-logs"

# ─────────────────────────────────────────────
#  COULEURS EMBEDS
# ─────────────────────────────────────────────
COLORS = {
    "success":  0x2ECC71,   # Vert
    "error":    0xE74C3C,   # Rouge
    "warning":  0xF39C12,   # Orange
    "info":     0x3498DB,   # Bleu
    "mute":     0x95A5A6,   # Gris
    "ban":      0xC0392B,   # Rouge foncé
    "kick":     0xE67E22,   # Orange foncé
    "warn":     0xF1C40F,   # Jaune
    "unban":    0x27AE60,   # Vert foncé
    "log":      0x2C3E50,   # Gris foncé
    "join":     0x1ABC9C,   # Teal
    "leave":    0xE74C3C,   # Rouge
    "ticket":   0x9B59B6,   # Violet
    "stats":    0x3498DB,   # Bleu
}

# ─────────────────────────────────────────────
#  EMOJIS
# ─────────────────────────────────────────────
EMOJIS = {
    "success":  "✅",
    "error":    "❌",
    "warning":  "⚠️",
    "ban":      "🔨",
    "kick":     "👢",
    "mute":     "🔇",
    "warn":     "⚠️",
    "unban":    "🔓",
    "ticket":   "🎫",
    "log":      "📋",
    "stats":    "📊",
    "shield":   "🛡️",
    "lock":     "🔒",
    "unlock":   "🔓",
    "trash":    "🗑️",
    "clock":    "⏰",
    "crown":    "👑",
    "member":   "👤",
    "join":     "📥",
    "leave":    "📤",
}

# ─────────────────────────────────────────────
#  BASE DE DONNÉES
# ─────────────────────────────────────────────
DB_PATH: str = "modbot.db"
