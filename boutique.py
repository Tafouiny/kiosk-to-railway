"""
- Kasongo Mashika Samuel Evariste
- Papa Mbaye Diop
- Sokhna Sylla
- Hountondji Geoffroy
- Mouhamadou Moustapha Ndiaye
"""

from datetime import datetime, timedelta
from peewee import fn
from models import db, Client, Categorie, Produit, Commande, LigneCommande
from auth import authentifier


# ── Affichage du catalogue ───────────────────────────────────────────────────

def afficher_catalogue(token: str) -> dict:
    """
    Retourne la liste des produits groupés par catégorie.
    Nécessite un token valide.
    """
    ok, client, err = authentifier(token)
    if not ok:
        return {"statut": "ERREUR", "message": err}

    catalogue = {}
    for cat in Categorie.select():
        produits = []
        for p in (Produit
                  .select()
                  .where(Produit.categorie == cat)):
            produits.append({
                "id":            p.id,
                "nom":           p.nom,
                "prix_unitaire": p.prix_unitaire,
                "stock":         p.stock,
            })
        catalogue[cat.nom] = produits

    return {"statut": "OK", "catalogue": catalogue}


# ── Passer une commande ──────────────────────────────────────────────────────

def passer_commande(token: str, articles: list[dict]) -> dict:
    """
    Crée une commande à partir d'une liste d'articles.

    articles : [{"produit_id": int, "quantite": int}, ...]

    Règles :
    - Stock suffisant obligatoire pour chaque article
    - Bourse suffisante après remise de 30 %
    - Le stock est débité immédiatement
    - La bourse est débitée immédiatement
    - La commande reste en statut 'en_attente' pendant 5 minutes

    Retourne la facture si succès.
    """
    ok, client, err = authentifier(token)
    if not ok:
        return {"statut": "ERREUR", "message": err}

    if not articles:
        return {"statut": "ERREUR", "message": "ERREUR: Aucun article dans la commande."}

    # ── Vérifications préalables ─────────────────────────────────────────────
    lignes_prep = []   # données validées avant toute écriture
    montant_total = 0.0

    for art in articles:
        try:
            produit = Produit.get_by_id(art["produit_id"])
        except Produit.DoesNotExist:
            return {"statut": "ERREUR",
                    "message": f"ERREUR: Produit ID {art['produit_id']} introuvable."}

        qte = int(art.get("quantite", 0))
        if qte <= 0:
            return {"statut": "ERREUR",
                    "message": f"ERREUR: Quantité invalide pour '{produit.nom}'."}

        if produit.stock < qte:
            return {"statut": "ERREUR",
                    "message": (f"ERREUR: Stock insuffisant pour '{produit.nom}'. "
                                f"Disponible : {produit.stock}.")}

        lignes_prep.append({
            "produit":       produit,
            "quantite":      qte,
            "prix_unitaire": produit.prix_unitaire,
            "sous_total":    produit.prix_unitaire * qte,
        })
        montant_total += produit.prix_unitaire * qte

    # Montant après remise 30 %
    montant_paye = montant_total * (1 - Commande.REMISE)

    # Vérification de la bourse
    if client.bourse < montant_paye:
        return {"statut": "ERREUR",
                "message": (f"ERREUR: Bourse insuffisante. "
                            f"Nécessaire : {montant_paye:.0f} FCFA | "
                            f"Disponible : {client.bourse:.0f} FCFA.")}

    # ── Écriture atomique en base ─────────────────────────────────────────────
    with db.atomic():
        # Créer la commande
        commande = Commande.create(
            client=client,
            montant_total=montant_total,
            montant_paye=montant_paye,
            statut=Commande.STATUT_ATTENTE,
            cree_le=datetime.now(),
        )

        # Créer les lignes et décrémenter le stock
        for lg in lignes_prep:
            LigneCommande.create(
                commande=commande,
                produit=lg["produit"],
                quantite=lg["quantite"],
                prix_unitaire=lg["prix_unitaire"],
            )
            Produit.update(
                stock=Produit.stock - lg["quantite"]
            ).where(Produit.id == lg["produit"].id).execute()

        # Débiter la bourse
        Client.update(
            bourse=Client.bourse - montant_paye
        ).where(Client.id == client.id).execute()

    # ── Construction de la facture ────────────────────────────────────────────
    facture = _construire_facture(commande, lignes_prep,
                                  montant_total, montant_paye)

    return {
        "statut":     "OK",
        "commande_id": commande.id,
        "facture":    facture,
        "message":    ("Commande enregistrée ! Vous avez 5 minutes pour "
                       "l'annuler si nécessaire.")
    }


def _construire_facture(commande, lignes, montant_total, montant_paye) -> str:
    """Formate une facture texte lisible."""
    lignes_txt = []
    for lg in lignes:
        lignes_txt.append(
            f"  {lg['produit'].nom:<22} x{lg['quantite']:<4} "
            f"@ {lg['prix_unitaire']:>6.0f} FCFA  "
            f"= {lg['sous_total']:>8.0f} FCFA"
        )

    remise_montant = montant_total * Commande.REMISE

    facture = (
        f"\n{'='*55}\n"
        f"  FACTURE — Commande #{commande.id}\n"
        f"  Date : {commande.cree_le.strftime('%d/%m/%Y %H:%M:%S')}\n"
        f"{'='*55}\n"
        + "\n".join(lignes_txt) +
        f"\n{'-'*55}\n"
        f"  Sous-total brut  : {montant_total:>10.0f} FCFA\n"
        f"  Remise  (30 %)   : -{remise_montant:>9.0f} FCFA\n"
        f"  {'─'*40}\n"
        f"  TOTAL PAYÉ       : {montant_paye:>10.0f} FCFA\n"
        f"{'='*55}\n"
    )
    return facture


