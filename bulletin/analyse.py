"""Analyse de l'actualité et rédaction du bulletin radio (Gemini par défaut, Claude en option)."""
from __future__ import annotations

import json
import logging

from .llm import appeler, extraire_json

log = logging.getLogger(__name__)

MOTS_PAR_MINUTE = 150


def _schema(ids_rubriques: list[str]) -> dict:
    nouvelle = {
        "type": "object",
        "properties": {
            "titre": {"type": "string", "description": "Titre clair et factuel, rédigé par toi."},
            "resume": {"type": "string", "description": "2 à 3 phrases : les faits essentiels."},
            "pourquoi_important": {"type": "string", "description": "1 à 2 phrases : la portée ou l'enjeu."},
            "importance": {"type": "integer", "description": "De 1 (mineur) à 5 (majeur)."},
            "articles": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Numéros des articles fournis qui appuient cette nouvelle.",
            },
        },
        "required": ["titre", "resume", "pourquoi_important", "importance", "articles"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "titre_edition": {"type": "string", "description": "Manchette de l'édition, une phrase."},
            "resume_executif": {"type": "string", "description": "3 à 5 phrases sur l'essentiel de l'édition."},
            "a_surveiller": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3 à 5 éléments à surveiller dans les prochaines heures ou jours.",
            },
            "rubriques": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": ids_rubriques},
                        "synthese": {"type": "string", "description": "2 à 3 phrases d'analyse de la rubrique."},
                        "nouvelles": {"type": "array", "items": nouvelle},
                    },
                    "required": ["id", "synthese", "nouvelles"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["titre_edition", "resume_executif", "a_surveiller", "rubriques"],
        "additionalProperties": False,
    }


def _articles_numerotes(config: dict, articles: dict[str, list[dict]]) -> tuple[str, list[dict]]:
    index: list[dict] = []
    blocs = []
    for rubrique in config["rubriques"]:
        lignes = [f"## Rubrique « {rubrique['nom']} » (id : {rubrique['id']})"]
        for article in articles.get(rubrique["id"], []):
            index.append(article)
            n = len(index)
            ligne = f"[{n}] {article['titre']} — {article['source']}"
            if article["publie"]:
                ligne += f" ({article['publie'][:16].replace('T', ' ')} UTC)"
            if article["extrait"] and article["extrait"] not in article["titre"]:
                ligne += f"\n    {article['extrait']}"
            lignes.append(ligne)
        if len(lignes) == 1:
            lignes.append("(aucun article récent)")
        blocs.append("\n".join(lignes))
    return "\n\n".join(blocs), index


SYSTEME_ANALYSE = """Tu es rédacteur en chef d'un service de veille de l'actualité pour un avocat \
plaideur québécois. Tu lis des manchettes et des extraits issus de fils RSS, tu regroupes les \
articles qui traitent du même événement, tu écartes le bruit (faits divers mineurs, sport, \
divertissement, publicité) et tu produis une analyse claire, factuelle et nuancée, en français \
québécois soigné.

Règles :
- Base-toi uniquement sur les articles fournis. N'invente aucun fait, chiffre ni citation.
- Si l'information est incomplète ou contradictoire entre les sources, dis-le.
- Garde un ton neutre sur les sujets politiques; présente les positions sans prendre parti.
- Pour chaque rubrique, retiens de 3 à 6 nouvelles, classées de la plus importante à la moins importante.
- Dans la rubrique Droit, fais ressortir les décisions, les réformes et les incidences pour la pratique.
- Les titres sont rédigés par toi, pas copiés des médias."""


