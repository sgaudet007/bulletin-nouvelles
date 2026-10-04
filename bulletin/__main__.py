"""Point d'entrée : python -m bulletin [--edition matin|soir|auto] [--planifie] [--demo] [--sans-audio]"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from . import publication as pub

RACINE_PROJET = Path(__file__).resolve().parent.parent
FUSEAU = ZoneInfo("America/Toronto")
log = logging.getLogger("bulletin")


def choisir_edition(demande: str, planifie: bool, config: dict, maintenant: datetime) -> str | None:
    if demande in ("matin", "soir"):
        return demande
    for nom, params in config["editions"].items():
        if maintenant.hour == params["heure"]:
            return nom
    if planifie:
        return None  # déclenchement hors de l'heure locale prévue (changement d'heure)
    return "matin" if maintenant.hour < 12 else "soir"


def signaler_publication(valeur: bool) -> None:
    sortie = os.environ.get("GITHUB_OUTPUT")
    if sortie:
        with open(sortie, "a", encoding="utf-8") as f:
            f.write(f"publie={'true' if valeur else 'false'}\n")


def silence_demo(destination: Path) -> int:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "anullsrc=r=24000:cl=mono", "-t", "5", "-b:a", "48k", str(destination)], check=True)
    return 5


def main() -> int:
    parser = argparse.ArgumentParser(description="Produit le bulletin de nouvelles.")
    parser.add_argument("--edition", default="auto", choices=["auto", "matin", "soir"])
    parser.add_argument("--planifie", action="store_true", help="Exécution déclenchée par l'horaire")
    parser.add_argument("--demo", action="store_true", help="Données de démonstration, sans API")
    parser.add_argument("--sans-audio", action="store_true")
    parser.add_argument("--sortie", default="public")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    config = yaml.safe_load((RACINE_PROJET / "config.yaml").read_text(encoding="utf-8"))
    maintenant = datetime.now(FUSEAU)

    edition = choisir_edition(args.edition, args.planifie, config, maintenant)
    if not edition:
        log.info("Heure locale %s : aucune édition prévue, rien à faire.", maintenant.strftime("%H:%M"))
        signaler_publication(False)
        return 0

    identifiant = f"{maintenant:%Y-%m-%d}-{edition}"
    date_texte = pub.date_longue(maintenant)
    libelle = f"{'Matin' if edition == 'matin' else 'Fin de journée'} — {date_texte}"
    log.info("Édition : %s", libelle)

    racine = Path(args.sortie).resolve()
    shutil.rmtree(racine, ignore_errors=True)
    sortie = pub.dossier_publication(racine)
    (sortie / "audio").mkdir(parents=True, exist_ok=True)

    url = pub.url_du_site()
    etat = pub.recuperer_etat(url, sortie)
    if args.planifie and any(e["id"] == identifiant for e in etat["editions"]):
        log.info("L'édition %s est déjà publiée.", identifiant)
        signaler_publication(False)
        return 0
    precedente = pub.derniere_edition(sortie, etat)

    if args.demo:
        analyse = json.loads((RACINE_PROJET / "demo" / "analyse_demo.json").read_text(encoding="utf-8"))
        script = (RACINE_PROJET / "demo" / "script_demo.txt").read_text(encoding="utf-8")
    else:
        from .analyse import analyser, rediger_script
        from .collecte import collecter
        from .secours import analyse_secours, script_secours

        heures = 24
        if precedente and precedente.get("date"):
            ecart = maintenant - datetime.fromisoformat(precedente["date"])
            heures = int(min(24, max(8, ecart / timedelta(hours=1) + 2)))
        articles = collecter(config, heures=heures)
        if not any(articles.values()):
            log.error("Aucun article collecté : vérifie les sources dans config.yaml.")
            return 1
        sans_ia = config.get("fournisseur") == "aucun"
        try:
            if sans_ia:
                raise RuntimeError("fournisseur « aucun » choisi dans config.yaml")
            analyse = analyser(config, articles, edition, date_texte, precedente)
        except Exception as err:
            log.error("Analyse impossible, passage au mode de secours sans IA : %s", err)
            analyse = analyse_secours(config, articles)
        try:
            if sans_ia or analyse.get("mode") == "secours":
                raise RuntimeError("mode de secours")
            script = rediger_script(config, analyse, edition, date_texte)
        except Exception as err:
            if not sans_ia and analyse.get("mode") != "secours":
                log.error("Script radio impossible, lecture des manchettes à la place : %s", err)
            script = script_secours(config, analyse, edition, date_texte)

    donnees = {
        "id": identifiant,
        "edition": edition,
        "edition_libelle": libelle,
        "date": maintenant.isoformat(timespec="minutes"),
        **analyse,
        "script": script,
        "audio": None,
    }

    episode = None
    if not args.sans_audio:
        fichier = sortie / "audio" / f"{identifiant}.mp3"
        try:
            if args.demo:
                try:
                    from .audio import produire_audio
                    duree = produire_audio(script, config, fichier, essais=1)
                except Exception:
                    duree = silence_demo(fichier)
            else:
                from .audio import produire_audio
                duree = produire_audio(script, config, fichier)
            donnees["audio"] = {"fichier": fichier.name, "duree": duree}
            episode = pub.nouvel_episode(donnees, fichier, duree, maintenant)
        except Exception as err:
            log.error("Audio non produit, le tableau de bord sera publié sans épisode : %s", err)

    etat = pub.ajouter_edition(sortie, etat, donnees, episode, config)
    pub.copier_site(RACINE_PROJET / "site", sortie, racine, config)
    pub.ecrire_flux(sortie, etat, config, url)
    log.info("Tableau de bord : %s/", url)
    signaler_publication(True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