# ── Annuler une commande ─────────────────────────────────────────────────────

def annuler_commande(token: str, commande_id: int) -> dict:
    """
    Annule une commande si elle est encore dans la fenêtre de 5 minutes.

    Effets si annulation :
    - Statut -> 'annulee'
    - Stock remis à jour
    - Bourse remboursée MOINS pénalité de 11 % du montant total brut
    """
    ok, client, err = authentifier(token)
    if not ok:
        return {"statut": "ERREUR", "message": err}

    try:
        commande = Commande.get(
            Commande.id == commande_id,
            Commande.client == client
        )
    except Commande.DoesNotExist:
        return {"statut": "ERREUR",
                "message": "ERREUR: Commande introuvable."}

    # Vérifier le statut
    if commande.statut == Commande.STATUT_ANNULEE:
        return {"statut": "ERREUR",
                "message": "ERREUR: Cette commande est déjà annulée."}

    if commande.statut == Commande.STATUT_VALIDEE:
        return {"statut": "ERREUR",
                "message": "ERREUR: Cette commande est déjà validée, impossible d'annuler."}

    # Vérifier la fenêtre de 5 minutes
    limite = commande.cree_le + timedelta(minutes=5)
    if datetime.now() > limite:
        # Valider automatiquement si dépassé
        Commande.update(statut=Commande.STATUT_VALIDEE).where(
            Commande.id == commande.id
        ).execute()
        return {"statut": "ERREUR",
                "message": ("ERREUR: Délai d'annulation dépassé (5 min). "
                            "La commande est définitivement validée.")}

    # ── Annulation effective ──────────────────────────────────────────────────
    penalite     = commande.penalite()          # 11 % du montant total brut
    remboursement = commande.montant_paye - penalite  # ce qu'on rend au client

    with db.atomic():
        # Remettre le stock
        for ligne in commande.lignes:
            Produit.update(
                stock=Produit.stock + ligne.quantite
            ).where(Produit.id == ligne.produit_id).execute()

        # Rembourser la bourse (moins pénalité)
        Client.update(
            bourse=Client.bourse + remboursement
        ).where(Client.id == client.id).execute()

        # Mettre à jour le statut
        Commande.update(
            statut=Commande.STATUT_ANNULEE
        ).where(Commande.id == commande.id).execute()

    # Bourse après opération
    client_maj = Client.get_by_id(client.id)

    return {
        "statut":  "OK",
        "message": (
            f"Commande #{commande_id} annulée.\n"
            f"  Montant remboursé : {commande.montant_paye:.0f} FCFA\n"
            f"  Pénalité (11 %)   : -{penalite:.0f} FCFA\n"
            f"  Net crédité       : {remboursement:.0f} FCFA\n"
            f"  Nouvelle bourse   : {client_maj.bourse:.0f} FCFA"
        )
    }


# ── Valider manuellement une commande (après 5 min) ─────────────────────────

def valider_commande(commande_id: int):
    """
    Appelée par le serveur après expiration du délai de 5 minutes.
    Passe le statut de 'en_attente' à 'validee'.
    """
    Commande.update(
        statut=Commande.STATUT_VALIDEE
    ).where(
        Commande.id == commande_id,
        Commande.statut == Commande.STATUT_ATTENTE
    ).execute()


# ── Test rapide ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    if os.path.exists("kiosk.db"):
        os.remove("kiosk.db")

    from models import init_db
    from auth import inscrire_client, connecter_client

    init_db()

    # Préparer un client
    inscrire_client("keita01", "Keita", "Amadou", "pass123")
    r = connecter_client("keita01", "pass123")
    token = r["token"]
    print(f"Connecté : {r['message']}\n")

    # 1. Catalogue
    r = afficher_catalogue(token)
    for cat, produits in r["catalogue"].items():
        print(f"\n{'─'*45}")
        print(f"  {cat.upper()}")
        print(f"{'─'*45}")
        for p in produits:
            print(f"  [{p['id']:>2}] {p['nom']:<22} "
                  f"{p['prix_unitaire']:>6.0f} FCFA  "
                  f"stock: {p['stock']}")

    # 2. Passer une commande
    print("\n" + "="*55)
    print("  TEST COMMANDE")
    print("="*55)
    r = passer_commande(token, [
        {"produit_id": 1, "quantite": 2},   # Tomates x2
        {"produit_id": 5, "quantite": 1},   # Mangues x1
        {"produit_id": 9, "quantite": 1},   # Poulet x1
    ])
    print(r["facture"])
    print(r["message"])
    commande_id = r["commande_id"]

    # 3. Annuler dans les 5 minutes
    print("\n" + "="*55)
    print("  TEST ANNULATION (dans les 5 min)")
    print("="*55)
    r = annuler_commande(token, commande_id)
    print(r["message"])

    # 4. Bourse insuffisante
    print("\n" + "="*55)
    print("  TEST BOURSE INSUFFISANTE")
    print("="*55)
    r = passer_commande(token, [
        {"produit_id": 9, "quantite": 10},  # Poulet x10 = 35000 FCFA
    ])
    print(r)