def analyser(config: dict, articles: dict[str, list[dict]], edition: str,
             date_texte: str, precedente: dict | None) -> dict:
    texte_articles, index = _articles_numerotes(config, articles)
    params = config["editions"][edition]

    contexte = ""
    if precedente:
        titres = [n["titre"] for r in precedente.get("rubriques", []) for n in r.get("nouvelles", [])]
        contexte = ("\n\nNouvelles déjà couvertes dans l'édition précédente "
                    f"({precedente.get('edition_libelle', '')}) :\n- " + "\n- ".join(titres[:40]) +
                    "\nNe les reprends que s'il y a du nouveau, et précise alors ce qui a changé.")

    message = (f"Édition : {edition} — {date_texte}.\n{params['consigne']}{contexte}\n\n"
               f"Voici les articles collectés :\n\n{texte_articles}")

    log.info("Analyse : %d articles envoyés (%s)", len(index), config.get("fournisseur", "gemini"))
    schema = _schema([r["id"] for r in config["rubriques"]])
    analyse = extraire_json(appeler(config, SYSTEME_ANALYSE, message, schema))

    # Contrôle de la structure, puis remplacement des numéros d'articles par les
    # vraies sources (aucune URL inventée).
    for cle in ("titre_edition", "resume_executif"):
        if not isinstance(analyse.get(cle), str) or not analyse[cle].strip():
            raise ValueError(f"Champ « {cle} » manquant dans l'analyse")
    analyse["a_surveiller"] = [str(x) for x in analyse.get("a_surveiller") or []]
    noms = {r["id"]: r["nom"] for r in config["rubriques"]}
    rubriques = []
    for rubrique in analyse.get("rubriques") or []:
        identifiant = str(rubrique.get("id", "")).lower()
        if identifiant not in noms:
            continue
        rubrique["id"], rubrique["nom"] = identifiant, noms[identifiant]
        rubrique["synthese"] = str(rubrique.get("synthese", ""))
        nouvelles = []
        for nouvelle in rubrique.get("nouvelles") or []:
            if not nouvelle.get("titre"):
                continue
            try:
                nouvelle["importance"] = max(1, min(5, int(nouvelle.get("importance", 3))))
            except (TypeError, ValueError):
                nouvelle["importance"] = 3
            for champ in ("resume", "pourquoi_important"):
                nouvelle[champ] = str(nouvelle.get(champ, ""))
            sources = []
            for n in nouvelle.pop("articles", None) or []:
                if isinstance(n, int) and 1 <= n <= len(index):
                    a = index[n - 1]
                    sources.append({"nom": a["source"], "url": a["lien"]})
            nouvelle["sources"] = sources
            nouvelles.append(nouvelle)
        rubrique["nouvelles"] = nouvelles
        rubriques.append(rubrique)
    analyse["rubriques"] = rubriques
    ordre = [r["id"] for r in config["rubriques"]]
    analyse["rubriques"].sort(key=lambda r: ordre.index(r["id"]) if r["id"] in ordre else 99)
    analyse["articles_analyses"] = len(index)
    return analyse


SYSTEME_RADIO = """Tu écris le texte d'un bulletin de nouvelles radiophonique, lu par une voix \
de synthèse québécoise. Le texte est écouté en voiture : il doit se comprendre du premier coup.

Style :
- Phrases courtes, langage parlé mais soigné, ton d'animateur de radio d'information.
- Aucune mise en forme : pas de titres, de puces, d'astérisques, d'émojis ni d'URL.
- Écris les sigles qui se prononcent lettre par lettre avec des points ou en toutes lettres \
  au besoin, et évite les abréviations (écris « millions de dollars », « pour cent »).
- Annonce les transitions entre les rubriques de façon naturelle.
- Cite oralement la source quand c'est utile (« selon Radio-Canada »).
- Base-toi uniquement sur l'analyse fournie; n'ajoute aucun fait.
- Commence par une brève salutation avec la date et l'édition, puis les manchettes. \
  Termine par ce qu'il faut surveiller et une courte formule de fin.
Réponds uniquement avec le texte à lire."""


def rediger_script(config: dict, analyse: dict, edition: str, date_texte: str) -> str:
    minutes = config["editions"][edition]["duree_minutes"]
    mots = minutes * MOTS_PAR_MINUTE
    contenu = {k: analyse[k] for k in ("titre_edition", "resume_executif", "a_surveiller", "rubriques")}
    message = (f"Bulletin du {edition}, {date_texte}. Nom de l'émission : "
               f"{config['podcast']['titre']}.\nDurée visée : environ {minutes} minutes, "
               f"soit à peu près {mots} mots.\n\nAnalyse de l'actualité :\n"
               + json.dumps(contenu, ensure_ascii=False, indent=1))
    script = appeler(config, SYSTEME_RADIO, message).strip()
    if len(script.split()) < 80:
        raise ValueError("Script radio trop court")
    log.info("Script radio : %d mots", len(script.split()))
    return script
