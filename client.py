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
import time

HOST = "thomas.proxy.rlwy.net"
PORT = 46147
BUFFER_SIZE = 4096
MAX_TENTATIVES_RECONNEXION = 5
DELAI_RECONNEXION = 2  # secondes entre chaque tentative


class ConnexionPerdue(Exception):
    """Levée quand la connexion ne peut pas être rétablie après plusieurs essais."""
    pass


def se_connecter(host: str, port: int, silencieux: bool = False) -> socket.socket:
    """Ouvre une nouvelle connexion TCP avec keepalive activé."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    if hasattr(socket, "TCP_KEEPIDLE"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
    if hasattr(socket, "TCP_KEEPINTVL"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
    if hasattr(socket, "TCP_KEEPCNT"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
    sock.connect((host, port))
    if not silencieux:
        print(f"  ✓ Connecté à {host}:{port}")
    return sock


def _recevoir_sur_socket(sock) -> dict:
    """Lit un message JSON directement sur une socket brute (utilisé pendant la reconnexion)."""
    data = b""
    while not data.endswith(b"\n"):
        chunk = sock.recv(BUFFER_SIZE)
        if not chunk:
            raise ConnectionResetError("Connexion fermée par le serveur.")
        data += chunk
    return json.loads(data.decode("utf-8").strip())


def reconnecter(host: str, port: int) -> socket.socket:
    """Tente de rétablir la connexion plusieurs fois avant d'abandonner."""
    for tentative in range(1, MAX_TENTATIVES_RECONNEXION + 1):
        print(f"  ⟳ Reconnexion en cours… (tentative {tentative}/{MAX_TENTATIVES_RECONNEXION})")
        try:
            sock = se_connecter(host, port, silencieux=True)
            _recevoir_sur_socket(sock)  # consomme le message de bienvenue
            print("  ✓ Reconnecté avec succès.")
            return sock
        except (ConnectionRefusedError, OSError, ConnectionResetError):
            time.sleep(DELAI_RECONNEXION)
    raise ConnexionPerdue("Impossible de rétablir la connexion après plusieurs tentatives.")


