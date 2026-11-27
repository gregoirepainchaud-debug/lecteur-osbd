"""UDS (ISO 14229) sur ISO-TP — portage de UdsCodec.kt + aides de
tramage ISO-TP (ISO 15765-2) pour valider les flux.

L'adaptateur ELM/STN gère la segmentation ISO-TP et le contrôle de
flux ; les fonctions de tramage ci-dessous servent à construire /
vérifier les trames ISO-TP brutes (tests, console avancée).
"""
from dataclasses import dataclass, field

from .dtc import CodeDefaut, decoder as decoder_dtc
from .hexutil import u8

# --- Codes de réponse négative (NRC) ISO 14229 — libellés français ----

NRC_LIBELLES = {
    0x10: "rejet général",
    0x11: "service non supporté",
    0x12: "sous-fonction non supportée",
    0x13: "longueur ou format de message incorrect",
    0x14: "réponse trop longue",
    0x21: "occupé — répéter la demande",
    0x22: "conditions non remplies",
    0x24: "séquence de demande incorrecte",
    0x25: "pas de réponse d'un sous-réseau",
    0x26: "défaillance empêchant l'action",
    0x31: "demande hors plage (paramètre ou DID inconnu)",
    0x33: "accès de sécurité refusé",
    0x35: "clé de sécurité invalide",
    0x36: "nombre d'essais de sécurité dépassé",
    0x37: "délai de sécurité non écoulé",
    0x70: "transfert refusé",
    0x72: "échec de programmation général",
    0x78: "réponse en attente (le module travaille)",
    0x7E: "sous-fonction non supportée dans cette session",
    0x7F: "service non supporté dans cette session",
}


def decrire_nrc(nrc: int) -> str:
    return NRC_LIBELLES.get(nrc, "code NRC non documenté")


# --- Résultat d'une requête UDS ----------------------------------------


@dataclass
class ResultatUds:
    classe: str  # "positive" | "refus" | "silence" | "erreur_adaptateur"
    octets: bytes = b""
    service: int = 0
    nrc: int = 0
    message: str = ""

    @property
    def description_nrc(self) -> str:
        return decrire_nrc(self.nrc)

    @classmethod
    def positive(cls, octets: bytes) -> "ResultatUds":
        return cls("positive", octets=octets)

    @classmethod
    def refus(cls, service: int, nrc: int, octets: bytes = b"") -> "ResultatUds":
        # Les octets du refus sont CONSERVÉS (build 6) : avant, un
        # refus ne gardait ni ses octets ni trace écrite de son NRC —
        # le journal de session affichait une réponse vide et il a été
        # impossible, le 2026-11-26, de distinguer un 0x78 « en
        # attente » d'un refus sec à la relecture du journal.
        return cls("refus", octets=octets, service=service, nrc=nrc)

    @classmethod
    def silence(cls) -> "ResultatUds":
        return cls("silence")

    @classmethod
    def erreur_adaptateur(cls, message: str) -> "ResultatUds":
        return cls("erreur_adaptateur", message=message)


# --- Construction des requêtes ------------------------------------------

DID_VIN = 0xF190
DID_NUMERO_PIECE = 0xF187
DID_NIVEAU_LOGICIEL = 0xF189


def requete_tester_present() -> bytes:
    return bytes([0x3E, 0x00])


def requete_lire_did(did: int) -> bytes:
    return bytes([0x22, (did >> 8) & 0xFF, did & 0xFF])


def requete_lire_dtc(masque: int = 0xFF) -> bytes:
    """Lecture des DTC par masque de statut (0xFF = tous)."""
    return bytes([0x19, 0x02, masque & 0xFF])


def requete_effacer_dtc() -> bytes:
    """Effacement de tous les groupes de DTC."""
    return bytes([0x14, 0xFF, 0xFF, 0xFF])


# --- Analyse des réponses ------------------------------------------------


def classifier(octets: bytes, service_attendu: int) -> ResultatUds:
    """Classe une réponse brute (déjà réassemblée par l'adaptateur)."""
    if not octets:
        return ResultatUds.silence()
    premier = u8(octets, 0)
    if premier == 0x7F and len(octets) >= 3:
        return ResultatUds.refus(u8(octets, 1), u8(octets, 2), octets)
    # Positif attendu (service + 0x40) ou toute autre réponse livrée
    # telle quelle : rapportée comme positive non classée, comme
    # dans le build Android.
    return ResultatUds.positive(octets)


