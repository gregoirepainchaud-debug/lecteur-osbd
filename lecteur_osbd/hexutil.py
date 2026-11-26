"""Conversions hexadécimales et nettoyage des réponses ELM327/STN.

Portage fidèle de HexUtil.kt / ElmTexte.kt de l'app Android
« Diag Forester » (build 1, 2026-11-20). Logique pure, testée.
"""
import re

_HEX = set("0123456789ABCDEFabcdef")


def vers_octets(texte: str) -> bytes:
    """« 7F 19 31 » ou « 7F1931 » → octets. ValueError si invalide."""
    propre = re.sub(r"[\s,;]", "", texte).upper()
    if len(propre) % 2 != 0 or any(c not in "0123456789ABCDEF" for c in propre):
        raise ValueError(f"Chaîne hexadécimale invalide : « {texte} »")
    return bytes(int(propre[i:i + 2], 16) for i in range(0, len(propre), 2))


def est_hex(texte: str) -> bool:
    try:
        vers_octets(texte)
        return True
    except Exception:
        return False


def vers_texte(octets: bytes, separateur: str = " ") -> str:
    """Octets → « 7F 19 31 »."""
    return separateur.join(f"{b:02X}" for b in octets)


def u8(octets: bytes, i: int) -> int:
    return octets[i] if 0 <= i < len(octets) else 0


# --- Nettoyage des réponses texte de l'adaptateur ---------------------

LIGNES_BRUIT = {"SEARCHING...", "STOPPED", "OK"}


def lignes_utiles(brut: str, commande: str | None = None) -> list[str]:
    """Réponse brute (avec invite « > ») → lignes utiles, dans l'ordre."""
    sans_invite = brut.replace(">", "")
    lignes = []
    for ligne in sans_invite.splitlines():
        ligne = ligne.strip()
        if not ligne or ligne in LIGNES_BRUIT:
            continue
        if commande is not None and ligne.upper() == commande.upper():
            continue
        lignes.append(ligne)
    return lignes


def erreur_connue(lignes: list[str]) -> str | None:
    """Message d'erreur de l'adaptateur ou du bus, ou None."""
    texte = " ".join(lignes).upper()
    if "NO DATA" in texte:
        return "NO DATA (aucune réponse du véhicule)"
    if "UNABLE TO CONNECT" in texte:
        return "UNABLE TO CONNECT (connexion au bus impossible)"
    if "CAN ERROR" in texte:
        return "CAN ERROR (erreur du bus CAN)"
    if "BUS BUSY" in texte:
        return "BUS BUSY"
    if "BUFFER FULL" in texte:
        return "BUFFER FULL (tampon de l'adaptateur débordé)"
    if "FB ERROR" in texte:
        return "FB ERROR"
    if texte.strip() == "?":
        return "? (commande non reconnue par l'adaptateur)"
    return None


_COMPTEUR_LIGNE = re.compile(r"^\s*[0-9A-Fa-f]\s*:")


def octets_depuis_lignes(lignes: list[str]) -> bytes:
    """Extrait les octets d'une réponse OBD/UDS : concatène les jetons
    hexadécimaux de toutes les lignes (compteurs « 0: » retirés)."""
    morceaux = bytearray()
    for ligne_brute in lignes:
        ligne = _COMPTEUR_LIGNE.sub("", ligne_brute)
        propre = re.sub(r"[^0-9A-Fa-f]", "", ligne)
        if not propre or len(propre) % 2 != 0:
            continue
        if any(c not in _HEX for c in propre):
            continue
        morceaux.extend(vers_octets(propre))
    return bytes(morceaux)
