# Bulletin Gaudet — tableau de bord et bulletin radio de l'actualité

Deux fois par jour (6 h et 16 h, heure de Montréal), cette application :

1. lit les fils RSS de cinq rubriques : Québec et Canada, International, Économie et finances, Droit et tribunaux, IA et technologie;
2. demande à l'IA Gemini de Google (palier gratuit) de trier, regrouper et analyser les nouvelles;
3. publie un **tableau de bord** web (manchette, résumé, « À surveiller », nouvelles classées par importance avec leurs sources);
4. rédige un **bulletin radio** (environ 7 minutes le matin, 5 minutes le soir), le fait lire par une voix québécoise et le publie comme **balado privé**, que tu écoutes dans Android Auto avec Pocket Casts.

**Tout est gratuit** : GitHub (exécution et publication), Gemini (palier gratuit de Google), la voix de synthèse et Pocket Casts. Si Gemini ne répond pas un jour donné, l'application passe automatiquement en **mode de secours** : tu reçois quand même ton tableau de bord et ton bulletin, avec les manchettes, mais sans analyse.

---

## Installation (environ 30 minutes, une seule fois)

### 1. Créer le dépôt GitHub

1. Crée un compte sur <https://github.com> si tu n'en as pas.
2. En haut à droite, **+ → New repository**.
   - Nom : `bulletin-nouvelles`
   - Visibilité : **Public**. C'est nécessaire pour GitHub Pages gratuit. Seul le code est public : ta clé API reste secrète (étape 3).
   - Clique **Create repository**.
3. Sur la page du dépôt, clique **uploading an existing file**. Glisse le **contenu** du dossier décompressé : `bulletin`, `demo`, `site`, `config.yaml`, `requirements.txt` et `README.md`. Clique ensuite **Commit changes**.
4. Le dossier `.github` est caché sur Mac et Windows, il faut donc le créer à la main :
   **Add file → Create new file**, nomme le fichier exactement `.github/workflows/bulletin.yml`, colle le contenu du fichier `bulletin.yml` fourni, puis **Commit changes**.

### 2. Obtenir une clé Gemini gratuite

1. Va sur <https://aistudio.google.com> et connecte-toi avec un compte Google.
2. Accepte les conditions d'utilisation, puis clique **Get API key → Create API key**. Si on te demande un projet, laisse Google en créer un.
3. Copie la clé (elle commence habituellement par `AIza`).

N'ajoute **pas** de mode de paiement : la clé reste ainsi sur le palier gratuit et ne peut rien te facturer.

### 3. Donner la clé à GitHub

Dans le dépôt : **Settings → Secrets and variables → Actions → New repository secret**

| Nom | Valeur |
|---|---|
| `GEMINI_API_KEY` | ta clé Gemini |
| `SITE_SECRET` *(facultatif, recommandé)* | un mot inventé, sans espace ni accent, ex. `kx7-matin-q42` |

`SITE_SECRET` place le tableau de bord et le balado dans un sous-dossier difficile à deviner. Le site reste techniquement public, mais personne ne le trouvera par hasard. Il n'est pas non plus indexé par les moteurs de recherche.

### 4. Activer la publication web

**Settings → Pages → Build and deployment → Source : GitHub Actions**.

### 5. Lancer la première édition

**Actions** → si GitHub le demande, clique **I understand my workflows, go ahead and enable them**. Ensuite : **Bulletin de nouvelles → Run workflow → Run workflow**.

Après 3 à 6 minutes, la pastille devient verte. Tes adresses :

- Tableau de bord : `https://TON-COMPTE.github.io/bulletin-nouvelles/` (ajoute `TON-SECRET/` à la fin si tu as défini `SITE_SECRET`)
- Balado : la même adresse suivie de `feed.xml`. Le bouton **Copier le lien du balado** du tableau de bord le copie pour toi.

Ensuite, tout se fait automatiquement chaque jour.

---

## Écouter dans la voiture (Android Auto)

1. Installe **Pocket Casts** (Google Play, gratuit).
2. Dans Pocket Casts, onglet **Découvrir** ou **Podcasts**, colle l'adresse du balado (`…/feed.xml`) dans la barre de recherche, puis abonne-toi à **Bulletin Gaudet**.
3. Dans les réglages du balado :
   - **Téléchargement automatique** des nouveaux épisodes, pour que ça joue même sans réseau;
   - **Ajouter à « À suivre » (Up Next) → en haut de la liste**, pour que le dernier bulletin soit toujours le prochain.
