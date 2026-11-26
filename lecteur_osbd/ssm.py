"""SSM-sur-CAN (Subaru Select Monitor encapsulé dans ISO-TP).

Pourquoi ce module existe (recherche du 2026-11-26, voir
NOTES-TERRAIN.md) : sur les Subaru de l'ère CAN, les modules hors
groupe motopropulseur (VDC/ABS, airbag, BIU…) ne parlent pas UDS —
le recensement UDS 0x7E0–0x7E7 du terrain ne trouve que ECM et TCM.
La voie constructeur est le SSM, transporté en ISO-TP à 500 kbit/s,
dont l'adressage CAN suit la table SSM historique :

    adresse SSM 0x10 (ECM)   → requête 0x7E0 / réponse 0x7E8
    adresse SSM 0x18 (TCM)   → requête 0x7E1 / réponse 0x7E9
    adresse SSM 0x20 (VDC)   → requête 0x7E2 / réponse 0x7EA  (présumé)
    adresse SSM 0x28 (airbag)→ requête 0x7E3 / réponse 0x7EB  (présumé)
    adresse SSM 0x30 (BIU)   → requête 0x7E4 / réponse 0x7EC  (présumé)

Sur CAN, la charge utile ne contient que « opcode + arguments » :
l'en-tête/testeur/checksum du SSM série est pris en charge par
ISO-TP. Opcodes documentés par les implémentations ouvertes
(FastECU, SubuwuTuner — validés sur ECM/TCM réels) :

    init : envoi AA        → réponse EA + identifiant + capacités
    lire : envoi A8 00 <adresses de 3 octets…>
                         → réponse E8 <un octet par adresse, en ordre>

LECTURE SEULE : l'opcode d'écriture SSM (B8) n'est pas implémenté.
Le SSM n'a pas de service « lire les DTC » : les codes vivent à des
adresses mémoire propres à chaque module ; pour le VDC de la
plateforme SGP, cette carte n'est publiée nulle part — la première
étape est de prouver que le module répond à l'init.
"""
from dataclasses import dataclass, field

from .hexutil import vers_texte

OP_INIT = 0xAA
OP_INIT_REPONSE = 0xEA
OP_LIRE = 0xA8
OP_LIRE_REPONSE = 0xE8

# (adresse CAN de requête, nom présumé du module)
MODULES_SSM: list[tuple[int, str]] = [
    (0x7E0, "ECM — moteur"),
    (0x7E1, "TCM — transmission"),
    (0x7E2, "VDC / ABS — freins (présumé)"),
    (0x7E3, "Airbag (présumé)"),
    (0x7E4, "BIU — carrosserie (présumé)"),
]


@dataclass
class ResultatInitSsm:
    adresse: int
    nom: str
    repond: bool
    reponse: bytes = b""

    @property
    def adresse_hex(self) -> str:
        return f"{self.adresse:03X}"

    def ligne_affichage(self) -> str:
        if not self.repond:
            return f"{self.adresse_hex} — {self.nom} : silence"
        return (f"{self.adresse_hex} — {self.nom} : RÉPOND (SSM) · "
                f"init = {vers_texte(self.reponse)}")


def construire_lecture(adresses: list[int]) -> bytes:
    """Requête A8 : pad 0x00 (réponse unique) + adresses de 3 octets."""
    requete = bytearray([OP_LIRE, 0x00])
    for adresse in adresses:
        if not 0 <= adresse <= 0xFFFFFF:
            raise ValueError(f"Adresse SSM hors plage : {adresse:#x}")
        requete += adresse.to_bytes(3, "big")
    return bytes(requete)


def analyser_reponse_lecture(reponse: bytes | None,
                             adresses: list[int]) -> list[tuple[int, int]] | None:
    """Réponse E8 → [(adresse, valeur), …]. None si la réponse n'est
    pas une réponse de lecture SSM exploitable."""
    if not reponse or reponse[0] != OP_LIRE_REPONSE:
        return None
    valeurs = reponse[1:]
    return [(adresse, valeurs[i]) for i, adresse in enumerate(adresses)
            if i < len(valeurs)]


def initialiser(session, adresse: int) -> ResultatInitSsm:
    """Init SSM (AA) à une adresse CAN. session = SessionObd."""
    nom = dict(MODULES_SSM).get(adresse, "module inconnu")
    reponse = session.requete_brute(adresse, bytes([OP_INIT]), 3.0)
    repond = bool(reponse) and reponse[0] == OP_INIT_REPONSE
    return ResultatInitSsm(adresse, nom, repond, reponse or b"")


def lire_adresses(session, adresse: int,
                  adresses: list[int]) -> list[tuple[int, int]] | None:
    """Lecture A8 d'une série d'adresses mémoire d'un module SSM."""
    requete = construire_lecture(adresses)
    reponse = session.requete_brute(adresse, requete, 4.0)
    return analyser_reponse_lecture(reponse, adresses)


def recensement_ssm(session) -> list[ResultatInitSsm]:
    """Init SSM aux cinq adresses candidates. Les deux premières
    (ECM/TCM, modules connus) servent de témoins : si elles ne
    répondent pas en SSM, la mécanique elle-même est en doute ;
    si elles répondent et que 0x7E2 aussi, le VDC est trouvé."""
    resultats = []
    for adresse, _nom in MODULES_SSM:
        resultats.append(initialiser(session, adresse))
    session.journal.evenement("recensement_ssm", {
        "modules": [{"adresse": r.adresse_hex, "nom": r.nom,
                     "repond": r.repond,
                     "init": vers_texte(r.reponse)} for r in resultats],
    })
    return resultats


@dataclass
class ResultatSondes:
    directes: list[tuple[int, str]] = field(default_factory=list)
    fonctionnelle: list[str] = field(default_factory=list)

    def lignes_affichage(self) -> list[str]:
        lignes = ["SONDES UDS COMPLÉMENTAIRES (19 02 FF, sans session)"]
        for adresse, classe in self.directes:
            lignes.append(f"{adresse:03X} — {classe}")
        if self.fonctionnelle:
            lignes.append("Fonctionnelle 7DF — réponses brutes :")
            lignes += [f"  {l}" for l in self.fonctionnelle]
        else:
            lignes.append("Fonctionnelle 7DF — aucune réponse")
        return lignes


def sondes_uds_dormantes(session) -> ResultatSondes:
    """Filet de sécurité UDS : un éventuel VDC-UDS « dormant » qui
    ignorerait les sondes de session (0x10/0x3E) peut encore répondre
    à une lecture DTC directe (19 02 FF) ou à l'appel fonctionnel."""
    resultat = ResultatSondes()
    for adresse in range(0x7E2, 0x7E8):
        reponse = session.uds(adresse, bytes([0x19, 0x02, 0xFF]), 3.0)
        # « NO DATA » de l'adaptateur (classe erreur_adaptateur) =
        # le module ne répond pas : un silence, comme au recensement.
        classe = ("silence" if reponse.classe == "erreur_adaptateur"
                  else reponse.classe)
        resultat.directes.append((adresse, classe))
    resultat.fonctionnelle = session.requete_fonctionnelle(
        bytes([0x19, 0x02, 0xFF]), 3.0)
    session.journal.evenement("sondes_uds_dormantes", {
        "directes": {f"{a:03X}": c for a, c in resultat.directes},
        "fonctionnelle": resultat.fonctionnelle,
    })
    return resultat
