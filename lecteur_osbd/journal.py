"""Journal de session structuré (JSON) — portage de SessionJournal.kt.

Recensement, codes, effacements, requêtes manuelles, métadonnées.
Fichiers écrits dans le dossier du véhicule (sessions / rapports),
lisibles sans l'app.

Build 1 : aucun envoi serveur (endpoint « diag » à créer côté VPS) —
noté pour le build 2.
"""
import json
import time
from datetime import datetime
from pathlib import Path

from . import buildinfo


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _horodatage_fichier(dt: datetime) -> str:
    return dt.strftime("%Y%m%d-%H%M%S")


class JournalSession:
    def __init__(self) -> None:
        self._racine: dict | None = None
        self._evenements: list[dict] = []
        self._debut_ms: float = 0.0
        self._fichier_continu: Path | None = None

    def demarrer(self) -> None:
        self._debut_ms = time.time() * 1000
        self._racine = {
            "app": buildinfo.APP_NAME,
            "version": buildinfo.VERSION,
            "tampon": buildinfo.STAMP,
            "debut": _iso(datetime.now().astimezone()),
        }
        self._evenements = []

    def metadonnees(self, vin=None, protocole=None, tension=None,
                    vehicule=None) -> None:
        if self._racine is None:
            return
        if vin:
            self._racine["vin"] = vin
        if protocole:
            self._racine["protocole"] = protocole
        if tension:
            self._racine["tensionBatterie"] = tension
        if vehicule:
            self._racine["vehicule"] = vehicule

    def evenement(self, type_evt: str, details: dict | None = None) -> None:
        if self._racine is None:
            return
        self._evenements.append({
            "t": int(time.time() * 1000 - self._debut_ms),
            "type": type_evt,
            "details": details or {},
        })
        self._ecrire_continu()

    def definir_fichier(self, dossier_sessions: Path) -> Path:
        """Écriture continue (build 2) : dès que le dossier du véhicule
        est connu, le journal est réécrit sur disque à CHAQUE événement.
        Le build 1 ne l'écrivait qu'à la déconnexion — une fin brutale
        (laptop fermé, app tuée) perdait toute la session."""
        dossier_sessions.mkdir(parents=True, exist_ok=True)
        nom = f"session-{_horodatage_fichier(datetime.fromtimestamp(self._debut_ms / 1000).astimezone())}.json"
        self._fichier_continu = dossier_sessions / nom
        self._ecrire_continu()
        return self._fichier_continu

    def _ecrire_continu(self) -> None:
        if self._fichier_continu is None or self._racine is None:
            return
        try:
            self._fichier_continu.write_text(self.texte_json(), encoding="utf-8")
        except Exception:
            pass

    def texte_json(self) -> str:
        if self._racine is None:
            return "{}"
        copie = dict(self._racine)
        copie["evenements"] = list(self._evenements)
        return json.dumps(copie, ensure_ascii=False, indent=2)

    def enregistrer(self, dossier_sessions: Path) -> Path:
        dossier_sessions.mkdir(parents=True, exist_ok=True)
        fichier = dossier_sessions / f"session-{_horodatage_fichier(datetime.now())}.json"
        fichier.write_text(self.texte_json(), encoding="utf-8")
        return fichier

    def archiver_rapport(self, dossier_rapports: Path, texte_lisible: str,
                         motif: str) -> Path:
        """Archive un rapport complet (JSON + texte) — appelé
        systématiquement AVANT tout effacement de codes."""
        dossier_rapports.mkdir(parents=True, exist_ok=True)
        horodatage = _horodatage_fichier(datetime.now())
        (dossier_rapports / f"rapport-{horodatage}.json").write_text(
            self.texte_json(), encoding="utf-8")
        fichier = dossier_rapports / f"rapport-{horodatage}.txt"
        fichier.write_text(
            f"Rapport {buildinfo.APP_NAME} — {motif}\n"
            f"Archivé le {_iso(datetime.now().astimezone())}, avant effacement.\n\n"
            + texte_lisible,
            encoding="utf-8")
        self.evenement("archivage_rapport", {"motif": motif})
        return fichier
