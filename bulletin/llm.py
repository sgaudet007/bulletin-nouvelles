"""Appels aux modèles de langage : Gemini (palier gratuit, par défaut) ou Claude (API payante)."""
from __future__ import annotations

import json
import logging
import os
import time

import requests

log = logging.getLogger(__name__)

URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent"


class ErreurLLM(RuntimeError):
    pass


def appeler(config: dict, systeme: str, message: str, schema: dict | None = None) -> str:
    """Retourne le texte produit (du JSON si un schéma est fourni)."""
    fournisseur = config.get("fournisseur", "gemini")
    if fournisseur == "gemini":
        return _gemini(config["gemini"], systeme, message, schema)
    if fournisseur == "claude":
        return _claude(config["claude"], systeme, message, schema)
    raise ErreurLLM(f"Fournisseur inconnu : {fournisseur}")


# ── Gemini ───────────────────────────────────────────────────────────────

def _schema_gemini(schema: dict) -> dict:
    """Convertit un schéma JSON au format « responseSchema » de Gemini."""
    sortie: dict = {}
    for cle, valeur in schema.items():
        if cle == "additionalProperties":
            continue
        if cle == "type":
            sortie["type"] = valeur.upper()
        elif cle == "properties":
            sortie["properties"] = {k: _schema_gemini(v) for k, v in valeur.items()}
            sortie["propertyOrdering"] = list(valeur)
        elif cle == "items":
            sortie["items"] = _schema_gemini(valeur)
        else:
            sortie[cle] = valeur
    return sortie


def _gemini(params: dict, systeme: str, message: str, schema: dict | None) -> str:
    cle = os.environ.get("GEMINI_API_KEY")
    if not cle:
        raise ErreurLLM("Secret GEMINI_API_KEY absent")
    modeles = [params["modele"], *params.get("modeles_secours", [])]
    avec_schema = schema is not None
    derniere_erreur = ""

    for modele in modeles:
        for essai in range(1, 4):
            corps = {
                "systemInstruction": {"parts": [{"text": systeme}]},
                "contents": [{"role": "user", "parts": [{"text": message}]}],
                "generationConfig": {"temperature": 0.4, "maxOutputTokens": 32768},
            }
            if schema is not None:
                corps["generationConfig"]["responseMimeType"] = "application/json"
                if avec_schema:
                    corps["generationConfig"]["responseSchema"] = _schema_gemini(schema)
                else:  # schéma refusé par l'API : on le décrit dans la consigne
                    corps["contents"][0]["parts"][0]["text"] += (
                        "\n\nRéponds uniquement avec un objet JSON conforme à ce schéma :\n"
                        + json.dumps(schema, ensure_ascii=False))
            try:
                reponse = requests.post(URL_GEMINI.format(modele=modele), json=corps, timeout=300,
                                        headers={"x-goog-api-key": cle})
            except requests.RequestException as err:
                derniere_erreur = str(err)
                time.sleep(20 * essai)
                continue

            if reponse.status_code == 400 and avec_schema and "schema" in reponse.text.lower():
                log.warning("Schéma refusé par %s, nouvel essai en mode JSON simple.", modele)
                avec_schema = False
                continue
            if reponse.status_code in (429, 500, 502, 503, 504):
                derniere_erreur = f"{modele} : HTTP {reponse.status_code}"
                attente = 30 * essai
                log.warning("%s — nouvel essai dans %d s.", derniere_erreur, attente)
                time.sleep(attente)
                continue
            if reponse.status_code == 404:
                derniere_erreur = f"{modele} : modèle introuvable"
                log.warning("%s, passage au modèle suivant.", derniere_erreur)
                break
            if not reponse.ok:
                raise ErreurLLM(f"{modele} : HTTP {reponse.status_code} — {reponse.text[:300]}")

            donnees = reponse.json()
            candidats = donnees.get("candidates") or []
            if not candidats:
                raise ErreurLLM(f"Aucune réponse de {modele} : {donnees.get('promptFeedback')}")
            raison = candidats[0].get("finishReason", "")
            texte = "".join(p.get("text", "") for p in candidats[0].get("content", {}).get("parts", [])
                            if not p.get("thought"))
            if raison not in ("STOP", "") or not texte.strip():
                derniere_erreur = f"{modele} : réponse incomplète ({raison})"
                log.warning(derniere_erreur)
                continue
            usage = donnees.get("usageMetadata", {})
            log.info("%s : %s jetons en entrée, %s en sortie", modele,
                     usage.get("promptTokenCount"), usage.get("candidatesTokenCount"))
            return texte
        log.warning("Modèle %s abandonné après plusieurs essais.", modele)
    raise ErreurLLM(f"Gemini indisponible ({derniere_erreur})")


# ── Claude (option payante) ──────────────────────────────────────────────

def _claude(params: dict, systeme: str, message: str, schema: dict | None) -> str:
    import anthropic  # importé seulement si cette option est choisie

    options = {}
    if schema is not None:
        options["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
    reponse = anthropic.Anthropic().messages.create(
        model=params["modele"], max_tokens=16000, system=systeme,
        messages=[{"role": "user", "content": message}], **options)
    if reponse.stop_reason in ("refusal", "max_tokens"):
        raise ErreurLLM(f"Réponse incomplète de Claude ({reponse.stop_reason})")
    return "".join(b.text for b in reponse.content if b.type == "text")


def extraire_json(texte: str) -> dict:
    """Lit le JSON, même entouré de ``` si le modèle en a ajouté."""
    texte = texte.strip()
    if texte.startswith("```"):
        texte = texte.split("\n", 1)[1].rsplit("```", 1)[0]
    debut, fin = texte.find("{"), texte.rfind("}")
    return json.loads(texte[debut:fin + 1])
