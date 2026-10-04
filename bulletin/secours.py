"""Mode de secours sans IA : manchettes brutes, regroupées par rubrique."""
from __future__ import annotations

NOUVELLES_PAR_RUBRIQUE = 5
MANCHETTES_LUES = 3


def analyse_secours(config: dict, articles: dict[str, list[dict]]) -> dict:
    rubriques = []
    for rubrique in config["rubriques"]:
        nouvelles = [{
            "titre": a["titre"],
            "resume": a["extrait"] if a["extrait"] and a["extrait"] not in a["titre"] else "",
            "pourquoi_important": "",
            "importance": 3,
            "sources": [{"nom": a["source"], "url": a["lien"]}],
        } for a in articles.get(rubrique["id"], [])[:NOUVELLES_PAR_RUBRIQUE]]
        rubriques.append({"id": rubrique["id"], "nom": rubrique["nom"], "synthese": "",
                          "nouvelles": nouvelles})
    return {
        "titre_edition": "Les manchettes, sans analyse",
        "resume_executif": ("L'analyse automatique n'a pas pu être produite pour cette édition. "
                            "Voici les principales manchettes, regroupées par rubrique."),
        "a_surveiller": [],
        "rubriques": rubriques,
        "articles_analyses": sum(len(v) for v in articles.values()),
        "mode": "secours",
    }


def script_secours(config: dict, analyse: dict, edition: str, date_texte: str) -> str:
    moment = "ce matin" if edition == "matin" else "en cette fin de journée"
    parties = [f"Bonjour. Voici le {config['podcast']['titre']} du {date_texte}. "
               f"L'analyse automatique n'est pas disponible {moment}, "
               "alors voici simplement les principales manchettes."]
    for rubrique in analyse["rubriques"]:
        if not rubrique["nouvelles"]:
            continue
        lignes = [f"{rubrique['nom']}."]
        for nouvelle in rubrique["nouvelles"][:MANCHETTES_LUES]:
            source = nouvelle["sources"][0]["nom"] if nouvelle["sources"] else ""
            lignes.append(f"Selon {source} : {nouvelle['titre']}." if source else f"{nouvelle['titre']}.")
        parties.append(" ".join(lignes))
    parties.append(f"C'était le {config['podcast']['titre']}. Bonne journée.")
    return "\n\n".join(parties)
