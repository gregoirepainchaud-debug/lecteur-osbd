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
        return f"{self.code} — {d}" if d else self.code


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
    codes: dict[str, CodeDefaut] = {}
    i = 1
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
