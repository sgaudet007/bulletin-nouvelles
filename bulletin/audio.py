"""Synthèse vocale du bulletin (voix neuronales Microsoft Edge, gratuites)."""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import edge_tts
from mutagen.mp3 import MP3

log = logging.getLogger(__name__)


async def _synthetiser(texte: str, voix: str, vitesse: str, destination: Path) -> None:
    communication = edge_tts.Communicate(texte, voix, rate=vitesse)
    await communication.save(str(destination))


def produire_audio(texte: str, config: dict, destination: Path, essais: int = 3) -> int:
    """Crée le MP3 et retourne sa durée en secondes."""
    voix = config["voix"]["nom"]
    vitesse = config["voix"].get("vitesse", "+0%")
    for essai in range(1, essais + 1):
        try:
            asyncio.run(_synthetiser(texte, voix, vitesse, destination))
            duree = int(MP3(destination).info.length)
            log.info("Audio : %s (%d s, %.1f Mo)", destination.name, duree,
                     destination.stat().st_size / 1e6)
            return duree
        except Exception as err:  # réseau instable : on réessaie
            log.warning("Synthèse vocale, essai %d/%d échoué : %s", essai, essais, err)
            time.sleep(10 * essai)
    raise RuntimeError("La synthèse vocale a échoué après plusieurs essais")
