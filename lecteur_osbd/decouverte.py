"""Découverte fonctionnelle et accès ciblé aux modules hors 0x7E0.

Percée du terrain, 2026-11-26 au soir (voir NOTES-TERRAIN.md) : sur
le Forester SK, le recensement physique 0x7E0–0x7E7 ne trouve que
l'ECM et le TCM parce que les autres modules vivent à des adresses
UDS propriétaires. L'appel FONCTIONNEL « lire les DTC » (19 02 FF à
0x7DF) les fait tous répondre sous leur ID de réponse — dont le VDC
à 0x7B0 (réponse 0x7B8), en UDS standard, avec ses codes châssis
confirmés (C1954/C1955/C1984). L'init SSM-sur-CAN, elle, est muette
partout sur cette génération, témoins ECM/TCM inclus.

Ce module fournit :
- l'analyse des lignes brutes de la sonde fonctionnelle (réassemblage
  ISO-TP par ID de réponse, NRC 0x78 « en attente » traversé) ;
- la cartographie complète (sonde + identité DID de chaque module) ;
- l'accès ciblé à un module : identité, codes, effacement (0x14),
  sondes d'accès en OBSERVATION (session étendue, demande de graine
  SecurityAccess — aucune clé n'est jamais calculée ni envoyée) ;
- uds_attente : une requête UDS qui traverse les réponses
  « en attente » (NRC 0x78) en réessayant, comme le font les outils
  d'atelier.

Aucune commande d'actionneur ici : lectures, effacement de codes
(archivé par l'appelant) et sondes d'état seulement.
"""
import time
from dataclasses import dataclass, field

from . import uds as uds_mod
from .dtc import CodeDefaut, est_reel
from .hexutil import vers_texte
from .uds import ResultatUds

ADRESSE_VDC = 0x7B0

# Noms établis : 7E0/7E1 par le recensement des builds 1–2, 7B0 par la
# preuve de terrain du 2026-11-26 (codes de la famille VDC/EPB du
# manuel d'atelier), 7C4 par le code B14A1 (capteur d'ensoleillement,
# surveillé par le module de climatisation — manuel d'atelier).
NOMS_MODULES = {
    0x7E0: "ECM — moteur",
    0x7E1: "TCM — transmission",
    0x7B0: "VDC / ABS — freins",
    0x7C4: "Climatisation (A/C)",
}


def nom_module(adresse_requete: int) -> str:
    return NOMS_MODULES.get(adresse_requete, "Module à identifier")


@dataclass
class ModuleDecouvert:
    reponse: int                       # ID CAN de réponse (ex. 0x7B8)
    codes: list[CodeDefaut] = field(default_factory=list)  # tous les enregistrements
    attente_vue: bool = False          # un NRC 0x78 a précédé la réponse
    refus_nrc: int | None = None       # refus sec (7F …) sans données
    piece: str | None = None           # DID F187
    logiciel: str | None = None        # DID F189
    vin_lu: str | None = None          # DID F190

    @property
    def requete(self) -> int:
        return self.reponse - 8

    @property
    def requete_hex(self) -> str:
        return f"{self.requete:03X}"

    @property
    def nom(self) -> str:
        return nom_module(self.requete)

    @property
    def codes_reels(self) -> list[CodeDefaut]:
        return [c for c in self.codes if est_reel(c.statut)]

    def ligne_affichage(self) -> str:
        morceaux = [f"{self.requete_hex} → rép. {self.reponse:03X} — {self.nom}"]
        if self.piece:
            morceaux.append(f"pièce {self.piece}")
        if self.logiciel:
            morceaux.append(f"logiciel {self.logiciel}")
        if self.vin_lu:
            morceaux.append(f"VIN {self.vin_lu}")
        ligne = " · ".join(morceaux)
        reels = self.codes_reels
        if reels:
            ligne += f"\n    {len(reels)} code(s) réel(s) :"
            for c in reels:
                ligne += f"\n      {c.ligne_affichage()}"
        elif self.refus_nrc is not None:
            ligne += (f"\n    répond par un refus — NRC 0x{self.refus_nrc:02X} "
                      f"({uds_mod.decrire_nrc(self.refus_nrc)})")
        elif self.codes:
            ligne += (f"\n    aucun code réel "
                      f"({len(self.codes)} enregistrement(s) au dictionnaire du module)")
        else:
            ligne += "\n    aucun code"
        if self.attente_vue:
            ligne += "\n    (le module a d'abord répondu « en attente » — NRC 0x78)"
        return ligne


