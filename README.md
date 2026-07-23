# 🛡️ Bot Discord de Modération — Documentation complète

Bot Discord de modération professionnel, multi-serveurs, avec commandes slash, base de données SQLite persistante et architecture modulaire.

---

## 📋 Table des matières

1. [Prérequis](#prérequis)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Commandes](#commandes)
5. [AutoMod](#automod)
6. [Système de tickets](#système-de-tickets)
7. [Reaction Roles](#reaction-roles)
8. [Statistiques](#statistiques)
9. [Architecture du projet](#architecture-du-projet)

---

## ✅ Prérequis

- **Python 3.11+** (recommandé : 3.12)
- **Token de bot Discord** — [Discord Developer Portal](https://discord.com/developers/applications)
- Permissions bot recommandées : `Administrator` (ou permissions individuelles listées ci-dessous)

### Permissions Discord requises

| Permission | Utilisation |
|---|---|
| `Read Messages / View Channels` | Lecture des messages |
| `Send Messages` | Envoyer des messages |
| `Manage Messages` | Supprimer/purger des messages |
| `Embed Links` | Envoyer des embeds |
| `Ban Members` | Commandes ban/unban |
| `Kick Members` | Commande kick |
| `Moderate Members` | Timeout (mute) |
| `Manage Roles` | Reaction roles, autorole |
| `Manage Channels` | Lock/unlock, création tickets |
| `View Audit Log` | Logs détaillés (modérateur) |
| `Read Message History` | Purge, transcripts |

---

## 🚀 Installation

### 1. Cloner / Télécharger le projet

```bash
# Dans le dossier du projet
cd "d:/Games/Bots search/discord bots"
```

### 2. Créer un environnement virtuel (recommandé)

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Configurer le token

Éditez le fichier `.env` :

```env
BOT_TOKEN=votre_token_discord_ici
TEST_GUILD_ID=123456789012345678   # Optionnel : sync rapide sur votre serveur test
PREFIX=!
LOG_LEVEL=INFO
```

> ⚠️ **Ne partagez JAMAIS votre token Discord !** Ajoutez `.env` à votre `.gitignore`.

### 5. Lancer le bot

```bash
python bot.py
```

---

## ⚙️ Configuration initiale

Lors du premier démarrage, le bot crée automatiquement la base de données `modbot.db`.

### Étapes recommandées

1. **Définir le salon de logs**
   ```
   /config logs #mod-logs
   ```

2. **Définir les rôles modérateurs**
   ```
   /config modrole-add @Modérateur
   /config modrole-add @Admin
   ```

3. **Configurer le message de bienvenue**
   ```
   /config welcome #bienvenue "Bienvenue {user} sur {guild} ! Tu es le membre n°{count} 🎉"
   ```

4. **Déployer le panel de tickets**
   ```
   /ticket panel #support
   ```

5. **Configurer un autorole**
   ```
   /autorole set @Membre
   ```

---

## 🔨 Commandes

> Toutes les commandes sont des **slash commands** (`/commande`).
> Les commandes sensibles nécessitent un rôle de modération **ET** les permissions Discord correspondantes.

### Modération

| Commande | Description | Permissions requises |
|---|---|---|
| `/warn @membre <raison> [points]` | Avertir un membre | Rôle mod |
| `/unwarn <id>` | Révoquer un avertissement | Rôle mod |
| `/warnings @membre` | Voir les infractions | Rôle mod |
| `/kick @membre [raison]` | Expulser | Rôle mod + Kick Members |
| `/ban @membre [raison] [durée] [jours]` | Bannir | Rôle mod + Ban Members |
| `/unban <user_id>` | Débannir | Rôle mod + Ban Members |
| `/softban @membre [raison]` | Ban + unban (purge messages) | Rôle mod + Ban Members |
| `/mute @membre [durée] [raison]` | Timeout Discord | Rôle mod + Moderate Members |
| `/unmute @membre` | Lever le timeout | Rôle mod + Moderate Members |
| `/purge <nombre> [@membre]` | Supprimer des messages | Rôle mod + Manage Messages |
| `/slowmode [secondes] [#salon]` | Mode lent | Rôle mod + Manage Channels |
| `/lock [#salon] [raison]` | Verrouiller un salon | Rôle mod + Manage Channels |
| `/unlock [#salon] [raison]` | Déverrouiller | Rôle mod + Manage Channels |
| `/note @membre <note>` | Ajouter une note | Rôle mod |

### Sanctions progressives (automatiques)

Par défaut :
- **3 points** → Mute 1h
- **5 points** → Mute 24h
- **7 points** → Ban 3 jours
- **10 points** → Ban permanent

Configurer avec `/config sanctions-set`.

### Configuration

| Commande | Description |
|---|---|
| `/config overview` | Vue d'ensemble de la config |
| `/config logs #salon` | Définir le salon de logs |
| `/config modrole-add @role` | Ajouter un rôle modérateur |
| `/config modrole-remove @role` | Retirer un rôle modérateur |
| `/config modrole-list` | Lister les rôles modérateurs |
| `/config welcome #salon <message>` | Message de bienvenue |
| `/config automod-spam [options]` | Configurer l'anti-spam |
| `/config automod-raid [options]` | Configurer l'anti-raid |
| `/config automod-status` | Voir la config automod |
| `/config badword-add <mot>` | Ajouter un mot interdit |
| `/config badword-remove <mot>` | Retirer un mot interdit |
| `/config sanctions-list` | Voir les seuils de sanctions |
| `/config sanctions-set` | Définir un seuil |
| `/config sanctions-delete <points>` | Supprimer un seuil |
| `/config whitelist-channel #salon` | Exclure un salon de l'automod |

---

## 🤖 AutoMod

Le module AutoMod s'active automatiquement sur tous les messages.

### Modules disponibles

| Module | Description | Configurable |
|---|---|---|
| Anti-spam | Limite les messages répétés | ✅ |
| Anti-flood | Bloque les messages trop longs | ✅ |
| Anti-raid | Détecte les vagues d'arrivées | ✅ |
| Filtre mots | Liste noire de mots | ✅ |
| Filtre liens | Bloque domaines blacklistés | ✅ |
| Anti-invitations | Bloque les liens d'invitation Discord | ✅ |
| Anti-emoji spam | Limite les emojis par message | ✅ |
| Anti-mention spam | Limite les @mentions par message | ✅ |

### Whitelist

Exclure un salon ou un rôle de l'AutoMod :
```
/config whitelist-channel #salon-media
```

---

## 🎫 Système de tickets

### Déploiement

```
/ticket panel #support
```

Cela crée un bouton persistant. Les membres cliquent dessus → modal de sujet → salon privé créé.

### Commandes tickets

| Commande | Description |
|---|---|
| `/ticket create [sujet]` | Créer un ticket via commande |
| `/ticket close` | Fermer le ticket actuel |
| `/ticket add @membre` | Ajouter un membre au ticket |
| `/ticket remove @membre` | Retirer un membre |
| `/ticket panel [#salon]` | Afficher le panel |

---

## 🎭 Reaction Roles

```
/reactionrole add <message_id> #salon :emoji: @role [type]
```

**Types disponibles :**
- `toggle` — Ajoute/retire le rôle (défaut)
- `add_only` — Ajoute seulement
- `remove_only` — Retire seulement

---

## 📊 Statistiques

| Commande | Description |
|---|---|
| `/stats [@membre]` | Stats d'activité d'un membre |
| `/leaderboard [catégorie]` | Classement (messages/vocal/infractions) |
| `/serverstats` | Statistiques du serveur |
| `/userinfo [@membre]` | Informations détaillées |
| `/giverole @membre @role` | Attribuer un rôle |
| `/removerole @membre @role` | Retirer un rôle |

---

## 🗂️ Architecture du projet

```
discord bots/
├── bot.py                  # Point d'entrée
├── config.py               # Configuration & constantes
├── .env                    # Variables d'environnement (SECRET)
├── requirements.txt        # Dépendances Python
├── modbot.db               # Base de données (créée auto)
├── modbot.log              # Fichier de logs (créé auto)
├── database/
│   ├── db_manager.py       # Toutes les opérations DB
│   └── models.py           # Schéma des tables SQLite
├── cogs/
│   ├── moderation.py       # Ban, kick, mute, warn...
│   ├── automod.py          # Anti-spam, anti-raid, filtres
│   ├── logs.py             # Événements Discord → logs
│   ├── tickets.py          # Système de tickets
│   ├── roles.py            # Autoroles & reaction roles
│   ├── stats.py            # Statistiques & leaderboards
│   └── config_cog.py       # Configuration du bot
└── utils/
    ├── checks.py           # Vérifications permissions
    ├── embeds.py           # Générateurs d'embeds
    └── helpers.py          # Fonctions utilitaires
```

---

## 🔧 Commandes owner (préfixe `!`)

Réservées au propriétaire du bot :

| Commande | Description |
|---|---|
| `!sync [guild/global]` | Synchroniser les slash commands |
| `!reload <cog>` | Recharger un cog à chaud |
| `!status` | Voir l'état du bot |

---

## 📝 Notes importantes

- **Token Discord** : Toujours garder secret. Ne jamais le commit sur Git.
- **Permissions** : Le bot a besoin du rôle le plus haut possible pour pouvoir modérer les autres membres.
- **Slash commands globales** : Peuvent prendre jusqu'à 1h pour se propager. Utilisez `TEST_GUILD_ID` pour un déploiement instantané sur votre serveur de test.
- **SQLite** : La base de données est créée automatiquement dans le dossier du bot. Sauvegardez `modbot.db` régulièrement.
- **Multi-serveurs** : Toute la configuration est isolée par `guild_id`, le bot peut être sur plusieurs serveurs sans conflit.
