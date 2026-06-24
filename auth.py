"""
- Kasongo Mashika Samuel Evariste
- Papa Mbaye Diop
- Sokhna Sylla
- Hountondji Geoffroy
- Mouhamadou Moustapha Ndiaye
"""

from datetime import datetime
from peewee import IntegrityError
from models import db, Client, Session, hacher, generer_token


# ── Codes de réponse ─────────────────────────────────────────────────────────

OK                    = "OK"
ERR_CHAMPS_MANQUANTS  = "ERREUR: Champs obligatoires manquants."
ERR_ID_EXISTE         = "ERREUR: Cet identifiant est déjà pris."
ERR_IDENTIFIANTS      = "ERREUR: Identifiant ou mot de passe incorrect."
ERR_TOKEN_INVALIDE    = "ERREUR: Session invalide ou expirée. Reconnectez-vous."
ERR_MDP_INCORRECT     = "ERREUR: Mot de passe actuel incorrect."
ERR_CLIENT_INTROUVABLE = "ERREUR: Client introuvable."


# ── Inscription ──────────────────────────────────────────────────────────────

def inscrire_client(identifiant: str, nom: str,
                    prenom: str, mot_de_passe: str) -> dict:
    """
    Crée un nouveau compte client.
    Retourne : {"statut": OK, "message": ...}
            ou {"statut": ERREUR, "message": ...}
    """
    # Validation des champs
    if not all([identifiant, nom, prenom, mot_de_passe]):
        return {"statut": "ERREUR", "message": ERR_CHAMPS_MANQUANTS}

    try:
        client = Client.create(
            identifiant=identifiant.strip(),
            nom=nom.strip(),
            prenom=prenom.strip(),
            mot_de_passe=hacher(mot_de_passe),
            bourse=10_000.0
        )
        return {
            "statut": OK,
            "message": (f"Bienvenue {client.prenom} {client.nom} ! "
                        f"Votre compte a été créé. "
                        f"Bourse initiale : {client.bourse:.0f} FCFA.")
        }
    except IntegrityError:
        return {"statut": "ERREUR", "message": ERR_ID_EXISTE}


# ── Connexion ────────────────────────────────────────────────────────────────

def connecter_client(identifiant: str, mot_de_passe: str) -> dict:
    """
    Authentifie un client et crée une session active.
    Retourne le token si succès.
    """
    if not all([identifiant, mot_de_passe]):
        return {"statut": "ERREUR", "message": ERR_CHAMPS_MANQUANTS}

    try:
        client = Client.get(Client.identifiant == identifiant.strip())
    except Client.DoesNotExist:
        return {"statut": "ERREUR", "message": ERR_IDENTIFIANTS}

    if not client.verifier_mdp(mot_de_passe):
        return {"statut": "ERREUR", "message": ERR_IDENTIFIANTS}

    # Vérifier si une session est déjà active sur ce compte
    session_existante = Session.select().where(
        Session.client == client,
        Session.actif == True
    ).exists()

    if session_existante:
        return {
            "statut": "ERREUR",
            "message": ("ERREUR: Ce compte est déjà connecté depuis un autre terminal. "
                        "Déconnectez-vous d'abord.")
        }

    # Créer une nouvelle session
    token = generer_token()
    Session.create(client=client, token=token, cree_le=datetime.now())

    return {
        "statut": OK,
        "token": token,
        "message": (f"Connexion réussie. Bonjour {client.prenom} !\n"
                    f"Bourse disponible : {client.bourse:.0f} FCFA.")
    }


# ── Validation du token ──────────────────────────────────────────────────────

def valider_token(token: str) -> Client | None:
    """
    Vérifie que le token est valide et actif.
    Retourne le Client associé ou None si invalide.
    """
    if not token:
        return None
    try:
        session = (Session
                   .select(Session, Client)
                   .join(Client)
                   .where(Session.token == token,
                          Session.actif == True)
                   .get())
        return session.client
    except Session.DoesNotExist:
        return None


def authentifier(token: str) -> tuple[bool, Client | None, str]:
    """
    Helper pratique : retourne (succès, client, message_erreur).
    Usage dans les autres modules :
        ok, client, err = authentifier(token)
        if not ok: return {"statut": "ERREUR", "message": err}
    """
    client = valider_token(token)
    if client is None:
        return False, None, ERR_TOKEN_INVALIDE
    # Rafraîchir depuis la DB pour avoir les données à jour
    client = Client.get_by_id(client.id)
    return True, client, ""