def _analyser_ligne(ligne: str) -> tuple[int, bytes] | None:
    """« 7B8 10 0F 59 … » → (0x7B8, trame). None si la ligne n'est pas
    une trame adressée (bruit d'adaptateur, écho, texte)."""
    jetons = ligne.split()
    if len(jetons) < 2:
        return None
    try:
        can_id = int(jetons[0], 16)
        trame = bytes(int(j, 16) for j in jetons[1:])
    except ValueError:
        return None
    if not (0 <= can_id <= 0x7FF) or not trame:
        return None
    return can_id, trame


def analyser_lignes_fonctionnelles(lignes: list[str]) -> list[ModuleDecouvert]:
    """Réassemble les réponses ISO-TP de la sonde fonctionnelle et
    retourne un ModuleDecouvert par ID de réponse ayant livré un
    payload UDS classifiable (59 02 ou 7F). Les trames d'un même
    module peuvent être entrelacées avec celles des autres ; un
    NRC 0x78 en trame unique précède souvent la vraie réponse."""
    reassembleurs: dict[int, uds_mod.ReassembleurIsotp] = {}
    modules: dict[int, ModuleDecouvert] = {}

    def module(can_id: int) -> ModuleDecouvert:
        if can_id not in modules:
            modules[can_id] = ModuleDecouvert(reponse=can_id)
        return modules[can_id]

    for ligne in lignes:
        analyse = _analyser_ligne(ligne)
        if analyse is None:
            continue
        can_id, trame = analyse
        reasm = reassembleurs.setdefault(can_id, uds_mod.ReassembleurIsotp())
        payload = reasm.nourrir(trame)
        if payload is None:
            continue
        if len(payload) >= 3 and payload[0] == 0x7F:
            m = module(can_id)
            if payload[2] == 0x78:
                m.attente_vue = True
            else:
                m.refus_nrc = payload[2]
            continue
        if len(payload) >= 3 and payload[0] == 0x59 and payload[1] == 0x02:
            m = module(can_id)
            m.codes = uds_mod.analyser_dtc(
                payload, f"Module {can_id - 8:03X}")
            continue
        # Tout autre payload est ignoré : à une demande 19 02, un
        # module ne peut répondre que 59 02 ou 7F — le reste est du
        # bruit (écho de la demande elle-même, par exemple).
    return [modules[k] for k in sorted(modules)]


def uds_attente(session, adresse: int, requete: bytes, delai_s: float = 4.0,
                essais: int = 3, pause_s: float = 1.0) -> ResultatUds:
    """Requête UDS qui traverse les « réponse en attente » (NRC 0x78).

    Depuis le build 6, la traversée principale se fait DANS
    session.uds() : après un 0x78, l'adaptateur écoute la réponse
    tardive du module au lieu de renvoyer la commande (renvoyer
    relançait le travail du VDC indéfiniment — terrain du
    2026-11-26). Cette boucle ne sert plus que de seconde chance :
    si l'écoute n'a rien capté, le module a peut-être fini entre
    temps et une nouvelle demande reçoit sa réponse tout de suite."""
    resultat = session.uds(adresse, requete, delai_s)
    restants = essais
    while (resultat.classe == "refus" and resultat.nrc == 0x78
           and restants > 0):
        restants -= 1
        if pause_s:
            time.sleep(pause_s)
        resultat = session.uds(adresse, requete, delai_s)
    return resultat


