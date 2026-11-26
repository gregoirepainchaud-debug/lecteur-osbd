"""Garage de véhicules et historique permanent.

Registre local en JSON, dans le dossier de données de l'app :
  <Documents>/Lecteur OSBD/vehicules.json
  <Documents>/Lecteur OSBD/<nom du véhicule>/historique.json
  <Documents>/Lecteur OSBD/<nom du véhicule>/sessions/…
  <Documents>/Lecteur OSBD/<nom du véhicule>/rapports/…
  <Documents>/Lecteur OSBD/<nom du véhicule>/captures/…

L'historique n'est JAMAIS effacé automatiquement. Tous les fichiers
sont du JSON lisible sans l'app — c'est le format que Grégoire passe
à Muse pour analyse (méthode Beards : l'humain capture, l'IA lit).
"""
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path


def dossier_donnees() -> Path:
    """%USERPROFILE%\\Documents\\Lecteur OSBD (repli : ~\\Lecteur OSBD)."""
    documents = Path.home() / "Documents"
    base = documents if documents.exists() else Path.home()
    dossier = base / "Lecteur OSBD"
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def nom_dossier_sain(nom: str) -> str:
    """Nom de dossier sûr à partir du nom libre du véhicule."""
    sain = re.sub(r'[<>:"/\\|?*]', "_", nom).strip().strip(".")
    return sain or "Vehicule"


@dataclass
class Vehicule:
    nom: str
    marque: str = ""
    modele: str = ""
    annee: str = ""
    vin: str = ""
    notes: str = ""

    @property
    def marque_simple(self) -> str:
        """Marque normalisée pour adapter recensement/descriptions."""
        texte = f"{self.marque} {self.modele}".lower()
        if "subaru" in texte or "forester" in texte:
            return "subaru"
        if "mercedes" in texte or "sprinter" in texte or "benz" in texte:
            return "mercedes"
        return "autre"

    def libelle(self) -> str:
        morceaux = [self.nom]
        details = " ".join(x for x in (self.annee, self.marque, self.modele) if x)
        if details:
            morceaux.append(f"({details})")
        return " ".join(morceaux)


@dataclass
class Registre:
    racine: Path
    vehicules: list[Vehicule] = field(default_factory=list)

    @property
    def fichier(self) -> Path:
        return self.racine / "vehicules.json"

    @classmethod
    def charger(cls, racine: Path | None = None) -> "Registre":
        racine = racine or dossier_donnees()
        registre = cls(racine=racine)
        if registre.fichier.exists():
            try:
                donnees = json.loads(registre.fichier.read_text(encoding="utf-8"))
                registre.vehicules = [Vehicule(**v) for v in donnees.get("vehicules", [])]
            except Exception:
                registre.vehicules = []  # fichier illisible : on repart vide, sans l'écraser
        return registre

    def enregistrer(self) -> None:
        contenu = {"vehicules": [asdict(v) for v in self.vehicules]}
        self.fichier.write_text(json.dumps(contenu, ensure_ascii=False, indent=2),
                                encoding="utf-8")

    def ajouter(self, vehicule: Vehicule) -> Vehicule:
        self.vehicules.append(vehicule)
        self.enregistrer()
        self.dossier_vehicule(vehicule)
        return vehicule

    def par_vin(self, vin: str) -> Vehicule | None:
        if not vin:
            return None
        for v in self.vehicules:
            if v.vin and v.vin.upper() == vin.upper():
                return v
        return None

    def dossier_vehicule(self, vehicule: Vehicule) -> Path:
        dossier = self.racine / nom_dossier_sain(vehicule.nom)
        for sous in ("", "sessions", "rapports", "captures"):
            (dossier / sous).mkdir(parents=True, exist_ok=True)
        return dossier


# --- Historique par véhicule --------------------------------------------

FICHIER_HISTORIQUE = "historique.json"


