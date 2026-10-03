# 🤖 JARVIS Local

**Ton assistant vocal personnel, façon Iron Man, qui tourne 100 % sur ton PC.**

Tu parles à une orbe futuriste. JARVIS te répond à la voix (avec son flegme de
majordome britannique), et il sait vraiment faire des choses :

- 🗣️ **Conversation vocale en temps réel** (tu parles, il répond instantanément)
- 🛠️ **Vraies tâches sur ta machine** : il lance des sessions **Claude Code**
  (chercher sur internet, analyser des fichiers, écrire du code, créer des
  documents...) et te résume le résultat à voix haute
- 🚀 **Lancer tes applications** : « Ouvre Discord », « Mets Spotify sur
  l'écran de gauche » (multi-écrans géré)
- 🌐 **Ouvrir des sites** : « Ouvre mes emails » → Gmail s'ouvre dans ton navigateur
- 📊 **Afficher des rapports** : cartes, indicateurs, graphiques interactifs et
  tableaux directement sur l'interface (« Analyse ce fichier Excel et
  montre-moi un rapport »)
- ❌ **Annuler une tâche** à la voix ou d'un clic

> ⚠️ **Windows uniquement** pour le lancement d'applications et le multi-écrans.
> Le reste (voix, tâches Claude, rapports) marche partout.

---

## 💰 Combien ça coûte ?

Deux services payants sont nécessaires :

| Service | Sert à | Coût approximatif |
|---|---|---|
| **Claude** (Anthropic) | Les tâches (fichiers, code, recherches) | Abonnement Claude Pro (~20 $/mois) — si tu utilises déjà Claude Code, tu l'as déjà |
| **API OpenAI** | La voix temps réel | Paiement à l'usage : compte ~10-30 centimes pour 10 min de conversation. 5 $ de crédit suffisent largement pour découvrir |

---

## 📋 Étape 0 — Les prérequis

### Python (3.10 ou plus récent)

1. Va sur https://www.python.org/downloads/ et clique **Download Python**
2. Lance l'installeur. **IMPORTANT : coche la case "Add Python to PATH"** en bas
   de la première fenêtre avant de cliquer Install
3. Vérifie : ouvre un terminal (touche Windows → tape `cmd` → Entrée) et tape :
   ```
   python --version
   ```
   Tu dois voir `Python 3.x.x`. Si "python n'est pas reconnu", réinstalle en
   cochant bien la case PATH.

### Node.js (nécessaire pour installer Claude Code)

1. Va sur https://nodejs.org et télécharge la version **LTS**
2. Installe en cliquant Suivant partout
3. Vérifie dans un **nouveau** terminal :
   ```
   node --version
   ```

---

## 🧠 Étape 1 — Créer un compte Claude et installer Claude Code

Claude Code est l'agent qui exécute les vraies tâches sur ta machine.

1. **Crée un compte Claude** sur https://claude.ai (bouton *Sign up*)
2. **Prends un abonnement Claude Pro** (nécessaire pour utiliser Claude Code) :
   sur https://claude.ai, va dans les paramètres → *Upgrade*
3. **Installe Claude Code** — dans un terminal :
   ```
   npm install -g @anthropic-ai/claude-code
   ```
4. **Connecte-le à ton compte** — toujours dans le terminal :
   ```
   claude
   ```
   La première fois, il ouvre ton navigateur pour te connecter à ton compte
   Claude. Suis les instructions, puis tape `/exit` pour quitter.
5. **Vérifie** que tout marche :
   ```
   claude -p "Dis bonjour"
   ```
   Si Claude te répond dans le terminal, c'est gagné. ✅

---

## 🔑 Étape 2 — Créer un compte OpenAI et récupérer une clé API

La clé API OpenAI sert à la partie **voix temps réel** (ce n'est PAS un
abonnement ChatGPT Plus — c'est un compte développeur, facturé à l'usage).

1. **Crée un compte** sur https://platform.openai.com/signup
   (tu peux utiliser un compte Google)
2. **Ajoute du crédit** : va sur https://platform.openai.com/settings/organization/billing
   → *Add payment method* puis achète du crédit (5 $ suffisent pour commencer).
   ⚠️ Sans crédit, la voix ne fonctionnera pas (erreur "quota").
3. **Crée ta clé API** : va sur https://platform.openai.com/api-keys
   → *Create new secret key* → donne-lui un nom (ex : "jarvis") → *Create*
4. **Copie la clé immédiatement** (elle commence par `sk-...`) : elle ne sera
   plus jamais affichée. Garde-la secrète, c'est comme un mot de passe.

---

## ⚙️ Étape 3 — Installer JARVIS

1. **Télécharge ce dossier** (bouton vert *Code* → *Download ZIP* sur GitHub,
   puis décompresse-le où tu veux)

2. **Ouvre un terminal dans le dossier** : dans l'Explorateur Windows, ouvre le
   dossier, clique dans la barre d'adresse, tape `cmd` et appuie sur Entrée

3. **Installe les dépendances Python** :
   ```
   pip install -r requirements.txt
   ```

