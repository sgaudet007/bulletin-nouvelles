"""Collecte des articles à partir des fils RSS de chaque rubrique."""
from __future__ import annotations

import calendar
import html
import logging
import re
from datetime import datetime, timedelta, timezone

import feedparser
import requests

log = logging.getLogger(__name__)

ENTETES = {"User-Agent": "Mozilla/5.0 (BulletinNouvelles; +https://github.com)"}
_BALISES = re.compile(r"<[^>]+>")
_ESPACES = re.compile(r"\s+")


def _nettoyer(texte: str, limite: int = 400) -> str:
    texte = html.unescape(_BALISES.sub(" ", texte or ""))
    texte = _ESPACES.sub(" ", texte).strip()
    return texte[:limite] + ("…" if len(texte) > limite else "")


def _date(entree) -> datetime | None:
    for cle in ("published_parsed", "updated_parsed"):
        valeur = entree.get(cle)
        if valeur:
            return datetime.fromtimestamp(calendar.timegm(valeur), tz=timezone.utc)
    return None


def _cle_doublon(titre: str) -> str:
    return re.sub(r"[^a-z0-9àâçéèêëîïôûùüÿœ]", "", titre.lower())[:80]


def lire_fil(url: str, depuis: datetime) -> list[dict]:
    try:
        reponse = requests.get(url, headers=ENTETES, timeout=20)
        reponse.raise_for_status()
    except requests.RequestException as err:
        log.warning("Fil ignoré (%s) : %s", url, err)
        return []

    fil = feedparser.parse(reponse.content)
    nom_fil = _nettoyer(fil.feed.get("title", ""), 60)
    articles = []
    for entree in fil.entries:
        publie = _date(entree)
        if not publie or publie < depuis:
            continue  # article non daté ou trop ancien
        titre = _nettoyer(entree.get("title", ""), 220)
        if not titre:
            continue
        source = entree.get("source", {}).get("title") if isinstance(entree.get("source"), dict) else None
        if source:  # Google Actualités ajoute « - Nom du média » au titre
            for sep in (" - ", " – ", " | "):
                if titre.endswith(sep + source):
                    titre = titre[: -len(sep + source)]
        articles.append({
            "titre": titre,
            "source": source or nom_fil or url.split("/")[2],
            "lien": entree.get("link", ""),
            "publie": publie.isoformat() if publie else "",
            "extrait": _nettoyer(entree.get("summary", "")),
        })
    log.info("%3d articles — %s", len(articles), url[:90])
    return articles


def collecter(config: dict, heures: int = 24) -> dict[str, list[dict]]:
    """Retourne {id_rubrique: [articles]} pour les dernières `heures` heures."""
    depuis = datetime.now(timezone.utc) - timedelta(hours=heures)
    maximum = config.get("articles_par_rubrique", 30)
    resultat: dict[str, list[dict]] = {}
    vus: set[str] = set()

    for rubrique in config["rubriques"]:
        articles: list[dict] = []
        for url in rubrique["sources"]:
            for article in lire_fil(url, depuis):
                cle = _cle_doublon(article["titre"])
                if cle in vus:
                    continue
                vus.add(cle)
                articles.append(article)
        articles.sort(key=lambda a: a["publie"], reverse=True)
        resultat[rubrique["id"]] = articles[:maximum]
        log.info("Rubrique %s : %d articles retenus", rubrique["id"], len(resultat[rubrique["id"]]))
    return resultat
