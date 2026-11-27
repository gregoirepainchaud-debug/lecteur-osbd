"""PID du mode 01 (données en direct) — portage de PidCodec.kt.

Définitions et formules standard OBD-II, unités métriques.
Dans une réponse mode 01, les données utiles commencent à l'indice 2
(après 0x41 et le PID). En mode 02 (freeze frame), à l'indice 3.
"""
from dataclasses import dataclass
from typing import Callable

from .hexutil import octets_depuis_lignes, u8


def _a(o: bytes, i: int) -> int:
    return u8(o, i)


def _ab(o: bytes, i: int) -> int:
    return u8(o, i) * 256 + u8(o, i + 1)


@dataclass
class DefinitionPid:
    pid: int
    nom: str
    unite: str
    nb_octets: int
    formule: Callable[[bytes, int], float]

    def demande(self, mode: int, trame: int | None = None) -> str:
        if trame is None:
            return f"{mode:02X}{self.pid:02X}"
        return f"{mode:02X}{self.pid:02X}{trame:02X}"

    def decoder_reponse(self, octets: bytes, mode: int) -> float | None:
        debut = 3 if mode == 0x02 else 2
        if len(octets) < debut + self.nb_octets:
            return None
        return self.formule(octets, debut)


def decoder_lignes(definition: DefinitionPid, lignes: list[str],
                   mode: int = 0x01) -> float | None:
    """Décode la valeur d'un PID depuis les LIGNES de réponse, en
    cherchant le marqueur (0x40 + mode, PID) ligne par ligne — la
    première ligne qui le porte gagne.

    Le décodage à décalage fixe sur la concaténation de toutes les
    lignes (decoder_reponse appliqué au flux complet) est fragile :
    quand deux modules répondent au mode 01, ou qu'une réponse
    tardive d'un autre service traîne dans le tampon, un octet
    étranger en tête décale tout. Vu sur le terrain le 2026-11-26 :
    la vérification d'immobilité a lu « 10 km/h » sur une Subaru
    garée depuis une heure, et l'effacement a été refusé. Ici, seule
    une ligne portant le vrai marqueur est décodée ; sans marqueur,
    la valeur est illisible (None), jamais inventée."""
    marqueur = bytes([0x40 + mode, definition.pid])
    for ligne in lignes:
        octets = octets_depuis_lignes([ligne])
        i = octets.find(marqueur)
        if i < 0:
            continue
        donnees = octets[i:]
        if len(donnees) < 2 + definition.nb_octets:
            continue
        return definition.formule(donnees, 2)
    return None


DEFINITIONS: list[DefinitionPid] = [
    DefinitionPid(0x04, "Charge moteur", "%", 1, lambda o, i: _a(o, i) * 100.0 / 255),
    DefinitionPid(0x05, "Liquide de refroidissement", "°C", 1, lambda o, i: _a(o, i) - 40.0),
    DefinitionPid(0x0C, "Régime moteur", "tr/min", 2, lambda o, i: _ab(o, i) / 4.0),
    DefinitionPid(0x0D, "Vitesse du véhicule", "km/h", 1, lambda o, i: float(_a(o, i))),
    DefinitionPid(0x0F, "Air d'admission", "°C", 1, lambda o, i: _a(o, i) - 40.0),
    DefinitionPid(0x10, "Débit d'air (MAF)", "g/s", 2, lambda o, i: _ab(o, i) / 100.0),
    DefinitionPid(0x11, "Position du papillon", "%", 1, lambda o, i: _a(o, i) * 100.0 / 255),
    DefinitionPid(0x1F, "Temps depuis le démarrage", "s", 2, lambda o, i: float(_ab(o, i))),
    DefinitionPid(0x21, "Distance avec témoin d'anomalie", "km", 2, lambda o, i: float(_ab(o, i))),
    DefinitionPid(0x2F, "Niveau de carburant", "%", 1, lambda o, i: _a(o, i) * 100.0 / 255),
    DefinitionPid(0x33, "Pression barométrique", "kPa", 1, lambda o, i: float(_a(o, i))),
    DefinitionPid(0x42, "Tension du module moteur", "V", 2, lambda o, i: _ab(o, i) / 1000.0),
    DefinitionPid(0x46, "Air ambiant", "°C", 1, lambda o, i: _a(o, i) - 40.0),
    DefinitionPid(0x5C, "Huile moteur", "°C", 1, lambda o, i: _a(o, i) - 40.0),
]


def par_pid(pid: int) -> DefinitionPid | None:
    for d in DEFINITIONS:
        if d.pid == pid:
            return d
    return None


def pid_supportes(octets: bytes, pid_base: int) -> set[int]:
    """PID supportés d'après la réponse à 0x00 / 0x20 / 0x40 (bitmap)."""
    supportes: set[int] = set()
    if len(octets) < 6:
        return supportes
    for octet in range(4):
        valeur = u8(octets, 2 + octet)
        for bit in range(8):
            if valeur & (0x80 >> bit):
                supportes.add(pid_base + octet * 8 + bit + 1)
    return supportes


def formater(definition: DefinitionPid, valeur: float) -> str:
    texte = str(int(valeur)) if valeur == int(valeur) else f"{valeur:.1f}"
    return f"{texte} {definition.unite}".strip()
