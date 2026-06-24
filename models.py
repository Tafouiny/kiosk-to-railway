"""
- Kasongo Mashika Samuel Evariste
- Papa Mbaye Diop
- Sokhna Sylla
- Hountondji Geoffroy
- Mouhamadou Moustapha Ndiaye
"""

import hashlib
import secrets
from datetime import datetime
from peewee import (
    SqliteDatabase, Model,
    CharField, FloatField, IntegerField,
    DateTimeField, ForeignKeyField, BooleanField,
)

# ── Base de données ──────────────────────────────────────────────────────────

db = SqliteDatabase(
    "kiosk.db",
    pragmas={
        "foreign_keys": 1,
        "journal_mode": "wal",   # autorise lecteurs + 1 writer en parallèle
        "busy_timeout": 5000,    # attend jusqu'à 5s si la base est verrouillée
                                 # au lieu de planter immédiatement avec "database is locked"
    },
    check_same_thread=False,
)


class BaseModel(Model):
    class Meta:
        database = db


# ── Fonctions utilitaires (sans décorateurs) ─────────────────────────────────

def hacher(mdp: str) -> str:
    """Retourne le SHA-256 du mot de passe."""
    return hashlib.sha256(mdp.encode()).hexdigest()


def generer_token() -> str:
    """Génère un token de session aléatoire de 64 caractères hex."""
    return secrets.token_hex(32)


# ── Modèle Client ────────────────────────────────────────────────────────────

class Client(BaseModel):
    """
    Représente un client enregistré dans le kiosk.
    - identifiant : login unique de connexion
    - bourse      : solde en FCFA (initialisé à 10 000 à l'inscription)
    """
    identifiant  = CharField(unique=True, max_length=50)
    nom          = CharField(max_length=100)
    prenom       = CharField(max_length=100)
    mot_de_passe = CharField(max_length=256)   # stocké en SHA-256
    bourse       = FloatField(default=10000.0)

    class Meta:
        table_name = "clients"

    def verifier_mdp(self, mdp: str) -> bool:
        """Vérifie si le mot de passe fourni correspond à celui stocké."""
        return self.mot_de_passe == hacher(mdp)

    def __str__(self):
        return (f"Client({self.identifiant} | "
                f"{self.prenom} {self.nom} | "
                f"bourse={self.bourse:.2f} FCFA)")


# ── Modèle Catégorie ─────────────────────────────────────────────────────────

class Categorie(BaseModel):
    """Catégorie de produit : légumes, fruits, viandes, produits laitiers."""
    nom = CharField(unique=True, max_length=50)

    class Meta:
        table_name = "categories"

    def __str__(self):
        return self.nom


# ── Modèle Produit ───────────────────────────────────────────────────────────

class Produit(BaseModel):
    """
    Produit vendu dans le kiosk.
    - prix_unitaire : prix en FCFA
    - stock         : quantité disponible
    """
    nom           = CharField(max_length=100)
    prix_unitaire = FloatField()
    stock         = IntegerField(default=0)
    categorie     = ForeignKeyField(Categorie, backref="produits",
                                    on_delete="RESTRICT")

    class Meta:
        table_name = "produits"

    def __str__(self):
        return (f"{self.nom} | {self.prix_unitaire:.0f} FCFA "
                f"| stock: {self.stock}")


# ── Modèle Session ───────────────────────────────────────────────────────────

class Session(BaseModel):
    """
    Token de session pour authentifier chaque échange client <-> serveur.
    - token  : chaîne aléatoire de 64 caractères hexadécimaux
    - actif  : True tant que le client est connecté
    """
    client  = ForeignKeyField(Client, backref="sessions",
                              on_delete="CASCADE")
    token   = CharField(unique=True, max_length=128)
    cree_le = DateTimeField(default=datetime.now)
    actif   = BooleanField(default=True)

    class Meta:
        table_name = "sessions"

    def __str__(self):
        return f"Session({self.client.identifiant} | actif={self.actif})"


# ── Modèle Commande ──────────────────────────────────────────────────────────

