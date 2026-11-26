"""Décodage des DTC — portage de DtcCodec.kt. Logique pure.

Format standard : 2 octets, les 2 premiers bits donnent la lettre
(00=P, 01=C, 10=B, 11=U), puis 3 chiffres hexadécimaux.
"""
from dataclasses import dataclass

from . import codes_base
from .hexutil import u8


@dataclass
class CodeDefaut:
    code: str
    origine: str
    statut: int | None = None

    @property
    def description(self) -> str:
        return codes_base.decrire(self.code)

    def ligne_affichage(self) -> str:
        d = self.description
        base = f"{self.code} — {d}" if d else self.code
        if self.statut is not None:
            base += f"  [{texte_statut(self.statut)}]"
        return base


# Bits de l'octet de statut UDS (ISO 14229, DTCStatusMask) :
# 0x01 testFailed (en train de faillir), 0x02 testFailedThisOperationCycle,
# 0x04 pendingDTC, 0x08 confirmedDTC, 0x10 testNotCompletedSinceLastClear,
# 0x20 testFailedSinceLastClear, 0x40 testNotCompletedThisOperationCycle,
# 0x80 warningIndicatorRequested. Un enregistrement dont AUCUN bit de
# panne (0x01/0x02/0x04/0x08/0x20) n'est levé est une simple ligne du
# dictionnaire des codes supportés — pas une panne (leçon du terrain,
# 2026-11-26 : les modules Denso répondent leur catalogue complet au
# masque 0xFF).
MASQUE_PANNE = 0x01 | 0x02 | 0x04 | 0x08 | 0x20


def est_reel(statut: int | None) -> bool:
    """Vrai si l'enregistrement témoigne d'une panne présente ou passée."""
    return statut is not None and (statut & MASQUE_PANNE) != 0


def texte_statut(statut: int) -> str:
    morceaux = []
    if statut & 0x01:
        morceaux.append("actif")
    if statut & 0x08:
        morceaux.append("confirmé")
    if statut & 0x04:
        morceaux.append("en attente")
    if statut & 0x20 and not (statut & 0x01):
        morceaux.append("historique")
    if not morceaux:
        morceaux.append("supporté, jamais en panne")
    return " · ".join(morceaux)


def decoder(octet1: int, octet2: int) -> str:
    lettre = {0: "P", 1: "C", 2: "B"}.get(octet1 >> 6, "U")
    d1 = (octet1 >> 4) & 0x3
    return f"{lettre}{d1}{octet1 & 0xF:X}{octet2:02X}"


def decoder_octets(octets: bytes, offset: int) -> str:
    return decoder(u8(octets, offset), u8(octets, offset + 1))


def analyser_reponse_mode(octets: bytes, origine: str) -> list[CodeDefaut]:
    """Réponse aux modes 03 (43), 07 (47) et 0A (4A) : après l'octet de
    réponse, des paires d'octets (zéro de remplissage possible à la fin)."""
    if len(octets) < 3:
        return []
    # Alignement : l'octet de réponse (0x43/0x47/0x4A) doit être trouvé
    # en position 0 — ou en position 1 si un octet parasite le précède
    # (décalage vu sur le terrain le 2026-11-26 : le parseur lisait
    # l'octet de réponse comme la 2e moitié d'un code, d'où de faux
    # P0043/P0047/P004A). Sans octet de réponse repérable : rien.
    if u8(octets, 0) in (0x43, 0x47, 0x4A):
        depart = 1
    elif u8(octets, 1) in (0x43, 0x47, 0x4A):
        depart = 2
    else:
        return []
    codes: dict[str, CodeDefaut] = {}
    i = depart
    while i + 1 <= len(octets) - 1:
        a, b = u8(octets, i), u8(octets, i + 1)
        if a == 0 and b == 0:
            i += 2
            continue
        code = decoder(a, b)
        codes.setdefault(code, CodeDefaut(code, origine))
        i += 2
    return list(codes.values())


def kilometrage_pid_a6(octets: bytes) -> float | None:
    """Kilométrage mode 01 PID 0xA6 (si publié) : 4 octets, km/10."""
    if len(octets) < 6:
        return None
    brut = (u8(octets, 2) << 24) | (u8(octets, 3) << 16) | (u8(octets, 4) << 8) | u8(octets, 5)
    return brut / 10.0
