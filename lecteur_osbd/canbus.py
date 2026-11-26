"""Moniteur CAN : analyse des lignes ATMA, décodage DBC Subaru
Global (sous-ensemble opendbc), export CSV compatible SavvyCAN.

Portage de CanDbc.kt / CanLigne.kt (Diag Forester, build 1).
Convention DBC : signaux @1 (little-endian) extraits d'un entier
64 bits lu en little-endian ; angle de volant @0 signé big-endian
sur les 2 premiers octets.
"""
import re
from dataclasses import dataclass, replace

from .hexutil import u8, vers_texte


@dataclass
class TrameCan:
    id: int
    octets: bytes
    horodatage_ms: int

    def ligne_csv(self) -> str:
        return f"{self.horodatage_ms};{self.id:03X};{vers_texte(self.octets)}"


_HEXJ = re.compile(r"^[0-9A-Fa-f]+$")


def analyser_ligne(ligne: str) -> tuple[int, bytes] | None:
    """« 13A 0F 1E 22 … » → (id, données). None si ligne invalide."""
    jetons = [j for j in ligne.strip().split() if j]
    if len(jetons) < 2:
        return None
    id_texte = jetons[0]
    if len(id_texte) > 8 or not _HEXJ.match(id_texte):
        return None
    try:
        can_id = int(id_texte, 16)
    except ValueError:
        return None
    donnees = bytearray()
    for jeton in jetons[1:]:
        if len(jeton) != 2 or not _HEXJ.match(jeton):
            return None
        donnees.append(int(jeton, 16))
    if len(donnees) > 8:
        return None
    return can_id, bytes(donnees)


@dataclass
class EtatCan:
    angle_volant_deg: float | None = None
    regime_tr_min: int | None = None
    pedale_accel_brute: int | None = None
    vitesse_kmh: float | None = None
    pedale_frein_brute: int | None = None
    feux_stop: bool | None = None
    frein_actif: bool | None = None
    frein_eyesight: bool | None = None
    roue_avg: float | None = None
    roue_avd: float | None = None
    roue_arg: float | None = None
    roue_ard: float | None = None

    def vitesse_roue_max(self) -> float | None:
        valeurs = [v for v in (self.roue_avg, self.roue_avd, self.roue_arg, self.roue_ard)
                   if v is not None]
        return max(valeurs) if valeurs else None


ID_VOLANT = 0x002
ID_PEDALES_MOTEUR = 0x040
ID_FREIN = 0x139
ID_ROUES = 0x13A
ID_STATUT_FREIN = 0x13C


def _le64(o: bytes) -> int:
    v = 0
    for i in range(min(8, len(o))):
        v |= o[i] << (8 * i)
    return v


def _extraire(le: int, debut: int, longueur: int) -> int:
    return (le >> debut) & ((1 << longueur) - 1)


def appliquer(etat: EtatCan, can_id: int, o: bytes) -> EtatCan:
    """Applique une trame à l'état ; état inchangé si ID non décodé."""
    if len(o) < 8:
        return etat
    le = _le64(o)
    if can_id == ID_VOLANT:
        brut = (u8(o, 0) << 8) | u8(o, 1)
        signe = brut - 0x10000 if brut >= 0x8000 else brut
        return replace(etat, angle_volant_deg=signe * 0.1)
    if can_id == ID_PEDALES_MOTEUR:
        return replace(etat,
                       regime_tr_min=_extraire(le, 16, 13),
                       pedale_accel_brute=_extraire(le, 32, 8))
    if can_id == ID_FREIN:
        return replace(etat,
                       vitesse_kmh=_extraire(le, 16, 12) * 0.05625,
                       feux_stop=_extraire(le, 34, 1) == 1,
                       pedale_frein_brute=_extraire(le, 36, 12))
    if can_id == ID_ROUES:
        return replace(etat,
                       roue_avd=_extraire(le, 12, 13) * 0.057,
                       roue_ard=_extraire(le, 25, 13) * 0.057,
                       roue_arg=_extraire(le, 38, 13) * 0.057,
                       roue_avg=_extraire(le, 51, 13) * 0.057)
    if can_id == ID_STATUT_FREIN:
        return replace(etat,
                       frein_eyesight=_extraire(le, 58, 1) == 1,
                       frein_actif=_extraire(le, 62, 1) == 1)
    return etat


def decrire(can_id: int, o: bytes) -> str | None:
    """Libellé court des signaux décodés d'une trame, ou None."""
    e = appliquer(EtatCan(), can_id, o)
    if can_id == ID_VOLANT:
        if e.angle_volant_deg is None:
            return None
        return f"angle volant {e.angle_volant_deg:.1f}°"
    if can_id == ID_PEDALES_MOTEUR:
        return f"régime {e.regime_tr_min} tr/min, pédale accel brute {e.pedale_accel_brute}"
    if can_id == ID_FREIN:
        if e.vitesse_kmh is None:
            return None
        return (f"vitesse {e.vitesse_kmh:.1f} km/h, pédale de frein {e.pedale_frein_brute}, "
                f"feux stop {'oui' if e.feux_stop else 'non'}")
    if can_id == ID_ROUES:
        if e.roue_avg is None:
            return None
        return (f"roues AV-G {e.roue_avg:.1f} / AV-D {e.roue_avd:.1f} / "
                f"AR-G {e.roue_arg:.1f} / AR-D {e.roue_ard:.1f} km/h")
    if can_id == ID_STATUT_FREIN:
        return (f"frein {'actif' if e.frein_actif else 'relâché'}, "
                f"frein EyeSight {'actif' if e.frein_eyesight else 'non'}")
    return None


def ligne_savvycan(trame: TrameCan, base_s: float) -> str:
    """Ligne CSV au format que SavvyCAN importe :
    Time Stamp,ID,Extended,Dir,Bus,LEN,D1..D8"""
    rel = trame.horodatage_ms / 1000.0 - base_s
    champs = [f"{rel:.6f}", f"{trame.id:X}", "false", "Rx", "0", str(len(trame.octets))]
    champs += [f"{b}" for b in trame.octets]
    champs += [""] * (8 - len(trame.octets))
    return ",".join(champs)


ENTETE_SAVVYCAN = "Time Stamp,ID,Extended,Dir,Bus,LEN,D1,D2,D3,D4,D5,D6,D7,D8"
