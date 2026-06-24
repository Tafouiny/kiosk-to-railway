# Kiosk à Produits Frais

Serveur TCP multi-clients d'un kiosk de vente en ligne, réalisé en Python avec **Peewee** (ORM) et **SQLite**. Le projet simule un marché de proximité accessible uniquement aux clients enregistrés.

---

## Architecture

```
kiosk/
├── models.py     # Modèles Peewee (base de données SQLite)
├── auth.py       # Inscription, connexion, token de session, profil
├── boutique.py   # Catalogue, commandes, annulation
├── serveur.py    # Serveur TCP (20 clients simultanés, threading)
├── client.py     # Client interactif en ligne de commande
└── kiosk.db      # Base de données SQLite (générée au premier lancement)
```

---

## Prérequis

- Python 3.10 ou supérieur
- Bibliothèque Peewee

```bash
pip install peewee
```

---

## Lancement

### 1. Démarrer le serveur

```bash
python serveur.py
```

Le serveur :
- initialise automatiquement la base de données SQLite
- charge le catalogue (15 produits en 4 catégories)
- écoute sur `0.0.0.0:5555` et accepte jusqu'à **20 clients simultanés**

### 2. Connecter un client (dans un autre terminal)

```bash
python client.py
```

Pour se connecter à un serveur distant :

```bash
python client.py 192.168.1.10 5555
```

Vous pouvez ouvrir autant de terminaux clients que souhaité (max 20).

---

## Protocole réseau

La communication entre le client et le serveur repose sur **TCP** avec un échange de messages **JSON** délimités par un caractère newline (`\n`).

### Format d'une requête (client → serveur)

```json
{
  "action": "NOM_ACTION",
  "données": {
    "token": "abc123...",
    "clé": "valeur"
  }
}
```

### Format d'une réponse (serveur → client)

```json
{
  "statut": "OK",
  "message": "Texte lisible",
  "token": "abc123..."
}
```

---

## Authentification

Chaque échange nécessite un **token de session** obtenu à la connexion.

| Étape | Action |
|---|---|
| 1 | Le client envoie `CONNEXION` avec identifiant + mot de passe |
| 2 | Le serveur vérifie les identifiants en base (MDP hashé en SHA-256) |
| 3 | Un token hexadécimal de 64 caractères est généré et stocké en base |
| 4 | Toutes les requêtes suivantes incluent ce token dans `données.token` |
| 5 | Le serveur valide le token à chaque requête avant d'exécuter l'action |

---

## Actions disponibles

### Sans authentification

| Action | Paramètres requis | Description |
|---|---|---|
| `INSCRIPTION` | `identifiant`, `nom`, `prenom`, `mot_de_passe` | Crée un compte (bourse initiale : 10 000 FCFA) |
| `CONNEXION` | `identifiant`, `mot_de_passe` | Retourne un token de session |

### Avec token

| Action | Paramètres requis | Description |
|---|---|---|
| `PROFIL` | `token` | Affiche nom, identifiant et solde de la bourse |
| `MODIFIER_MDP` | `token`, `ancien_mdp`, `nouveau_mdp` | Change le mot de passe |
| `SUPPRIMER_PROFIL` | `token`, `mot_de_passe` | Supprime définitivement le compte |
| `CATALOGUE` | `token` | Liste les produits par catégorie avec prix et stock |
| `COMMANDER` | `token`, `articles` | Passe une commande (voir format ci-dessous) |
| `ANNULER` | `token`, `commande_id` | Annule une commande dans les 5 minutes |
| `DECONNEXION` | `token` | Invalide le token et ferme la session |

### Format de la commande

```json
{
  "action": "COMMANDER",
  "données": {
    "token": "abc123...",
    "articles": [
      { "produit_id": 1, "quantite": 2 },
      { "produit_id": 5, "quantite": 1 }
    ]
  }
}
```

---

## Règles métier

### Bourse
- Chaque client reçoit **10 000 FCFA** à l'inscription.
- La bourse est débitée à chaque commande validée.
- Le solde est consultable à tout moment via `PROFIL`.

### Remise
- Une **remise de 30 %** est automatiquement appliquée sur le montant total de chaque commande.

```
Montant payé = montant brut × (1 − 0.30)
```

### Annulation
- Le client dispose de **5 minutes** après la commande pour l'annuler.
- En cas d'annulation, le stock est restauré et la bourse remboursée, **moins une pénalité de 11 %** du montant brut.
- Passé ce délai, la commande est automatiquement validée par le serveur (timer en arrière-plan).

```
Pénalité       = montant brut × 0.11
Net remboursé  = montant payé − pénalité
```

### Exemple chiffré

| Étape | Montant |
|---|---|
| Commande brute | 5 000 FCFA |
| Remise 30 % | − 1 500 FCFA |
| **Total débité** | **3 500 FCFA** |
| Si annulation — pénalité 11 % | − 550 FCFA |
| **Net remboursé** | **2 950 FCFA** |

---

## Catalogue par défaut

| Catégorie | Produits |
|---|---|
| 🥦 Légumes | Tomates, Carottes, Oignons, Pommes de terre |
| 🍋 Fruits | Mangues, Bananes, Papayes, Oranges |
| 🥩 Viandes | Poulet (kg), Bœuf (kg), Mouton (kg) |
| 🥛 Produits laitiers | Lait (litre), Yaourt, Fromage (200g), Beurre (250g) |

---

## Base de données

Les tables sont créées automatiquement au premier démarrage du serveur.

| Table | Description |
|---|---|
| `clients` | Comptes clients (identifiant unique, MDP hashé, bourse) |
| `categories` | 4 catégories de produits |
| `produits` | 15 produits avec prix et stock |
| `sessions` | Tokens de session actifs par client |
| `commandes` | Historique des commandes avec statut et horodatage |
| `lignes_commande` | Détail produit/quantité/prix pour chaque commande |

---

## Limites et sécurité

- **20 clients maximum** simultanés — au-delà, la connexion est refusée poliment.
- Les mots de passe sont stockés en **SHA-256** (jamais en clair).
- Un token de session est **invalidé** à la déconnexion ou suppression de compte.
- Les anciennes sessions d'un client sont **révoquées** à chaque nouvelle connexion.
- Les opérations sur stock et bourse sont effectuées dans des **transactions atomiques** (`db.atomic()`).