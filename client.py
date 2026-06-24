"""
- Kasongo Mashika Samuel Evariste
- Papa Mbaye Diop
- Sokhna Sylla
- Hountondji Geoffroy
- Mouhamadou Moustapha Ndiaye
"""

import socket
import json
import sys

HOST = "127.0.0.1"
PORT = 5555
BUFFER_SIZE = 4096


# ── Protocole JSON ────────────────────────────────────────────────────────────

def envoyer(sock, action: str, données: dict = {}):
    requete = json.dumps({"action": action, "données": données},
                         ensure_ascii=False) + "\n"
    sock.sendall(requete.encode("utf-8"))


def recevoir(sock) -> dict:
    data = b""
    while not data.endswith(b"\n"):
        chunk = sock.recv(BUFFER_SIZE)
        if not chunk:
            return {}
        data += chunk
    return json.loads(data.decode("utf-8").strip())


# ── Affichage helpers ─────────────────────────────────────────────────────────

def afficher_reponse(rep: dict):
    if "message" in rep:
        print(rep["message"])
    if "facture" in rep:
        print(rep["facture"])
    if "profil" in rep:
        p = rep["profil"]
        print(f"  Identifiant : {p['identifiant']}")
        print(f"  Nom         : {p['prenom']} {p['nom']}")
        print(f"  Bourse      : {p['bourse']:.0f} FCFA")
    if "catalogue" in rep:
        for cat, produits in rep["catalogue"].items():
            print(f"\n{'─'*50}")
            print(f"  {cat.upper()}")
            print(f"{'─'*50}")
            for p in produits:
                print(f"  [{p['id']:>2}] {p['nom']:<24} "
                      f"{p['prix_unitaire']:>6.0f} FCFA  "
                      f"stock: {p['stock']}")


def menu_principal(connecte: bool) -> list:
    print("\n" + "═"*45)
    if not connecte:
        print("  1. S'inscrire")
        print("  2. Se connecter")
        print("  0. Quitter")
    else:
        print("  1. Voir le catalogue")
        print("  2. Passer une commande")
        print("  3. Annuler une commande")
        print("  4. Mon profil")
        print("  5. Modifier mon mot de passe")
        print("  6. Supprimer mon profil")
        print("  0. Se déconnecter")
    print("═"*45)
    return input("  Choix : ").strip()


# ── Flux non connecté ─────────────────────────────────────────────────────────

def flux_inscription(sock):
    print("\n── INSCRIPTION ──")
    identifiant = input("  Identifiant : ").strip()
    nom         = input("  Nom         : ").strip()
    prenom      = input("  Prénom      : ").strip()
    mdp         = input("  Mot de passe: ").strip()
    envoyer(sock, "INSCRIPTION", {
        "identifiant": identifiant, "nom": nom,
        "prenom": prenom, "mot_de_passe": mdp
    })
    return recevoir(sock)


def flux_connexion(sock):
    print("\n── CONNEXION ──")
    identifiant = input("  Identifiant : ").strip()
    mdp         = input("  Mot de passe: ").strip()
    envoyer(sock, "CONNEXION", {
        "identifiant": identifiant, "mot_de_passe": mdp
    })
    return recevoir(sock)


# ── Flux connecté ─────────────────────────────────────────────────────────────

def flux_commander(sock, token):
    print("\n── PASSER UNE COMMANDE ──")
    print("  Entrez les articles (format: ID QUANTITE), ligne vide pour terminer.")
    articles = []
    while True:
        ligne = input("  Article : ").strip()
        if not ligne:
            break
        parts = ligne.split()
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            print("  Format invalide. Exemple : 1 3  (produit ID=1, quantité=3)")
            continue
        articles.append({"produit_id": int(parts[0]),
                         "quantite":   int(parts[1])})
    if not articles:
        print("  Aucun article saisi.")
        return {}
    envoyer(sock, "COMMANDER", {"token": token, "articles": articles})
    return recevoir(sock)


def flux_annuler(sock, token):
    print("\n── ANNULER UNE COMMANDE ──")
    cid = input("  Numéro de commande : ").strip()
    if not cid.isdigit():
        print("  Numéro invalide.")
        return {}
    envoyer(sock, "ANNULER", {"token": token, "commande_id": int(cid)})
    return recevoir(sock)


def flux_modifier_mdp(sock, token):
    print("\n── MODIFIER MOT DE PASSE ──")
    ancien  = input("  Ancien mot de passe : ").strip()
    nouveau = input("  Nouveau mot de passe : ").strip()
    envoyer(sock, "MODIFIER_MDP", {
        "token": token, "ancien_mdp": ancien, "nouveau_mdp": nouveau
    })
    return recevoir(sock)


def flux_supprimer(sock, token):
    print("\n── SUPPRIMER MON PROFIL ──")
    confirm = input("  ⚠️  Cette action est irréversible. "
                    "Confirmez avec votre mot de passe : ").strip()
    envoyer(sock, "SUPPRIMER_PROFIL", {
        "token": token, "mot_de_passe": confirm
    })
    return recevoir(sock)


# ── Boucle principale ─────────────────────────────────────────────────────────

def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else PORT

    print(f"Connexion au serveur {host}:{port}…")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
    except ConnectionRefusedError:
        print("Impossible de se connecter au serveur. Est-il démarré ?")
        sys.exit(1)

    # Message de bienvenue
    rep = recevoir(sock)
    afficher_reponse(rep)

    token     = None
    connecte  = False

    try:
        while True:
            choix = menu_principal(connecte)

            # ── Non connecté ──────────────────────────────────────────────────
            if not connecte:
                if choix == "1":
                    rep = flux_inscription(sock)
                    afficher_reponse(rep)

                elif choix == "2":
                    rep = flux_connexion(sock)
                    afficher_reponse(rep)
                    if rep.get("statut") == "OK":
                        token    = rep["token"]
                        connecte = True

                elif choix == "0":
                    print("Au revoir !")
                    break
                else:
                    print("  Choix invalide.")

            # ── Connecté ──────────────────────────────────────────────────────
            else:
                if choix == "1":
                    envoyer(sock, "CATALOGUE", {"token": token})
                    rep = recevoir(sock)
                    afficher_reponse(rep)

                elif choix == "2":
                    # Afficher le catalogue d'abord
                    envoyer(sock, "CATALOGUE", {"token": token})
                    rep = recevoir(sock)
                    afficher_reponse(rep)
                    rep = flux_commander(sock, token)
                    afficher_reponse(rep)

                elif choix == "3":
                    rep = flux_annuler(sock, token)
                    afficher_reponse(rep)

                elif choix == "4":
                    envoyer(sock, "PROFIL", {"token": token})
                    rep = recevoir(sock)
                    afficher_reponse(rep)

                elif choix == "5":
                    rep = flux_modifier_mdp(sock, token)
                    afficher_reponse(rep)

                elif choix == "6":
                    rep = flux_supprimer(sock, token)
                    afficher_reponse(rep)
                    if rep.get("statut") == "OK":
                        token    = None
                        connecte = False

                elif choix == "0":
                    envoyer(sock, "DECONNEXION", {"token": token})
                    rep = recevoir(sock)
                    afficher_reponse(rep)
                    token    = None
                    connecte = False

                else:
                    print("  Choix invalide.")

    except KeyboardInterrupt:
        print("\n  Interruption.")
    finally:
        sock.close()


main()