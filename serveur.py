"""
serveur.py — Serveur TCP du Kiosk à produits
Adapté pour Railway : PORT lu depuis la variable d'environnement
"""

import socket
import threading
import json
import time
import os
import traceback
from datetime import datetime

from models import init_db, Commande, db
from auth import (inscrire_client, connecter_client,
                  deconnecter_client, consulter_profil,
                  modifier_mot_de_passe, supprimer_profil)
from boutique import (afficher_catalogue, passer_commande,
                      annuler_commande, valider_commande)

# ── Configuration ─────────────────────────────────────────────────────────────

HOST        = "0.0.0.0"
PORT        = int(os.environ.get("PORT", 5555))  # Railway injecte PORT auto
MAX_CLIENTS = 20
BUFFER_SIZE = 4096
DELAI_ANNUL = 300  # 5 minutes

# ── Compteur de connexions ────────────────────────────────────────────────────

connexions_actives = 0
verrou_connexions  = threading.Lock()

# ── Message de bienvenue ──────────────────────────────────────────────────────

BIENVENUE = r"""
╔══════════════════════════════════════════════════╗
║         BIENVENUE AU KIOSK PRODUITS FRAIS        ║
║  Votre marché de proximité, disponible 24h/24 !  ║
╚══════════════════════════════════════════════════╝
Connectez-vous ou créez un compte pour commencer.
"""

# ── TCP Keepalive (évite les connexions "zombies" coupées par les proxys) ────

def activer_keepalive(conn: socket.socket):
    """
    Active le TCP keepalive natif du système pour détecter rapidement
    les connexions mortes (coupées par un proxy/NAT intermédiaire, ex. Railway)
    au lieu de rester bloqué indéfiniment sur recv().
    """
    try:
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if hasattr(socket, "TCP_KEEPIDLE"):
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
        if hasattr(socket, "TCP_KEEPINTVL"):
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
        if hasattr(socket, "TCP_KEEPCNT"):
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
    except OSError:
        pass


# ── Protocole JSON ────────────────────────────────────────────────────────────

def envoyer(conn: socket.socket, data: dict) -> bool:
    """Envoie un message JSON. Retourne False si la connexion est morte."""
    try:
        message = json.dumps(data, ensure_ascii=False) + "\n"
        conn.sendall(message.encode("utf-8"))
        return True
    except (BrokenPipeError, OSError):
        return False


def recevoir(conn: socket.socket) -> dict | None:
    try:
        data = b""
        while not data.endswith(b"\n"):
            chunk = conn.recv(BUFFER_SIZE)
            if not chunk:
                return None
            data += chunk
        return json.loads(data.decode("utf-8").strip())
    except (json.JSONDecodeError, OSError, ConnectionResetError):
        return None


# ── Timer d'annulation ────────────────────────────────────────────────────────

def lancer_timer_validation(commande_id: int):
    def _valider():
        time.sleep(DELAI_ANNUL)
        valider_commande(commande_id)
        print(f"[TIMER] Commande #{commande_id} validée automatiquement.")

    t = threading.Thread(target=_valider, daemon=True)
    t.start()


# ── Dispatch des actions ──────────────────────────────────────────────────────

def traiter_action(action: str, données: dict) -> dict:
    token = données.get("token", "")

    if action == "PING":
        return {"statut": "OK", "message": "PONG"}
    if action == "INSCRIPTION":
        return inscrire_client(
            données.get("identifiant", ""),
            données.get("nom", ""),
            données.get("prenom", ""),
            données.get("mot_de_passe", ""),
        )
    if action == "CONNEXION":
        return connecter_client(
            données.get("identifiant", ""),
            données.get("mot_de_passe", ""),
        )
    if action == "DECONNEXION":
        return deconnecter_client(token)
    if action == "PROFIL":
        return consulter_profil(token)
    if action == "MODIFIER_MDP":
        return modifier_mot_de_passe(
            token,
            données.get("ancien_mdp", ""),
            données.get("nouveau_mdp", ""),
        )
    if action == "SUPPRIMER_PROFIL":
        return supprimer_profil(token, données.get("mot_de_passe", ""))
    if action == "CATALOGUE":
        return afficher_catalogue(token)
    if action == "COMMANDER":
        resultat = passer_commande(token, données.get("articles", []))
        if resultat.get("statut") == "OK":
            lancer_timer_validation(resultat["commande_id"])
        return resultat
    if action == "ANNULER":
        return annuler_commande(token, données.get("commande_id"))

    return {"statut": "ERREUR", "message": f"Action inconnue '{action}'."}