# ── Déconnexion ──────────────────────────────────────────────────────────────

def deconnecter_client(token: str) -> dict:
    """Invalide le token de session du client."""
    ok, client, err = authentifier(token)
    if not ok:
        return {"statut": "ERREUR", "message": err}

    Session.update(actif=False).where(Session.token == token).execute()

    return {
        "statut": OK,
        "message": f"Au revoir {client.prenom} ! Vous êtes déconnecté."
    }


# ── Consulter le profil ──────────────────────────────────────────────────────

def consulter_profil(token: str) -> dict:
    """Retourne les informations du profil du client connecté."""
    ok, client, err = authentifier(token)
    if not ok:
        return {"statut": "ERREUR", "message": err}

    return {
        "statut": OK,
        "profil": {
            "identifiant": client.identifiant,
            "nom":         client.nom,
            "prenom":      client.prenom,
            "bourse":      client.bourse,
        }
    }


# ── Modifier le mot de passe ─────────────────────────────────────────────────

def modifier_mot_de_passe(token: str,
                          ancien_mdp: str,
                          nouveau_mdp: str) -> dict:
    """
    Modifie le mot de passe du client après vérification de l'ancien.
    """
    ok, client, err = authentifier(token)
    if not ok:
        return {"statut": "ERREUR", "message": err}

    if not client.verifier_mdp(ancien_mdp):
        return {"statut": "ERREUR", "message": ERR_MDP_INCORRECT}

    if not nouveau_mdp or len(nouveau_mdp) < 4:
        return {"statut": "ERREUR",
                "message": "ERREUR: Le nouveau mot de passe est trop court (min 4 caractères)."}

    Client.update(
        mot_de_passe=hacher(nouveau_mdp)
    ).where(Client.id == client.id).execute()

    return {"statut": OK, "message": "Mot de passe modifié avec succès."}


# ── Supprimer le profil ──────────────────────────────────────────────────────

def supprimer_profil(token: str, mot_de_passe: str) -> dict:
    """
    Supprime définitivement le compte client.
    Demande confirmation via le mot de passe.
    """
    ok, client, err = authentifier(token)
    if not ok:
        return {"statut": "ERREUR", "message": err}

    if not client.verifier_mdp(mot_de_passe):
        return {"statut": "ERREUR", "message": ERR_MDP_INCORRECT}

    nom_complet = f"{client.prenom} {client.nom}"

    # Invalider la session d'abord
    Session.update(actif=False).where(
        Session.client == client
    ).execute()

    # Supprimer le client (CASCADE supprime ses sessions)
    client.delete_instance(recursive=True)

    return {
        "statut": OK,
        "message": f"Profil de {nom_complet} supprimé définitivement."
    }


# ── Test rapide ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    if os.path.exists("kiosk.db"):
        os.remove("kiosk.db")

    from models import init_db
    init_db()

    print("\n" + "="*50)
    print("  TESTS AUTH")
    print("="*50)

    # 1. Inscription
    r = inscrire_client("sow01", "Sow", "Fatou", "mdp1234")
    print(f"\n[Inscription]  {r}")

    r2 = inscrire_client("sow01", "Sow", "Fatou", "mdp1234")
    print(f"[ID dupliqué]  {r2}")

    # 2. Connexion
    r = connecter_client("sow01", "mdp1234")
    print(f"\n[Connexion OK] {r['message']}")
    token = r["token"]
    print(f"  Token : {token[:20]}…")

    r = connecter_client("sow01", "mauvais")
    print(f"[Mauvais MDP]  {r}")

    # 3. Validation token
    client = valider_token(token)
    print(f"\n[Token valide] Client : {client}")

    client_faux = valider_token("tokenbidon")
    print(f"[Token faux]   Résultat : {client_faux}")

    # 4. Profil
    r = consulter_profil(token)
    print(f"\n[Profil]       {r}")

    # 5. Modifier mot de passe
    r = modifier_mot_de_passe(token, "mdp1234", "nouveau456")
    print(f"\n[MDP modifié]  {r}")

    r = connecter_client("sow01", "nouveau456")
    print(f"[Reconnexion]  {r['message']}")
    token = r["token"]

    # 6. Supprimer profil
    r = supprimer_profil(token, "nouveau456")
    print(f"\n[Suppression]  {r}")

    r = connecter_client("sow01", "nouveau456")
    print(f"[Après suppr.] {r}")