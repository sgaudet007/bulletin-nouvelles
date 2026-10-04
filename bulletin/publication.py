"""Gestion de l'état du site, du flux balado (RSS) et des données du tableau de bord."""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

import requests

log = logging.getLogger(__name__)

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
EDITIONS_CONSERVEES = 30


def date_longue(moment: datetime) -> str:
    jour = "1er" if moment.day == 1 else str(moment.day)
    return f"{JOURS[moment.weekday()]} {jour} {MOIS[moment.month - 1]} {moment.year}"


def url_du_site() -> str:
    """URL publique : SITE_URL si défini, sinon déduite du dépôt GitHub."""
    url = os.environ.get("SITE_URL", "").strip().rstrip("/")
    if not url:
        depot = os.environ.get("GITHUB_REPOSITORY", "utilisateur/bulletin-nouvelles")
        proprietaire, nom = depot.split("/", 1)
        proprietaire = proprietaire.lower()
        if nom.lower() == f"{proprietaire}.github.io":
            url = f"https://{proprietaire}.github.io"
        else:
            url = f"https://{proprietaire}.github.io/{nom}"
    dossier = os.environ.get("SITE_SECRET", "").strip().strip("/")
    return f"{url}/{dossier}" if dossier else url


def dossier_publication(racine: Path) -> Path:
    dossier = os.environ.get("SITE_SECRET", "").strip().strip("/")
    return racine / dossier if dossier else racine


def recuperer_etat(url: str, sortie: Path) -> dict:
    """Télécharge l'état publié et les fichiers à conserver (le site est remplacé à chaque déploiement)."""
    vide = {"episodes": [], "editions": []}
    try:
        reponse = requests.get(f"{url}/data/etat.json", timeout=30)
        if reponse.status_code == 404:
            log.info("Premier déploiement : aucun état précédent.")
            return vide
        reponse.raise_for_status()
        etat = reponse.json()
    except (requests.RequestException, ValueError) as err:
        log.warning("État précédent introuvable (%s); on repart à zéro.", err)
        return vide

    for episode in etat.get("episodes", []):
        _telecharger(f"{url}/audio/{episode['fichier']}", sortie / "audio" / episode["fichier"])
    for edition in etat.get("editions", []):
        _telecharger(f"{url}/data/editions/{edition['id']}.json",
                     sortie / "data" / "editions" / f"{edition['id']}.json")
    # Ne garde que ce qui a bien été récupéré.
    etat["episodes"] = [e for e in etat.get("episodes", [])
                        if (sortie / "audio" / e["fichier"]).exists()]
    etat["editions"] = [e for e in etat.get("editions", [])
                        if (sortie / "data" / "editions" / f"{e['id']}.json").exists()]
    return etat