class Connexion:
    """
    Encapsule la socket TCP et gère la reconnexion automatique en cas de
    coupure (ex: proxy Railway qui ferme une connexion inactive).
    Toute requête échouée déclenche une tentative de reconnexion puis
    un nouvel essai avant d'abandonner.
    """

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.sock = se_connecter(host, port)

    def _reconnecter(self):
        try:
            self.sock.close()
        except OSError:
            pass
        self.sock = reconnecter(self.host, self.port)

    def envoyer(self, action: str, données: dict = {}) -> bool:
        """Envoie une requête. Retourne False si même après reconnexion ça échoue."""
        requete = json.dumps({"action": action, "données": données},
                             ensure_ascii=False) + "\n"
        try:
            self.sock.sendall(requete.encode("utf-8"))
            return True
        except (BrokenPipeError, OSError, ConnectionResetError):
            print("  ⚠ Connexion perdue. Tentative de reconnexion…")
            try:
                self._reconnecter()
                self.sock.sendall(requete.encode("utf-8"))
                return True
            except (ConnexionPerdue, OSError):
                print("  ✗ Reconnexion impossible. Vérifiez votre réseau.")
                return False

    def recevoir(self) -> dict:
        """Reçoit une réponse. Tente une reconnexion si la connexion est morte."""
        try:
            return self._recevoir_brut()
        except (ConnectionResetError, OSError, json.JSONDecodeError):
            print("  ⚠ Connexion perdue en attendant la réponse. Reconnexion…")
            try:
                self._reconnecter()
                return {"statut": "ERREUR",
                        "message": ("La connexion a été rétablie, mais la dernière "
                                    "action n'a peut-être pas été prise en compte. "
                                    "Vérifiez votre profil/commande puis réessayez.")}
            except ConnexionPerdue:
                print("  ✗ Reconnexion impossible. Vérifiez votre réseau.")
                return {"statut": "ERREUR", "message": "Connexion au serveur perdue."}

    def _recevoir_brut(self) -> dict:
        return _recevoir_sur_socket(self.sock)

    def fermer(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ── Protocole JSON (compatibilité, utilisé par les fonctions flux_*) ─────────

def envoyer(conn: "Connexion", action: str, données: dict = {}):
    conn.envoyer(action, données)


def recevoir(conn: "Connexion") -> dict:
    return conn.recevoir()


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

def flux_inscription(conn):
    print("\n── INSCRIPTION ──")
    identifiant = input("  Identifiant : ").strip()
    nom         = input("  Nom         : ").strip()
    prenom      = input("  Prénom      : ").strip()
    mdp         = input("  Mot de passe: ").strip()
    conn.envoyer("INSCRIPTION", {
        "identifiant": identifiant, "nom": nom,
        "prenom": prenom, "mot_de_passe": mdp
    })
    return conn.recevoir()


def flux_connexion(conn):
    print("\n── CONNEXION ──")
    identifiant = input("  Identifiant : ").strip()
    mdp         = input("  Mot de passe: ").strip()
    conn.envoyer("CONNEXION", {
        "identifiant": identifiant, "mot_de_passe": mdp
    })
    return conn.recevoir()


# ── Flux connecté ─────────────────────────────────────────────────────────────

def flux_commander(conn, token):
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
    conn.envoyer("COMMANDER", {"token": token, "articles": articles})
    return conn.recevoir()


def flux_annuler(conn, token):
    print("\n── ANNULER UNE COMMANDE ──")
    cid = input("  Numéro de commande : ").strip()
    if not cid.isdigit():
        print("  Numéro invalide.")
        return {}
    conn.envoyer("ANNULER", {"token": token, "commande_id": int(cid)})
    return conn.recevoir()


def flux_modifier_mdp(conn, token):
    print("\n── MODIFIER MOT DE PASSE ──")
    ancien  = input("  Ancien mot de passe : ").strip()
    nouveau = input("  Nouveau mot de passe : ").strip()
    conn.envoyer("MODIFIER_MDP", {
        "token": token, "ancien_mdp": ancien, "nouveau_mdp": nouveau
    })
    return conn.recevoir()


def flux_supprimer(conn, token):
    print("\n── SUPPRIMER MON PROFIL ──")
    confirm = input("  ⚠️  Cette action est irréversible. "
                    "Confirmez avec votre mot de passe : ").strip()
    conn.envoyer("SUPPRIMER_PROFIL", {
        "token": token, "mot_de_passe": confirm
    })
    return conn.recevoir()


# ── Boucle principale ─────────────────────────────────────────────────────────

def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else PORT

    print(f"Connexion au serveur {host}:{port}…")
    try:
        conn = Connexion(host, port)
    except (ConnectionRefusedError, OSError):
        print("Impossible de se connecter au serveur. Est-il démarré ?")
        sys.exit(1)

    # Message de bienvenue
    rep = conn.recevoir()
    afficher_reponse(rep)

    token     = None
    connecte  = False

    try:
        while True:
            choix = menu_principal(connecte)

            # ── Non connecté ──────────────────────────────────────────────────
            if not connecte:
                if choix == "1":
                    rep = flux_inscription(conn)
                    afficher_reponse(rep)

                elif choix == "2":
                    rep = flux_connexion(conn)
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
                    conn.envoyer("CATALOGUE", {"token": token})
                    rep = conn.recevoir()
                    afficher_reponse(rep)

                elif choix == "2":
                    # Afficher le catalogue d'abord
                    conn.envoyer("CATALOGUE", {"token": token})
                    rep = conn.recevoir()
                    afficher_reponse(rep)
                    rep = flux_commander(conn, token)
                    afficher_reponse(rep)

                elif choix == "3":
                    rep = flux_annuler(conn, token)
                    afficher_reponse(rep)

                elif choix == "4":
                    conn.envoyer("PROFIL", {"token": token})
                    rep = conn.recevoir()
                    afficher_reponse(rep)

                elif choix == "5":
                    rep = flux_modifier_mdp(conn, token)
                    afficher_reponse(rep)

                elif choix == "6":
                    rep = flux_supprimer(conn, token)
                    afficher_reponse(rep)
                    if rep.get("statut") == "OK":
                        token    = None
                        connecte = False

                elif choix == "0":
                    conn.envoyer("DECONNEXION", {"token": token})
                    rep = conn.recevoir()
                    afficher_reponse(rep)
                    token    = None
                    connecte = False

                else:
                    print("  Choix invalide.")

    except KeyboardInterrupt:
        print("\n  Interruption.")
    finally:
        conn.fermer()


main()