def classifier_avec_suite(octets: bytes, service_attendu: int
                          ) -> tuple[ResultatUds, bool]:
    """Classification d'une lecture qui peut contenir DEUX réponses :
    un « en attente » (7F ·· 78) suivi, dans la même lecture, de la
    vraie réponse du module.

    C'est le comportement réel du VDC du Forester via l'adaptateur
    (terrain du 2026-11-26, session de 22 h) : l'adaptateur livre le
    0x78 ET la réponse complète, collés dans le même tampon. Le
    build 6 classait sur les 3 premiers octets (« refus 0x78 ») puis
    écoutait 8 s une réponse déjà reçue. Ici : si la suite après le
    cadre NRC se classe de façon définitive, c'est ELLE le résultat.

    La suite n'est acceptée comme positive que si elle commence par
    l'octet de réponse positive attendu (service + 0x40) : un reste
    de bourrage ne doit jamais devenir un faux « positif ».
    Retourne (résultat, vrai si la suite a fourni le résultat)."""
    resultat = classifier(octets, service_attendu)
    if (resultat.classe == "refus" and resultat.nrc == 0x78
            and len(octets) > 3):
        suite = octets[3:]
        candidat = classifier(suite, service_attendu)
        if candidat.classe == "refus" and candidat.nrc != 0x78:
            return candidat, True
        if (candidat.classe == "positive"
                and suite[0] == ((service_attendu + 0x40) & 0xFF)):
            return candidat, True
    return resultat, False


def analyser_lire_did(octets: bytes) -> tuple[int, bytes] | None:
    """Réponse à ReadDataByIdentifier : (DID, données utiles)."""
    if len(octets) < 3 or u8(octets, 0) != 0x62:
        return None
    did = u8(octets, 1) * 256 + u8(octets, 2)
    return did, octets[3:]


def analyser_dtc(octets: bytes, origine: str) -> list[CodeDefaut]:
    """Réponse à ReadDTCInformation (0x59 0x02) : masque de disponibilité
    puis enregistrements de 4 octets (3 de code + 1 de statut)."""
    if len(octets) < 3 or u8(octets, 0) != 0x59 or u8(octets, 1) != 0x02:
        return []
    codes = []
    i = 3
    while i + 3 <= len(octets) - 1:
        b1, b2, b3 = u8(octets, i), u8(octets, i + 1), u8(octets, i + 2)
        statut = u8(octets, i + 3)
        if b1 == 0 and b2 == 0 and b3 == 0:
            i += 4
            continue
        # Le code DTC UDS tient sur les 2 premiers octets au format
        # OBD ; le 3e octet est un type/extension (souvent 0).
        codes.append(CodeDefaut(decoder_dtc(b1, b2), origine, statut))
        i += 4
    return codes


def texte_did(octets: bytes) -> str:
    """Texte lisible d'un DID texte (VIN, numéro de pièce)."""
    return "".join(chr(b) for b in octets if 0x20 <= b <= 0x7E).strip()


# --- ISO-TP (ISO 15765-2) : tramage brut ---------------------------------


def isotp_encadrer(payload: bytes) -> list[bytes]:
    """Découpe un payload UDS en trames CAN ISO-TP (trame unique si
    ≤ 7 octets, sinon première trame + trames consécutives)."""
    if len(payload) <= 7:
        return [bytes([len(payload)]) + payload]
    trames = [bytes([0x10 | ((len(payload) >> 8) & 0x0F), len(payload) & 0xFF]) + payload[:6]]
    reste = payload[6:]
    compteur = 1
    while reste:
        trames.append(bytes([0x20 | (compteur & 0x0F)]) + reste[:7])
        reste = reste[7:]
        compteur += 1
    return trames


@dataclass
class ReassembleurIsotp:
    """Réassemble un flux de trames CAN ISO-TP en payload UDS."""

    _attendu: int = 0
    _tampon: bytearray = field(default_factory=bytearray)
    _prochain: int = 1

    def nourrir(self, trame: bytes) -> bytes | None:
        if not trame:
            return None
        type_trame = (trame[0] >> 4) & 0x0F
        if type_trame == 0x0:  # trame unique
            longueur = trame[0] & 0x0F
            return bytes(trame[1:1 + longueur])
        if type_trame == 0x1:  # première trame
            if len(trame) < 2:
                return None
            self._attendu = ((trame[0] & 0x0F) << 8) | trame[1]
            self._tampon = bytearray(trame[2:])
            self._prochain = 1
            return self._verifier()
        if type_trame == 0x2:  # trame consécutive
            if (trame[0] & 0x0F) != (self._prochain & 0x0F):
                self._attendu = 0
                self._tampon = bytearray()
                return None
            self._tampon.extend(trame[1:])
            self._prochain += 1
            return self._verifier()
        return None  # contrôle de flux ou inconnu : ignoré ici

    def _verifier(self) -> bytes | None:
        if self._attendu and len(self._tampon) >= self._attendu:
            payload = bytes(self._tampon[:self._attendu])
            self._attendu = 0
            self._tampon = bytearray()
            return payload
        return None