def _telecharger(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with requests.get(url, timeout=60, stream=True) as reponse:
            reponse.raise_for_status()
            with open(destination, "wb") as fichier:
                for bloc in reponse.iter_content(1 << 16):
                    fichier.write(bloc)
    except requests.RequestException as err:
        log.warning("Impossible de récupérer %s : %s", url, err)
        destination.unlink(missing_ok=True)


def derniere_edition(sortie: Path, etat: dict) -> dict | None:
    if not etat["editions"]:
        return None
    chemin = sortie / "data" / "editions" / f"{etat['editions'][0]['id']}.json"
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ajouter_edition(sortie: Path, etat: dict, edition: dict, episode: dict | None,
                    config: dict) -> dict:
    """Écrit l'édition, met à jour l'état et purge les anciens fichiers."""
    dossier_editions = sortie / "data" / "editions"
    dossier_editions.mkdir(parents=True, exist_ok=True)
    texte = json.dumps(edition, ensure_ascii=False, indent=1)
    (dossier_editions / f"{edition['id']}.json").write_text(texte, encoding="utf-8")
    (sortie / "data" / "derniere.json").write_text(texte, encoding="utf-8")

    etat["editions"] = [e for e in etat["editions"] if e["id"] != edition["id"]]
    etat["editions"].insert(0, {"id": edition["id"], "libelle": edition["edition_libelle"],
                                "date": edition["date"]})
    for ancienne in etat["editions"][EDITIONS_CONSERVEES:]:
        (dossier_editions / f"{ancienne['id']}.json").unlink(missing_ok=True)
    etat["editions"] = etat["editions"][:EDITIONS_CONSERVEES]

    if episode:
        etat["episodes"] = [e for e in etat["episodes"] if e["guid"] != episode["guid"]]
        etat["episodes"].insert(0, episode)
        garder = config["podcast"].get("episodes_conserves", 10)
        for ancien in etat["episodes"][garder:]:
            (sortie / "audio" / ancien["fichier"]).unlink(missing_ok=True)
        etat["episodes"] = etat["episodes"][:garder]

    (sortie / "data" / "etat.json").write_text(
        json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")
    return etat


def ecrire_flux(sortie: Path, etat: dict, config: dict, url: str) -> None:
    p = config["podcast"]
    e = lambda s: escape(str(s))  # noqa: E731
    items = []
    for ep in etat["episodes"]:
        heures, reste = divmod(ep["duree"], 3600)
        duree = f"{heures:02d}:{reste // 60:02d}:{reste % 60:02d}"
        items.append(f"""    <item>
      <title>{e(ep['titre'])}</title>
      <description>{e(ep['description'])}</description>
      <itunes:summary>{e(ep['description'])}</itunes:summary>
      <enclosure url="{e(url)}/audio/{e(ep['fichier'])}" length="{ep['taille']}" type="audio/mpeg"/>
      <guid isPermaLink="false">{e(ep['guid'])}</guid>
      <pubDate>{e(ep['pubdate'])}</pubDate>
      <itunes:duration>{duree}</itunes:duration>
      <itunes:episodeType>full</itunes:episodeType>
      <itunes:explicit>false</itunes:explicit>
      <link>{e(url)}/?edition={e(ep['guid'])}</link>
    </item>""")
    maintenant = format_datetime(datetime.now().astimezone())
    flux = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{e(p['titre'])}</title>
    <link>{e(url)}/</link>
    <atom:link href="{e(url)}/feed.xml" rel="self" type="application/rss+xml"/>
    <description>{e(p['description'])}</description>
    <language>{e(p.get('langue', 'fr-ca'))}</language>
    <lastBuildDate>{maintenant}</lastBuildDate>
    <itunes:author>{e(p['auteur'])}</itunes:author>
    <itunes:summary>{e(p['description'])}</itunes:summary>
    <itunes:image href="{e(url)}/couverture.png"/>
    <image><url>{e(url)}/couverture.png</url><title>{e(p['titre'])}</title><link>{e(url)}/</link></image>
    <itunes:category text="News"><itunes:category text="Daily News"/></itunes:category>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
    <itunes:block>Yes</itunes:block>
{chr(10).join(items)}
  </channel>
</rss>
"""
    (sortie / "feed.xml").write_text(flux, encoding="utf-8")
    log.info("Flux balado : %d épisode(s) — %s/feed.xml", len(etat["episodes"]), url)


def copier_site(gabarit: Path, sortie: Path, racine: Path, config: dict) -> None:
    for fichier in gabarit.iterdir():
        if fichier.is_file():
            shutil.copy2(fichier, sortie / fichier.name)
    (sortie / "data").mkdir(parents=True, exist_ok=True)
    (sortie / "data" / "config.json").write_text(json.dumps({
        "titre": config["podcast"]["titre"],
        "rubriques": [{"id": r["id"], "nom": r["nom"]} for r in config["rubriques"]],
    }, ensure_ascii=False), encoding="utf-8")
    if sortie != racine:  # dossier secret : page racine vide et non indexée
        (racine / "index.html").write_text(
            '<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex">'
            "<title>Page introuvable</title><p>Rien à voir ici.</p>", encoding="utf-8")
    (racine / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")


def nouvel_episode(edition: dict, fichier: Path, duree: int, moment: datetime) -> dict:
    return {
        "guid": edition["id"],
        "titre": f"{edition['edition_libelle']} — {edition['titre_edition']}",
        "description": edition["resume_executif"],
        "fichier": fichier.name,
        "taille": fichier.stat().st_size,
        "duree": duree,
        "pubdate": format_datetime(moment),
    }
