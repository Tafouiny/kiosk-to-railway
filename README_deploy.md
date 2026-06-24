# Kiosk à Produits Frais — Déploiement Railway

## Lancement local

```bash
pip install peewee
python serveur.py          # Terminal 1
python client.py           # Terminal 2
```

## Déploiement sur Railway (étapes)

### 1. Créer un compte Railway
Aller sur https://railway.app et se connecter avec GitHub.

### 2. Pousser le code sur GitHub
```bash
git init
git add .
git commit -m "Kiosk initial"
git remote add origin https://github.com/TON_USERNAME/kiosk.git
git push -u origin main
```

### 3. Créer le projet sur Railway
- Aller sur https://railway.app/new
- Choisir "Deploy from GitHub repo"
- Sélectionner le dépôt kiosk
- Railway détecte automatiquement Python et installe requirements.txt

### 4. Exposer le port TCP
Dans le dashboard Railway :
- Aller dans l'onglet "Settings" du service
- Section "Networking" → "Add a TCP Proxy"
- Railway génère une URL et un port du type :
  monapp.railway.app : 12345

### 5. Se connecter depuis n'importe où
```bash
python client.py monapp.railway.app 12345
```
C'est tout — tes camarades font pareil avec la même commande.

## Variables d'environnement
Railway injecte PORT automatiquement. Le serveur le lit avec :
```python
PORT = int(os.environ.get("PORT", 5555))
```
Aucune configuration manuelle nécessaire.

## Base de données
SQLite crée kiosk.db localement sur le serveur Railway.
Les données persistent tant que le service tourne.