class Commande(BaseModel):
    """
    Commande passée par un client.
    - montant_total : coût brut avant remise
    - montant_paye  : coût après remise de 30 %
    - statut        : 'en_attente' | 'validee' | 'annulee'
    - cree_le       : horodatage (utilisé pour la fenêtre d'annulation 5 min)
    """
    STATUT_ATTENTE = "en_attente"
    STATUT_VALIDEE = "validee"
    STATUT_ANNULEE = "annulee"

    REMISE   = 0.30   # 30 % de remise après achat
    PENALITE = 0.11   # 11 % de pénalité si annulation

    client        = ForeignKeyField(Client, backref="commandes",
                                    on_delete="RESTRICT")
    montant_total = FloatField(default=0.0)
    montant_paye  = FloatField(default=0.0)
    statut        = CharField(max_length=20, default=STATUT_ATTENTE)
    cree_le       = DateTimeField(default=datetime.now)

    class Meta:
        table_name = "commandes"

    def appliquer_remise(self):
        """Calcule montant_paye après remise de 30 %."""
        self.montant_paye = self.montant_total * (1 - self.REMISE)

    def penalite(self) -> float:
        """Retourne la pénalité d'annulation (11 % du montant total)."""
        return self.montant_total * self.PENALITE

    def __str__(self):
        return (f"Commande#{self.id} | {self.client.identifiant} | "
                f"total={self.montant_total:.2f} | "
                f"payé={self.montant_paye:.2f} | statut={self.statut}")


# ── Modèle LigneCommande ─────────────────────────────────────────────────────

class LigneCommande(BaseModel):
    """
    Détail d'une commande : 1 produit + quantité.
    - prix_unitaire : snapshot du prix au moment de l'achat
    """
    commande      = ForeignKeyField(Commande, backref="lignes",
                                    on_delete="CASCADE")
    produit       = ForeignKeyField(Produit, backref="lignes",
                                    on_delete="RESTRICT")
    quantite      = IntegerField()
    prix_unitaire = FloatField()

    class Meta:
        table_name = "lignes_commande"

    def sous_total(self) -> float:
        """Retourne le sous-total de la ligne (quantité × prix unitaire)."""
        return self.quantite * self.prix_unitaire

    def __str__(self):
        return (f"{self.produit.nom} x{self.quantite} "
                f"@ {self.prix_unitaire:.0f} FCFA "
                f"= {self.sous_total():.0f} FCFA")


# ── Initialisation DB + données de départ ────────────────────────────────────

def init_db():
    """Crée les tables et insère le catalogue produits."""
    db.connect(reuse_if_open=True)
    db.create_tables(
        [Client, Categorie, Produit, Session, Commande, LigneCommande],
        safe=True
    )
    _seed_produits()


def _seed_produits():
    """Insère 4 catégories et 15 produits si la table est vide."""
    if Produit.select().count() > 0:
        return

    catalogue = {
        "Légumes": [
            ("Tomates",          500,  50),
            ("Carottes",         300,  40),
            ("Oignons",          200,  60),
            ("Pommes de terre",  400,  80),
        ],
        "Fruits": [
            ("Mangues",          750,  30),
            ("Bananes",          300,  45),
            ("Papayes",          600,  20),
            ("Oranges",          400,  35),
        ],
        "Viandes": [
            ("Poulet (kg)",     3500,  15),
            ("Boeuf (kg)",      4500,  10),
            ("Mouton (kg)",     4000,  12),
        ],
        "Produits laitiers": [
            ("Lait (litre)",     800,  25),
            ("Yaourt",           500,  30),
            ("Fromage (200g)",  1200,  20),
            ("Beurre (250g)",    900,  18),
        ],
    }

    for nom_cat, produits in catalogue.items():
        cat, _ = Categorie.get_or_create(nom=nom_cat)
        for nom_p, prix, stock in produits:
            Produit.get_or_create(
                nom=nom_p,
                defaults={"prix_unitaire": prix, "stock": stock,
                          "categorie": cat}
            )

    print(f"[DB] Catalogue chargé : {Produit.select().count()} produits "
          f"dans {Categorie.select().count()} catégories.")


# ── Test rapide ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    if os.path.exists("kiosk.db"):
        os.remove("kiosk.db")

    init_db()

    for cat in Categorie.select():
        print(f"\n{'='*45}")
        print(f"  {cat.nom.upper()}")
        print(f"{'='*45}")
        for p in cat.produits:
            print(f"  • {p}")

    client = Client.create(
        identifiant="diallo01",
        nom="Diallo",
        prenom="Moussa",
        mot_de_passe=hacher("secret123"),
    )
    print(f"\n✅ {client}")

    tok = generer_token()
    sess = Session.create(client=client, token=tok)
    print(f"🔑 Token : {tok[:20]}…  actif={sess.actif}")

    print(f"🔐 MDP correct   : {client.verifier_mdp('secret123')}")
    print(f"🔐 MDP incorrect : {client.verifier_mdp('mauvais')}")