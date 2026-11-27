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
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

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


# --- Mise à jour en place avec relance (build 3) ---------------------
# Windows interdit d'écraser ou d'effacer un exe qui roule, mais
# permet de le RENOMMER. La danse : le nouvel exe arrive sous
# « LecteurOSBD.new », l'exe courant se renomme en « .old », le
# « .new » prend la place, on relance, et la nouvelle instance
# efface le « .old » à son démarrage. Avant le build 3, la mise à
# jour écrivait par-dessus l'exe en cours → « [Errno 13] Permission
# denied » (vu le 2026-11-26).


def est_fige() -> bool:
    """Vrai quand l'app roule comme exe PyInstaller (pas en sources)."""
    return bool(getattr(sys, "frozen", False))


def chemin_exe_courant() -> Path:
    return Path(sys.executable)


def chemin_nouveau(exe_courant: Path) -> Path:
    return exe_courant.with_suffix(".new")


def _supprimer_ou_ecarter(chemin: Path) -> None:
    """Supprime un fichier, avec petits réessais (l'ancien processus
    peut le tenir encore quelques instants) ; à défaut, l'écarte sous
    un nom unique pour libérer le nom d'origine — le nettoyage de
    démarrage finira le travail. Ne lève que si même l'écartement
    échoue."""
    for tentative in range(3):
        try:
            chemin.unlink()
            return
        except OSError:
            if tentative < 2:
                time.sleep(0.3)
    if chemin.exists():
        chemin.rename(chemin.with_name(
            f"{chemin.name}.reste-{int(time.time() * 1000)}"))


def preparer_bascule(exe_courant: Path, nouveau: Path) -> Path:
    """Renomme l'exe courant en « .old » et le nouveau téléchargé à sa
    place. Retourne le chemin à relancer (l'exe courant, nouveau
    contenu). Lève OSError si un renommage échoue — dans ce cas rien
    n'est relancé et l'app reste sur l'ancien exe si la première
    étape n'a pas eu lieu."""
    ancien = exe_courant.with_suffix(".old")
    if ancien.exists():
        _supprimer_ou_ecarter(ancien)
    exe_courant.rename(ancien)
    try:
        nouveau.rename(exe_courant)
    except OSError:
        ancien.rename(exe_courant)  # marche arrière : on remet l'ancien
        raise
    return exe_courant


def relancer(chemin: Path) -> None:
    subprocess.Popen([str(chemin)], close_fds=True)


def _restes(exe_courant: Path) -> list[Path]:
    """Fichiers laissés par les bascules : le « .old » et le « .new »
    officiels, plus les « .reste-<horodatage> » écartés par
    _supprimer_ou_ecarter."""
    candidats = [exe_courant.with_suffix(s)
                 for s in (".old", ".new")]
    # Les fichiers écartés portent le nom de LEUR fichier d'origine
    # (« LecteurOSBD.old.reste-… »), pas celui de l'exe : on ratisse
    # par la racine commune « LecteurOSBD ».
    candidats += sorted(exe_courant.parent.glob(
        exe_courant.stem + "*.reste-*"))
    return [c for c in candidats if c.exists()]


def _nettoyer_en_arriere_plan(restes: list[Path],
                              delais: tuple[float, ...]) -> None:
    for delai in delais:
        time.sleep(delai)
        survivants = []
        for reste in restes:
            try:
                reste.unlink()
            except OSError:
                if reste.exists():
                    survivants.append(reste)
        restes = survivants
        if not restes:
            return


def nettoyer_restes(exe_courant: Path,
                    delais: tuple[float, ...] = (2.0, 5.0, 15.0, 30.0, 60.0)
                    ) -> list[Path]:
    """Au démarrage : efface les restes des bascules précédentes.

    Build 6 : le nettoyage est ROBUSTE. Le premier essai est immédiat ;
    ce qui résiste (l'ancien processus tient encore son exe pendant
    qu'il se ferme — « l'effacement de l'installation a failed »,
    constaté par Grégoire le 2026-11-26 alors que la mise à jour,
    elle, avait marché) est réessayé en arrière-plan avec des délais
    croissants, en silence : un reste qui traîne ne doit jamais ni
    faire échouer une mise à jour ni déranger l'utilisateur — au pire,
    le prochain démarrage finit le ménage. Retourne les restes encore
    présents après l'essai immédiat."""
    restes = _restes(exe_courant)
    survivants = []
    for reste in restes:
        try:
            reste.unlink()
        except OSError:
            if reste.exists():
                survivants.append(reste)
    if survivants and delais:
        fil = threading.Thread(
            target=_nettoyer_en_arriere_plan,
            args=(survivants, tuple(delais)),
            name="nettoyage-restes", daemon=True)
        fil.start()
    return survivants