4. Dans la voiture : « **Ok Google, fais jouer Bulletin Gaudet sur Pocket Casts** ».
   Si l'assistant ne reconnaît pas le nom, « **Reprends la lecture sur Pocket Casts** » joue le premier épisode de ta liste « À suivre », c'est-à-dire le dernier bulletin si tu as fait le réglage précédent.

Pocket Casts vérifie les nouveaux épisodes périodiquement. Si un bulletin tarde à apparaître, tire l'écran vers le bas dans le balado pour actualiser.

---

## Personnaliser (fichier `config.yaml`, modifiable directement sur GitHub avec le crayon)

- **Nom du balado** (`podcast.titre`) : c'est le nom à prononcer dans la voiture. Il doit être court et distinctif.
- **Durée** des bulletins (`duree_minutes`) et **consignes** de chaque édition.
- **Voix** : `fr-CA-SylvieNeural` (femme) ou `fr-CA-AntoineNeural`, `fr-CA-JeanNeural`, `fr-CA-ThierryNeural` (hommes). Tu peux aussi régler la vitesse.
- **Rubriques et sources** : ajoute ou retire des adresses de fils RSS. Un fil qui ne répond pas est ignoré.
- **Service d'IA** (`fournisseur`) : `gemini` (gratuit, par défaut), `claude` (API payante, analyse plus fine, nécessite le secret `ANTHROPIC_API_KEY`) ou `aucun` (manchettes seulement).
- **Modèles Gemini** : si Google retire ou renomme un modèle, remplace son nom dans `gemini.modele`. Les modèles de `modeles_secours` sont essayés automatiquement si le premier est saturé.

### Changer les heures de production

Modifie `heure` dans `config.yaml`, puis les deux lignes `cron` de `.github/workflows/bulletin.yml`. Les heures GitHub sont en UTC, et chaque ligne contient deux heures pour couvrir l'heure d'été et l'heure d'hiver :

| Heure à Montréal | Ligne `cron` |
|---|---|
| 5 h | `"0 9,10 * * *"` |
| 6 h | `"0 10,11 * * *"` |
| 7 h | `"0 11,12 * * *"` |
| 16 h | `"0 20,21 * * *"` |
| 17 h | `"0 21,22 * * *"` |

GitHub peut lancer les tâches planifiées avec 5 à 30 minutes de retard aux heures achalandées.

---

## Dépannage

- **Voir ce qui s'est passé** : onglet **Actions** → cliquer sur une exécution → **produire** → **Produire le bulletin**. Le journal indique le nombre d'articles par source et les fils ignorés.
- **« Aucun article collecté »** : les fils RSS ne répondent plus. Remplace-les dans `config.yaml`.
- **« Mode de secours » dans le tableau de bord** : Gemini n'a pas répondu. Le journal indique pourquoi :
  - `GEMINI_API_KEY absent` ou `HTTP 400/403` : la clé est mal copiée ou le secret est mal nommé;
  - `HTTP 429` répété : quota gratuit atteint, ce qui ne devrait pas arriver avec deux bulletins par jour. Réessaie plus tard;
  - `modèle introuvable` : Google a retiré le modèle. Mets à jour `gemini.modele` dans `config.yaml`.
- **Courriel de GitHub disant que l'horaire a été désactivé** : GitHub suspend les tâches planifiées des dépôts inactifs depuis 60 jours. Le programme réactive l'horaire chaque lundi pour éviter ça. Si ça arrive quand même, clique **Enable workflow** dans l'onglet Actions.
- **Pas d'audio** : la voix utilise le service de synthèse gratuit de Microsoft Edge (non officiel). Le tableau de bord est publié même si l'audio échoue, et l'exécution suivante réessaie.

## Bon à savoir

- Le tableau de bord conserve les 30 dernières éditions (menu en haut à droite) et le balado, les 10 derniers épisodes.
- Les titres et extraits des articles sont envoyés à Gemini pour l'analyse. Sur le palier gratuit, Google peut utiliser ce contenu pour améliorer ses produits. Il ne s'agit que de manchettes publiques : aucune donnée personnelle ni de clients n'est transmise. **N'ajoute jamais de sources privées ou confidentielles dans `config.yaml`.**
- Les quotas gratuits de Google peuvent changer. Si un jour ils ne suffisent plus, le mode de secours prend le relais, et tu peux passer à `fournisseur: "claude"`, qui est payant.
- L'analyse est produite par IA à partir de manchettes et de courts extraits. Elle peut contenir des erreurs, alors vérifie la source avant de t'appuyer sur une nouvelle.

## Tester sur ton ordinateur (facultatif)

```bash
pip install -r requirements.txt
python -m bulletin --demo --sans-audio      # aperçu sans API, dans le dossier public/
GEMINI_API_KEY=AIza... python -m bulletin --edition matin
```
