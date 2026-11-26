"""Session OBD : transport série (pyserial) vers un adaptateur
ELM327/STN (OBDLink EX, puce STN2230, pont FTDI), protocole ELM,
opérations OBD-II et UDS/ISO-TP.

Portage de SessionObd.kt (Diag Forester, build 1).

Toutes les entrées/sorties passent par un verrou unique ; le mode
moniteur CAN détient le port tant qu'il roule. Aucune commande
active vers les actionneurs n'existe dans ce build — seules
écritures : les effacements de codes (mode 04 / UDS 0x14).
"""
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import canbus, dtc as dtc_mod, pids as pids_mod, uds as uds_mod
from .canbus import EtatCan, TrameCan
from .dtc import CodeDefaut
from .hexutil import (erreur_connue, lignes_utiles, octets_depuis_lignes,
                      u8, vers_texte)
from .journal import JournalSession
from .uds import ResultatUds

DEBITS_ESSAIS = [115200, 38400, 9600, 230400, 500000]


@dataclass
class InfoModule:
    adresse: int
    repond: bool
    refus: str | None = None
    identite: str | None = None
    vin_lu: str | None = None

    @property
    def adresse_hex(self) -> str:
        return f"{self.adresse:03X}"

    def ligne_affichage(self) -> str:
        if not self.repond and self.refus is None:
            return f"{self.adresse_hex} — silence (aucune réponse)"
        if not self.repond:
            return f"{self.adresse_hex} — refuse : {self.refus}"
        texte = f"{self.adresse_hex} — répond"
        if self.identite:
            texte += f" · {self.identite}"
        if self.vin_lu:
            texte += f" · VIN {self.vin_lu}"
        return texte


def lister_ports() -> list[tuple[str, str]]:
    """Ports COM disponibles : [(device, description), …]."""
    try:
        from serial.tools import list_ports
        return [(p.device, p.description or "") for p in list_ports.comports()]
    except Exception:
        return []