def lire_identite(session, adresse: int) -> dict:
    """DID standard d'identité (F187 pièce, F189 logiciel, F190 VIN).
    Valeurs None quand le module ne répond pas ou refuse."""
    identite = {"piece": None, "logiciel": None, "vin": None}
    for cle, did in (("piece", uds_mod.DID_NUMERO_PIECE),
                     ("logiciel", uds_mod.DID_NIVEAU_LOGICIEL),
                     ("vin", uds_mod.DID_VIN)):
        r = uds_attente(session, adresse, uds_mod.requete_lire_did(did), 3.0)
        if r.classe == "positive":
            lu = uds_mod.analyser_lire_did(r.octets)
            if lu:
                identite[cle] = uds_mod.texte_did(lu[1]) or None
    return identite


def lire_codes_module(session, adresse: int) -> tuple[ResultatUds, list[CodeDefaut]]:
    """Lecture DTC directe (19 02 FF) à une adresse physique, en
    traversant les NRC 0x78. Retourne le résultat brut et TOUS les
    enregistrements décodés (le filtrage par statut est à l'appelant :
    les modules répondent leur dictionnaire complet)."""
    r = uds_attente(session, adresse, uds_mod.requete_lire_dtc(), 5.0)
    codes: list[CodeDefaut] = []
    if r.classe == "positive":
        codes = uds_mod.analyser_dtc(r.octets, f"Module {adresse:03X}")
    return r, codes


def effacer_codes_module(session, adresse: int) -> ResultatUds:
    """Effacement UDS 0x14 à une adresse physique. L'ARCHIVAGE des
    codes présents est fait par l'appelant AVANT cet appel (même
    contrat que SessionObd.effacer_codes)."""
    return uds_attente(session, adresse, uds_mod.requete_effacer_dtc(), 5.0)


def sondes_acces(session, adresse: int) -> list[tuple[str, ResultatUds]]:
    """Sondes d'état, en OBSERVATION seulement : session étendue
    (10 03), demande de graine SecurityAccess (27 01) — on constate
    si la porte existe, aucune clé n'est calculée ni envoyée — puis
    retour à la session par défaut (10 01) pour laisser le module
    propre."""
    sondes = []
    r = uds_attente(session, adresse, bytes([0x10, 0x03]), 3.0)
    sondes.append(("Session étendue (10 03)", r))
    r = uds_attente(session, adresse, bytes([0x27, 0x01]), 3.0)
    sondes.append(("Graine SecurityAccess (27 01)", r))
    r = uds_attente(session, adresse, bytes([0x10, 0x01]), 3.0)
    sondes.append(("Retour à la session par défaut (10 01)", r))
    session.journal.evenement("sondes_acces", {
        "adresse": f"{adresse:03X}",
        "sondes": [{"nom": nom, "classe": r.classe,
                    "nrc": f"0x{r.nrc:02X}" if r.classe == "refus" else None,
                    "reponse": vers_texte(r.octets) if r.octets else None}
                   for nom, r in sondes],
    })
    return sondes


def decouvrir(session, delai_s: float = 8.0) -> list[ModuleDecouvert]:
    """Cartographie complète : sonde fonctionnelle 19 02 FF, puis
    identité DID de chaque module découvert (best effort)."""
    lignes = session.requete_fonctionnelle(
        uds_mod.requete_lire_dtc(), delai_s)
    modules = analyser_lignes_fonctionnelles(lignes)
    for m in modules:
        identite = lire_identite(session, m.requete)
        m.piece = identite["piece"]
        m.logiciel = identite["logiciel"]
        m.vin_lu = identite["vin"]
    session.derniere_decouverte = modules
    session.journal.evenement("decouverte_fonctionnelle", {
        "modules": [{
            "requete": m.requete_hex, "reponse": f"{m.reponse:03X}",
            "nom": m.nom, "piece": m.piece, "logiciel": m.logiciel,
            "codes_reels": [{"code": c.code, "statut": c.statut}
                            for c in m.codes_reels],
            "nb_enregistrements": len(m.codes),
            "attente_vue": m.attente_vue, "refus_nrc": m.refus_nrc,
        } for m in modules],
    })
    return modules