# ── Gestion d'un client ───────────────────────────────────────────────────────

def gerer_client(conn: socket.socket, adresse: tuple):
    global connexions_actives

    ip, port = adresse
    activer_keepalive(conn)
    db.connect(reuse_if_open=True)
    print(f"[+] Nouveau client : {ip}:{port} (actifs: {connexions_actives})")

    if not envoyer(conn, {
        "statut":  "BIENVENUE",
        "message": BIENVENUE,
        "actions": [
            "INSCRIPTION", "CONNEXION", "DECONNEXION",
            "PROFIL", "MODIFIER_MDP", "SUPPRIMER_PROFIL",
            "CATALOGUE", "COMMANDER", "ANNULER",
        ]
    }):
        print(f"[!] Impossible d'envoyer le message de bienvenue à {ip}:{port} "
              f"(connexion déjà fermée)")

    try:
        while True:
            requete = recevoir(conn)
            if requete is None:
                print(f"[-] Déconnexion : {ip}:{port}")
                break

            action  = requete.get("action", "").upper()
            données = requete.get("données", {})
            if action != "PING":
                print(f"[>] {ip}:{port}  action={action}")

            try:
                réponse = traiter_action(action, données)
            except Exception as e:
                print(f"[!] Erreur {action} chez {ip}:{port} : {e}")
                traceback.print_exc()
                réponse = {"statut": "ERREUR", "message": f"Erreur serveur : {e}"}

            if not envoyer(conn, réponse):
                print(f"[-] Connexion perdue en répondant à {ip}:{port}")
                break

            if action == "DECONNEXION" and réponse.get("statut") == "OK":
                break

    except Exception as e:
        print(f"[!] Erreur inattendue client {ip}:{port} : {e}")
        traceback.print_exc()
    finally:
        conn.close()
        if not db.is_closed():
            db.close()
        with verrou_connexions:
            connexions_actives -= 1
        print(f"[=] {ip}:{port} déconnecté (actifs: {connexions_actives})")


# ── Boucle principale ─────────────────────────────────────────────────────────

def demarrer_serveur():
    print("[DB] Initialisation...")
    init_db()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(MAX_CLIENTS)

    print(f"[OK] Serveur démarré sur {HOST}:{PORT} (max {MAX_CLIENTS} clients)")

    global connexions_actives

    try:
        while True:
            try:
                conn, adresse = srv.accept()
            except OSError as e:
                print(f"[!] Erreur sur accept() : {e}")
                traceback.print_exc()
                break

            try:
                with verrou_connexions:
                    if connexions_actives >= MAX_CLIENTS:
                        envoyer(conn, {
                            "statut":  "ERREUR",
                            "message": "Serveur complet (20 clients max). Réessayez plus tard."
                        })
                        conn.close()
                        continue
                    connexions_actives += 1

                t = threading.Thread(
                    target=gerer_client,
                    args=(conn, adresse),
                    daemon=True
                )
                t.start()
            except Exception as e:
                # Ne jamais laisser une erreur sur UNE connexion tuer la boucle d'accept
                print(f"[!] Erreur en démarrant le thread client : {e}")
                traceback.print_exc()

    except KeyboardInterrupt:
        print("\n[..] Arrêt du serveur.")
    except Exception as e:
        print(f"[!!!] Erreur fatale dans la boucle principale : {e}")
        traceback.print_exc()
    finally:
        srv.close()


if __name__ == "__main__":
    demarrer_serveur()