4. **Configure ta clé** :
   - Fais une copie du fichier `.env.example` et renomme-la `.env`
     (dans le terminal : `copy .env.example .env`)
   - Ouvre `.env` avec le Bloc-notes et colle ta clé OpenAI après
     `OPENAI_API_KEY=` (sans espaces, sans guillemets) :
     ```
     OPENAI_API_KEY=sk-proj-ta-cle-ici
     ```
   - (Conseillé) Décommente `JARVIS_WORKDIR` et mets un dossier dédié où
     JARVIS aura le droit de travailler sur tes fichiers

---

## 🚀 Étape 4 — Lancer JARVIS

Dans le terminal, toujours dans le dossier :

```
python server.py
```

Puis ouvre ton navigateur sur **http://127.0.0.1:8788**

1. Clique sur l'orbe
2. **Autorise le micro** quand le navigateur le demande
3. Parle !

### Exemples de commandes vocales

- « Bonjour JARVIS, présente-toi. »
- « Ouvre Discord. » / « Mets Chrome sur l'écran de droite. »
- « Ouvre mes emails. »
- « Liste les fichiers de mon dossier de travail et dis-moi ce qu'il y a dedans. »
- « Cherche les dernières actus IA et fais-moi un résumé. »
- « Affiche-moi un comparatif des 3 meilleurs GPU du moment dans un rapport. »
- « Annule la tâche. »

Pour l'arrêter : reclique sur l'orbe, et ferme le terminal (ou Ctrl+C dedans).

---

## 🔧 Personnalisation (fichier `.env`)

| Variable | Défaut | Rôle |
|---|---|---|
| `OPENAI_API_KEY` | *(requis)* | Clé API OpenAI pour la voix |
| `REALTIME_MODEL` | `gpt-realtime` | Modèle vocal OpenAI |
| `JARVIS_VOICE` | `ballad` | Voix (ballad = majordome ; ash, echo, verse, cedar, marin...) |
| `JARVIS_LANGUAGE` | `français` | Langue parlée |
| `JARVIS_WORKDIR` | dossier utilisateur | Où travaillent les sessions Claude Code |
| `JARVIS_TASK_TIMEOUT` | `600` | Durée max d'une tâche (secondes) |
| `JARVIS_PORT` | `8788` | Port du serveur local |
| `JARVIS_PERMISSION_MODE` | `bypassPermissions` | Autorisations des sessions Claude Code : `bypassPermissions` (aucune demande), `acceptEdits` (fichiers OK, shell demande), `off` (comportement d'origine) |

---

## ❓ Problèmes fréquents

**« OPENAI_API_KEY manquant »**
→ Le fichier `.env` n'existe pas ou la clé n'est pas dedans. Vérifie qu'il
s'appelle bien `.env` (pas `.env.txt` — active l'affichage des extensions de
fichiers dans l'Explorateur) et relance `python server.py`.

**Erreur `insufficient_quota` ou `429`**
→ Pas de crédit sur ton compte OpenAI. Retourne à l'étape 2, point 2.

**« La commande 'claude' est introuvable » sur les tâches**
→ Claude Code n'est pas installé ou pas connecté. Refais l'étape 1 et vérifie
avec `claude -p "test"` dans un terminal.

**Le micro ne marche pas**
→ Vérifie que tu as bien cliqué "Autoriser" sur la demande du navigateur.
Sinon : icône 🔒/⚙ à gauche de l'adresse → Micro → Autoriser, puis recharge.

**L'orbe dit « erreur » à la connexion**
→ Lis le message affiché sous l'orbe : il contient la vraie raison (clé
invalide, pas de crédit, pas d'internet...).

**Les rapports/graphiques ne s'affichent pas**
→ Il faut une connexion internet (les composants graphiques se chargent en ligne).

**Python ou pip « n'est pas reconnu »**
→ Python n'est pas dans le PATH. Réinstalle-le en cochant "Add Python to PATH".

---

## 🔒 Sécurité — à lire

- Ta clé OpenAI **ne quitte jamais ton PC** : le navigateur ne reçoit qu'un
  jeton temporaire de session. Ne partage jamais ton fichier `.env`.
- JARVIS exécute des tâches **avec les droits de ton utilisateur** dans
  `JARVIS_WORKDIR`, et peut lancer tes applications. C'est le but — mais ne
  mets **jamais** ce serveur sur internet : il est conçu pour tourner en local
  (127.0.0.1) uniquement.
- ⚠️ Les sessions Claude Code tournent **sans demande d'autorisation**
  (`JARVIS_PERMISSION_MODE=bypassPermissions`). C'est nécessaire : elles n'ont
  aucune interface, donc personne ne pourrait répondre à une demande — la tâche
  resterait bloquée jusqu'au timeout. En contrepartie, JARVIS peut écrire,
  supprimer et exécuter des commandes sans te consulter. **Configure donc
  `JARVIS_WORKDIR` sur un dossier dédié** (pas ton dossier utilisateur) pour
  limiter ce qu'il peut atteindre. Si tu préfères un garde-fou plus strict, mets
  `JARVIS_PERMISSION_MODE=acceptEdits` : les commandes shell seront alors
  refusées au lieu d'être exécutées.
- Les sessions Claude Code utilisent **ton** compte et **ta** machine, avec les
  protections normales de Claude Code.

## 📄 Licence

MIT — fais-en ce que tu veux.