class SessionObd:
    def __init__(self, journal: JournalSession | None = None) -> None:
        self._port = None
        self._verrou = threading.RLock()
        self._tampon = ""
        self.journal = journal or JournalSession()
        self.connecte = False
        self.moniteur_actif = False
        self.protocole: str | None = None
        self.vin: str | None = None
        self.kilometrage_km: float | None = None
        self.derniere_tension: str | None = None
        self.etat_can = EtatCan()
        self._etat_can_maj_ms = 0.0
        self.dernier_recensement: list[InfoModule] = []
        self.derniers_codes: list[CodeDefaut] = []
        self._en_tete_courante = -1
        self._arret_moniteur = False
        self._fichier_capture = None

    # --- Transport ---------------------------------------------------

    def ouvrir(self, port_com: str) -> str:
        import serial  # import paresseux : les tests n'en ont pas besoin

        self.fermer()
        initialise = False
        dernier_port = None
        for debit in DEBITS_ESSAIS:
            try:
                p = serial.Serial(port_com, debit, timeout=0.2,
                                  write_timeout=1.0, dsrdtr=False)
                p.dtr = True
                p.rts = True
                dernier_port = p
                self._port = p
                time.sleep(0.15)
                self._vider_tampon()
                reponse = self._commande_brute("ATZ", 2.5)
                if ("ELM" in reponse or "STN" in reponse
                        or "OBDLink" in reponse or "327" in reponse):
                    initialise = True
                    break
                p.close()
                self._port = None
            except Exception:
                self._port = None
                continue
        if not initialise:
            self.fermer()
            raise IOError(
                "L'adaptateur ne répond pas aux commandes AT "
                f"(essayés : {', '.join(str(d) for d in DEBITS_ESSAIS)} bauds)")
        self.connecte = True
        self.journal.demarrer()
        self._initialiser_elm()
        self._lire_infos_vehicule()
        self.journal.metadonnees(self.vin, self.protocole, self.derniere_tension)
        return (f"Adaptateur initialisé · protocole {self.protocole or 'inconnu'}"
                + (f" · VIN {self.vin}" if self.vin else ""))

    def fermer(self) -> None:
        try:
            if self._port is not None:
                self._port.close()
        except Exception:
            pass
        self._port = None
        self.connecte = False
        self.moniteur_actif = False
        self._en_tete_courante = -1

    def _vider_tampon(self) -> None:
        self._tampon = ""
        if self._port is None:
            return
        try:
            self._port.reset_input_buffer()
        except Exception:
            pass

    def _lire_jusqua_invite(self, delai_s: float) -> str:
        if self._port is None:
            raise IOError("Adaptateur non connecté")
        limite = time.time() + delai_s
        while time.time() < limite:
            idx = self._tampon.find(">")
            if idx >= 0:
                resultat = self._tampon[:idx]
                self._tampon = self._tampon[idx + 1:]
                return resultat
            n = self._port.in_waiting
            data = self._port.read(max(1, n)) if n else self._port.read(1)
            if data:
                self._tampon += data.decode("iso-8859-1", errors="replace")
        reste, self._tampon = self._tampon, ""
        return reste

    def _lire_ligne(self, delai_s: float) -> str | None:
        if self._port is None:
            return None
        limite = time.time() + delai_s
        while time.time() < limite:
            texte = self._tampon
            fin = next((i for i, c in enumerate(texte) if c in "\r\n"), -1)
            if fin >= 0:
                debut = fin + 1
                while debut < len(texte) and texte[debut] in "\r\n":
                    debut += 1
                self._tampon = texte[debut:]
                ligne = texte[:fin].strip()
                if ligne:
                    return ligne
                continue
            n = self._port.in_waiting
            data = self._port.read(max(1, n)) if n else self._port.read(1)
            if data:
                self._tampon += data.decode("iso-8859-1", errors="replace")
        return None

    def _ecrire(self, texte: str) -> None:
        if self._port is None:
            raise IOError("Adaptateur non connecté")
        self._port.write((texte + "\r").encode("iso-8859-1"))

    def _commande_brute(self, commande: str, delai_s: float) -> str:
        self._ecrire(commande)
        return self._lire_jusqua_invite(delai_s)

    def commande(self, commande: str, delai_s: float = 5.0) -> list[str]:
        if not self.connecte:
            raise IOError("Adaptateur non connecté")
        if self.moniteur_actif:
            raise IOError("Moniteur CAN actif : arrête-le d'abord")
        with self._verrou:
            self._ecrire(commande)
            brut = self._lire_jusqua_invite(delai_s)
            return lignes_utiles(brut, commande)

    def _commande_interne(self, commande: str, delai_s: float = 3.0) -> list[str]:
        self._ecrire(commande)
        brut = self._lire_jusqua_invite(delai_s)
        return lignes_utiles(brut, commande)

    def _commande_octets(self, commande: str, delai_s: float = 5.0) -> bytes:
        return octets_depuis_lignes(self.commande(commande, delai_s))

    # --- Initialisation et infos véhicule ----------------------------

    def _initialiser_elm(self) -> None:
        self.commande("ATE0")
        self.commande("ATL0")
        self.commande("ATH0")
        self.commande("ATST32")
        self.commande("ATSP0")
        essai = self.commande("0100", 8.0)
        if erreur_connue(essai) is not None or not essai:
            self.commande("ATSP6")
            self.commande("0100", 8.0)
        lignes = self.commande("ATDP")
        self.protocole = lignes[0] if lignes else None
        self.maj_tension()

    def maj_tension(self) -> None:
        try:
            lignes = self.commande("ATRV", 3.0)
            for ligne in lignes:
                if "V" in ligne.upper():
                    self.derniere_tension = ligne.strip().upper()
                    break
        except Exception:
            pass

    def _lire_infos_vehicule(self) -> None:
        try:
            octets = self._commande_octets("0902", 8.0)
            self.vin = extraire_vin(octets) or self.vin
        except Exception:
            pass
        try:
            octets = self._commande_octets("01A6", 5.0)
            km = dtc_mod.kilometrage_pid_a6(octets)
            if km is not None:
                self.kilometrage_km = km
        except Exception:
            pass
        self.maj_tension()

    # --- UDS sur ISO-TP via l'adaptateur -------------------------------

    def uds(self, adresse: int, requete: bytes, delai_s: float = 4.0) -> ResultatUds:
        with self._verrou:
            if not self.connecte:
                raise IOError("Adaptateur non connecté")
            if self.moniteur_actif:
                raise IOError("Moniteur CAN actif : arrête-le d'abord")
            if self._en_tete_courante != adresse:
                self._commande_interne("ATSP6")
                self._commande_interne(f"ATSH{adresse:03X}")
                self._commande_interne(f"ATCRA{adresse + 8:03X}")
                self._commande_interne("ATH0")
                self._en_tete_courante = adresse
            self._ecrire(vers_texte(requete, ""))
            brut = self._lire_jusqua_invite(delai_s)
            lignes = lignes_utiles(brut)
            err = erreur_connue(lignes)
            if err is not None:
                resultat = ResultatUds.erreur_adaptateur(err)
            else:
                octets = octets_depuis_lignes(lignes)
                service = requete[0] if requete else 0
                resultat = uds_mod.classifier(octets, service)
            self.journal.evenement("requete_uds", {
                "adresse": f"{adresse:03X}",
                "requete": vers_texte(requete),
                "reponse": vers_texte(resultat.octets),
                "classe": resultat.classe,
            })
            return resultat

    def _retour_mode_obd(self) -> None:
        with self._verrou:
            self._commande_interne("ATSH7DF")
            self._commande_interne("ATCRA000")
            self._commande_interne("ATSP0")
            self._en_tete_courante = -1

    # --- Recensement des modules ---------------------------------------

    def recensement(self) -> list[InfoModule]:
        modules = []
        for adresse in range(0x7E0, 0x7E8):
            repond = False
            refus = None
            identite = None
            vin_lu = None
            r = self.uds(adresse, uds_mod.requete_tester_present(), 2.5)
            if r.classe == "positive":
                repond = True
            elif r.classe == "refus":
                repond = True  # il répond, en refusant : il est là
                refus = f"NRC 0x{r.nrc:02X} — {r.description_nrc}"
            elif r.classe == "erreur_adaptateur":
                refus = r.message
            if repond:
                r2 = self.uds(adresse, uds_mod.requete_lire_did(uds_mod.DID_NUMERO_PIECE), 2.5)
                if r2.classe == "positive":
                    lu = uds_mod.analyser_lire_did(r2.octets)
                    if lu:
                        identite = uds_mod.texte_did(lu[1]) or None
                r3 = self.uds(adresse, uds_mod.requete_lire_did(uds_mod.DID_VIN), 2.5)
                if r3.classe == "positive":
                    lu = uds_mod.analyser_lire_did(r3.octets)
                    if lu:
                        vin_lu = uds_mod.texte_did(lu[1]) or None
            modules.append(InfoModule(adresse, repond, refus, identite, vin_lu))
        self._retour_mode_obd()
        self.dernier_recensement = modules
        self.journal.evenement("recensement", {
            "modules": [{
                "adresse": m.adresse_hex, "repond": m.repond,
                "refus": m.refus, "identite": m.identite,
            } for m in modules],
        })
        return modules

    # --- Codes de défaut -------------------------------------------------

    def lire_codes(self) -> list[CodeDefaut]:
        codes: list[CodeDefaut] = []
        self._retour_mode_obd()
        for mode, origine in (("03", "Moteur (confirmés)"),
                              ("07", "Moteur (en attente)"),
                              ("0A", "Moteur (permanents)")):
            try:
                octets = self._commande_octets(mode, 6.0)
                codes.extend(dtc_mod.analyser_reponse_mode(octets, origine))
            except Exception:
                pass
        modules = self.dernier_recensement or self.recensement()
        for module in [m for m in modules if m.repond]:
            r = self.uds(module.adresse, uds_mod.requete_lire_dtc(), 5.0)
            if r.classe == "positive":
                codes.extend(uds_mod.analyser_dtc(r.octets, f"Module {module.adresse_hex}"))
            elif r.classe == "refus":
                self.journal.evenement("lecture_dtc_refusee", {
                    "adresse": module.adresse_hex, "nrc": f"0x{r.nrc:02X}"})
        self._retour_mode_obd()
        vus = set()
        uniques = []
        for c in codes:
            cle = f"{c.code}|{c.origine}"
            if cle not in vus:
                vus.add(cle)
                uniques.append(c)
        self.derniers_codes = uniques
        self.journal.evenement("lecture_codes", {
            "codes": [{"code": c.code, "origine": c.origine} for c in uniques]})
        return uniques

    def lire_freeze_frame(self) -> list[str]:
        lignes = []
        for pid in (0x04, 0x05, 0x0C, 0x0D, 0x11):
            definition = pids_mod.par_pid(pid)
            if definition is None:
                continue
            try:
                octets = self._commande_octets(definition.demande(0x02, 0), 4.0)
                valeur = definition.decoder_reponse(octets, 0x02)
                if valeur is not None:
                    lignes.append(f"{definition.nom} : {pids_mod.formater(definition, valeur)}")
            except Exception:
                pass
        return lignes

    def effacer_codes(self) -> list[str]:
        """Effacement : mode 04 puis UDS 0x14 par module qui répond.
        L'ARCHIVAGE du rapport est fait par l'appelant AVANT cet appel."""
        resultats = []
        self._retour_mode_obd()
        try:
            lignes = self.commande("04", 6.0)
            err = erreur_connue(lignes)
            resultats.append("Moteur (mode 04) : "
                             + (f"échec — {err}" if err else "commande acceptée"))
        except Exception as e:
            resultats.append(f"Moteur (mode 04) : échec — {e}")
        for module in [m for m in self.dernier_recensement if m.repond]:
            r = self.uds(module.adresse, uds_mod.requete_effacer_dtc(), 5.0)
            if r.classe == "positive":
                texte = "commande acceptée"
            elif r.classe == "refus":
                texte = f"refus — NRC 0x{r.nrc:02X} ({r.description_nrc})"
            elif r.classe == "erreur_adaptateur":
                texte = f"erreur adaptateur — {r.message}"
            else:
                texte = "silence du module"
            resultats.append(f"Module {module.adresse_hex} (UDS 0x14) : {texte}")
        self._retour_mode_obd()
        self.journal.evenement("effacement", {"resultats": resultats})
        return resultats

    # --- Données en direct ------------------------------------------------

    def lire_pid(self, definition) -> float | None:
        octets = self._commande_octets(definition.demande(0x01), 4.0)
        return definition.decoder_reponse(octets, 0x01)

    def pid_supportes(self) -> set[int]:
        supportes: set[int] = set()
        for base in (0x00, 0x20, 0x40):
            try:
                octets = self._commande_octets(f"01{base:02X}", 4.0)
                supportes |= pids_mod.pid_supportes(octets, base)
            except Exception:
                pass
            if base not in supportes and base != 0x00:
                break
        return supportes

    # --- Garde-fou mouvement ------------------------------------------------

    def verifier_immobile(self) -> bool:
        """Vrai si le véhicule est immobile. Sources, par ordre :
        vitesses de roue du moniteur CAN si fraîches (< 3 s), sinon
        PID 0x0D. Vitesse illisible → considéré immobile (journalisé
        par l'appelant), comme le build Android."""
        if time.time() * 1000 - self._etat_can_maj_ms < 3000:
            vmax = self.etat_can.vitesse_roue_max()
            if vmax is not None:
                return vmax < 0.5
            if self.etat_can.vitesse_kmh is not None:
                return self.etat_can.vitesse_kmh < 0.5
        if self.moniteur_actif:
            return True
        try:
            definition = pids_mod.par_pid(0x0D)
            valeur = self.lire_pid(definition)
            return (valeur if valeur is not None else 0.0) < 0.5
        except Exception:
            return True

    # --- Moniteur CAN --------------------------------------------------------

    def demarrer_moniteur(self, filtres: set[int], chemin_capture: Path,
                          rappel) -> None:
        """Écoute seule (ATMA). Les trames sont diffusées en continu
        vers le fichier de capture (CSV SavvyCAN) ; le rappel reçoit
        (trame, état) pour l'affichage (vue bornée côté interface)."""
        if not self.connecte:
            raise IOError("Adaptateur non connecté")
        if self.moniteur_actif:
            raise IOError("Moniteur déjà actif")
        self._arret_moniteur = False
        fil = threading.Thread(target=self._boucle_moniteur,
                               args=(filtres, Path(chemin_capture), rappel),
                               name="moniteur-can", daemon=True)
        fil.start()

    def _boucle_moniteur(self, filtres, chemin_capture, rappel) -> None:
        with self._verrou:
            try:
                self._commande_interne("ATSP6")
                self._commande_interne("ATH1")
                if len(filtres) == 1:
                    can_id = next(iter(filtres))
                    self._commande_interne(f"ATCF{can_id:03X}")
                    self._commande_interne("ATCM000007FF")
                chemin_capture.parent.mkdir(parents=True, exist_ok=True)
                fichier = open(chemin_capture, "w", encoding="utf-8", newline="")
                self._fichier_capture = fichier
                fichier.write(canbus.ENTETE_SAVVYCAN + "\n")
                base_ms = time.time() * 1000
                self.etat_can = EtatCan()
                self._ecrire("ATMA")
                self.moniteur_actif = True
                while not self._arret_moniteur:
                    ligne = self._lire_ligne(0.4)
                    if ligne is None or ligne == ">":
                        continue
                    analyse = canbus.analyser_ligne(ligne)
                    if analyse is None:
                        continue
                    can_id, donnees = analyse
                    if filtres and can_id not in filtres:
                        continue
                    trame = TrameCan(can_id, donnees, int(time.time() * 1000))
                    fichier.write(canbus.ligne_savvycan(trame, base_ms / 1000.0) + "\n")
                    self.etat_can = canbus.appliquer(self.etat_can, can_id, donnees)
                    self._etat_can_maj_ms = time.time() * 1000
                    rappel(trame, self.etat_can)
            except Exception:
                pass
            finally:
                try:
                    self._ecrire("")
                    self._lire_jusqua_invite(1.5)
                    self._commande_interne("ATH0")
                except Exception:
                    pass
                try:
                    if self._fichier_capture is not None:
                        self._fichier_capture.close()
                except Exception:
                    pass
                self._fichier_capture = None
                self.moniteur_actif = False
                self._en_tete_courante = -1

    def arreter_moniteur(self) -> None:
        self._arret_moniteur = True


def extraire_vin(octets: bytes) -> str | None:
    """Cherche la séquence 49 02 puis lit l'ASCII du VIN (17 caractères)."""
    for i in range(max(0, len(octets) - 2)):
        if u8(octets, i) == 0x49 and u8(octets, i + 1) == 0x02:
            ascii_vin = "".join(
                chr(c) for c in octets[i + 2:]
                if 0x30 <= c <= 0x39 or 0x41 <= c <= 0x5A)
            if len(ascii_vin) >= 17:
                return ascii_vin[:17]
            return ascii_vin or None
    return None
