"""PID du mode 01 (données en direct) — portage de PidCodec.kt.

Définitions et formules standard OBD-II, unités métriques.
Dans une réponse mode 01, les données utiles commencent à l'indice 2
(après 0x41 et le PID). En mode 02 (freeze frame), à l'indice 3.
"""
from dataclasses import dataclass
from typing import Callable

from .hexutil import u8


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
