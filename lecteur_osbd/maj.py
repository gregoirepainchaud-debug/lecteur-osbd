"""Vérification de mise à jour — règle de Grégoire : chaque app
maison expose un bouton « Mettre à jour l'app » VISIBLE.

Le bouton (dans la barre principale de l'interface, pas dans un
menu) interroge la dernière Release GitHub du dépôt, compare son
numéro de build au tampon courant, et :
- build plus récent → propose le téléchargement direct du nouvel
  exe ou l'ouverture de la page de la release ;
- à jour → le dit clairement ;
- jamais de mise à jour silencieuse.
"""
import json
import re
import urllib.request

from . import buildinfo

API_RELEASES = f"https://api.github.com/repos/{buildinfo.GITHUB_REPO}/releases/latest"
PAGE_RELEASES = f"https://github.com/{buildinfo.GITHUB_REPO}/releases"


def numero_build_depuis_tag(tag: str) -> int | None:
    """« build-12 » ou « v12 » → 12 ; None si non reconnu."""
    m = re.search(r"(\d+)", tag or "")
    return int(m.group(1)) if m else None


def comparer(build_courant: int, build_distant: int | None) -> str:
    """« nouveau » | « a_jour » | « inconnu »."""
    if build_distant is None:
        return "inconnu"
    return "nouveau" if build_distant > build_courant else "a_jour"


def derniere_release(delai_s: float = 10.0) -> dict:
    """Dernière release GitHub : {tag, numero, nom, page, exe:{nom,url,taille}}."""
    requete = urllib.request.Request(
        API_RELEASES,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": f"{buildinfo.APP_NAME}/{buildinfo.VERSION}"})
    with urllib.request.urlopen(requete, timeout=delai_s) as reponse:
        donnees = json.loads(reponse.read().decode("utf-8"))
    exe = None
    for asset in donnees.get("assets", []):
        if asset.get("name", "").lower().endswith(".exe"):
            exe = {"nom": asset["name"],
                   "url": asset["browser_download_url"],
                   "taille": asset.get("size", 0)}
            break
    return {
        "tag": donnees.get("tag_name", ""),
        "numero": numero_build_depuis_tag(donnees.get("tag_name", "")),
        "nom": donnees.get("name", ""),
        "page": donnees.get("html_url", PAGE_RELEASES),
        "exe": exe,
    }


def telecharger(url: str, destination, delai_s: float = 120.0) -> None:
    requete = urllib.request.Request(
        url, headers={"User-Agent": f"{buildinfo.APP_NAME}/{buildinfo.VERSION}"})
    with urllib.request.urlopen(requete, timeout=delai_s) as reponse, \
            open(destination, "wb") as fichier:
        while True:
            bloc = reponse.read(65536)
            if not bloc:
                break
            fichier.write(bloc)