def charger_historique(dossier_vehicule: Path) -> dict:
    fichier = dossier_vehicule / FICHIER_HISTORIQUE
    if fichier.exists():
        try:
            return json.loads(fichier.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"sessions": []}


def ajouter_session(dossier_vehicule: Path, session: dict) -> dict:
    """Ajoute une session à l'historique (jamais d'effacement)."""
    historique = charger_historique(dossier_vehicule)
    historique.setdefault("sessions", []).append(session)
    fichier = dossier_vehicule / FICHIER_HISTORIQUE
    fichier.write_text(json.dumps(historique, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    return historique


def upsert_session(dossier_vehicule: Path, session: dict) -> dict:
    """Insère la session, ou remplace celle de même « debut » (une
    connexion = une session, mise à jour à chaque jalon)."""
    historique = charger_historique(dossier_vehicule)
    sessions = historique.setdefault("sessions", [])
    for i, existante in enumerate(sessions):
        if existante.get("debut") == session.get("debut"):
            sessions[i] = session
            break
    else:
        sessions.append(session)
    fichier = dossier_vehicule / FICHIER_HISTORIQUE
    fichier.write_text(json.dumps(historique, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    return historique


def chronologie_codes(historique: dict) -> dict[str, dict]:
    """Pour chaque code : première vue, effacements, réapparitions.

    Les sessions portent « codes » (liste de codes lus) et
    « actions » (liste de chaînes ; « effacement » signale un clear).
    """
    chrono: dict[str, dict] = {}
    for session in historique.get("sessions", []):
        date = session.get("debut", "")
        for code in session.get("codes", []):
            entree = chrono.setdefault(code, {
                "code": code,
                "premiere_vue": date,
                "derniere_vue": date,
                "nb_sessions_present": 0,
                "effacements": [],
                "reapparitions": [],
                "present_derniere_session": False,
            })
            # Réapparition : le code revient après une session où il
            # était absent alors qu'un effacement a eu lieu entre-temps.
            if (entree["nb_sessions_present"] > 0
                    and not entree["present_derniere_session"]
                    and entree["effacements"]):
                entree["reapparitions"].append(date)
            entree["derniere_vue"] = date
            entree["nb_sessions_present"] += 1
            entree["present_derniere_session"] = True
        presents = set(session.get("codes", []))
        for code, entree in chrono.items():
            if code not in presents:
                entree["present_derniere_session"] = False
        if any("effacement" in a for a in session.get("actions", [])):
            for code in session.get("codes", []):
                if code in chrono:
                    chrono[code]["effacements"].append(date)
    return chrono


def comparer_sessions(session_a: dict, session_b: dict) -> dict:
    """Diff de codes entre deux sessions (A = ancienne, B = récente)."""
    codes_a = set(session_a.get("codes", []))
    codes_b = set(session_b.get("codes", []))
    return {
        "apparus": sorted(codes_b - codes_a),
        "disparus": sorted(codes_a - codes_b),
        "persistants": sorted(codes_a & codes_b),
    }


def fusionner_doublons(registre: "Registre") -> int:
    """Fusionne les fiches de même nom dont une seule porte un VIN
    (cas vu le 2026-11-26 : fiche créée à la main sans VIN, puis seconde
    fiche créée à la connexion quand le VIN est lu). Les dossiers sont
    nommés par le nom — même nom, même dossier : rien à déplacer.
    Retourne le nombre de fiches retirées."""
    par_nom: dict[str, list[Vehicule]] = {}
    for v in registre.vehicules:
        par_nom.setdefault(nom_dossier_sain(v.nom).lower(), []).append(v)
    retires = 0
    for groupe in par_nom.values():
        if len(groupe) < 2:
            continue
        avec_vin = [v for v in groupe if v.vin]
        if len(avec_vin) != 1:
            continue
        garde = avec_vin[0]
        for v in groupe:
            if v is not garde:
                registre.vehicules.remove(v)
                retires += 1
    if retires:
        registre.enregistrer()
    return retires
