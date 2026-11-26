"""Interface graphique Tkinter de Lecteur OSBD.

Barre principale toujours visible : port COM, connexion, véhicule,
tension — et le bouton « Mettre à jour l'app » (règle de Grégoire :
visible, jamais enfoui dans un menu).

Onglets : Véhicule · Codes · Données en direct · Moniteur CAN ·
Freins / VDC (lecture seule) · Historique · Avancé (console UDS).

Aucune commande EPB, aucune écriture autre que l'effacement de
codes archivé au préalable.
"""
import queue
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from . import buildinfo, maj, pids as pids_mod, registry, ssm as ssm_mod
from .hexutil import est_hex, vers_octets, vers_texte
from .journal import JournalSession
from .session import SessionObd, lister_ports

TEXTE_FREINS = (
    "FREINS / VDC — LECTURE SEULE\n\n"
    "Sur le Forester, le frein de stationnement électrique (EPB) est "
    "piloté par le module VDC — le même qui gère l'ABS et "
    "l'antipatinage. Aucune commande d'actionneur dans ce build : "
    "on lit, on ne commande pas.\n\n"
    "Le VDC d'un Subaru ne parle pas UDS : sa voie est le SSM "
    "(protocole constructeur, encapsulé dans ISO-TP), adresse CAN "
    "présumée 0x7E2. Le bouton « Rechercher les modules SSM » fait "
    "l'init SSM (AA) aux adresses 7E0–7E4 — 7E0/7E1 sont les témoins "
    "connus — plus un filet de sondes UDS directes au cas où.\n\n"
    "Sur le Sprinter, le frein de stationnement est mécanique "
    "(levier) ; le module ESP reste lisible en diagnostic.\n\n"
    "Vitesses de roue en direct : démarre le moniteur CAN (trame "
    "0x13A, véhicules Subaru) ou les données en direct pour les comparer."
)


class Application(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{buildinfo.APP_NAME} — {buildinfo.STAMP}")
        self.geometry("1080x760")
        self.minsize(900, 620)

        self.racine_donnees = registry.dossier_donnees()
        self.registre = registry.Registre.charger(self.racine_donnees)
        registry.fusionner_doublons(self.registre)
        if maj.est_fige():
            maj.nettoyer_restes(maj.chemin_exe_courant())
        self.journal = JournalSession()
        self.session = SessionObd(self.journal)
        self.vehicule_courant: registry.Vehicule | None = None
        self.vin_lu: str | None = None
        self.session_historique: dict | None = None

        self._file_ui: queue.Queue = queue.Queue()
        self._file_moniteur: queue.Queue = queue.Queue()
        self._trames_vue: deque = deque(maxlen=5000)
        self._moniteur_en_cours = False
        self._direct_en_cours = False

        self._construire_interface()
        self._rafraichir_vehicules()
        self._rafraichir_ports()
        self.after(100, self._traiter_file_ui)
        self.after(500, self._traiter_file_moniteur)
        self.after(5000, self._boucle_tension)
        self.protocol("WM_DELETE_WINDOW", self._fermer)

    # --- Construction -------------------------------------------------

    def _construire_interface(self) -> None:
        barre = ttk.Frame(self, padding=8)
        barre.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(barre, text="Port COM :").grid(row=0, column=0, sticky="w")
        self.var_port = tk.StringVar()
        self.combo_port = ttk.Combobox(barre, textvariable=self.var_port, width=14)
        self.combo_port.grid(row=0, column=1, padx=4)
        ttk.Button(barre, text="Rafraîchir", command=self._rafraichir_ports).grid(
            row=0, column=2, padx=2)
        self.bouton_connexion = ttk.Button(barre, text="Connecter",
                                           command=self._basculer_connexion)
        self.bouton_connexion.grid(row=0, column=3, padx=6)
        self.label_tension = ttk.Label(barre, text="Tension : —")
        self.label_tension.grid(row=0, column=4, padx=6)

        ttk.Label(barre, text="Véhicule :").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.var_vehicule = tk.StringVar()
        self.combo_vehicule = ttk.Combobox(barre, textvariable=self.var_vehicule,
                                           state="readonly", width=34)
        self.combo_vehicule.grid(row=1, column=1, columnspan=2, padx=4, pady=(6, 0),
                                 sticky="w")
        self.combo_vehicule.bind("<<ComboboxSelected>>", self._vehicule_choisi)
        ttk.Button(barre, text="Ajouter un véhicule",
                   command=self._dialogue_ajout_vehicule).grid(
            row=1, column=3, padx=6, pady=(6, 0))

        # Bouton de mise à jour : TOUJOURS visible, dans la barre
        # principale (règle de Grégoire pour toutes ses apps maison).
        self.bouton_maj = ttk.Button(barre, text="Mettre à jour l'app",
                                     command=self._verifier_maj)
        self.bouton_maj.grid(row=0, column=5, padx=10, sticky="e")
        self.label_maj = ttk.Label(barre, text=f"Version : {buildinfo.STAMP}")
        self.label_maj.grid(row=1, column=5, padx=10, pady=(6, 0), sticky="e")
        barre.columnconfigure(5, weight=1)

        self.onglets = ttk.Notebook(self)
        self.onglets.pack(fill=tk.BOTH, expand=True, padx=8)

        self._onglet_vehicule()
        self._onglet_codes()
        self._onglet_direct()
        self._onglet_moniteur()
        self._onglet_freins()
        self._onglet_historique()
        self._onglet_avance()

        pied = ttk.Frame(self, padding=8)
        pied.pack(side=tk.BOTTOM, fill=tk.X)
        self.label_statut = ttk.Label(pied, text="Prêt. Branche l'adaptateur, choisis le port COM, connecte.")
        self.label_statut.pack(side=tk.LEFT)
        ttk.Button(pied, text="Ouvrir le dossier des données",
                   command=lambda: self._ouvrir_dossier(self.racine_donnees)).pack(side=tk.RIGHT)

    def _zone_texte(self, parent) -> tk.Text:
        cadre = ttk.Frame(parent)
        cadre.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        texte = tk.Text(cadre, wrap=tk.WORD, height=18)
        defilement = ttk.Scrollbar(cadre, command=texte.yview)
        texte.configure(yscrollcommand=defilement.set)
        texte.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        defilement.pack(side=tk.RIGHT, fill=tk.Y)
        return texte

    def _onglet_vehicule(self) -> None:
        onglet = ttk.Frame(self.onglets)
        self.onglets.add(onglet, text="Véhicule")
        ttk.Button(onglet, text="Recenser les modules (UDS)",
                   command=self._recenser).pack(anchor="w", padx=8, pady=8)
        self.texte_vehicule = self._zone_texte(onglet)

    def _onglet_codes(self) -> None:
        onglet = ttk.Frame(self.onglets)
        self.onglets.add(onglet, text="Codes")
        boutons = ttk.Frame(onglet, padding=8)
        boutons.pack(fill=tk.X)
        ttk.Button(boutons, text="Lire les codes", command=self._lire_codes).pack(side=tk.LEFT)
        ttk.Button(boutons, text="Effacer les codes…",
                   command=self._effacer_codes).pack(side=tk.LEFT, padx=8)
        self.texte_codes = self._zone_texte(onglet)

    def _onglet_direct(self) -> None:
        onglet = ttk.Frame(self.onglets)
        self.onglets.add(onglet, text="Données en direct")
        boutons = ttk.Frame(onglet, padding=8)
        boutons.pack(fill=tk.X)
        self.bouton_direct = ttk.Button(boutons, text="Démarrer la lecture en direct",
                                        command=self._basculer_direct)
        self.bouton_direct.pack(side=tk.LEFT)
        cadre = ttk.Frame(onglet)
        cadre.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.arbre_direct = ttk.Treeview(cadre, columns=("valeur",), show="tree headings")
        self.arbre_direct.heading("#0", text="Mesure")
        self.arbre_direct.heading("valeur", text="Valeur")
        self.arbre_direct.pack(fill=tk.BOTH, expand=True)
        self._lignes_direct = {}
        for definition in pids_mod.DEFINITIONS:
            iid = self.arbre_direct.insert("", tk.END, text=definition.nom, values=("—",))
            self._lignes_direct[definition.pid] = iid

    def _onglet_moniteur(self) -> None:
        onglet = ttk.Frame(self.onglets)
        self.onglets.add(onglet, text="Moniteur CAN")
        boutons = ttk.Frame(onglet, padding=8)
        boutons.pack(fill=tk.X)
        ttk.Label(boutons, text="Filtres ID (hex, séparés par des espaces) :").pack(side=tk.LEFT)
        self.var_filtres = tk.StringVar()
        ttk.Entry(boutons, textvariable=self.var_filtres, width=24).pack(side=tk.LEFT, padx=4)
        self.bouton_moniteur = ttk.Button(boutons, text="Démarrer l'écoute",
                                          command=self._basculer_moniteur)
        self.bouton_moniteur.pack(side=tk.LEFT, padx=6)
        self.label_capture = ttk.Label(boutons, text="Capture : —")
        self.label_capture.pack(side=tk.LEFT, padx=6)
        self.texte_moniteur = self._zone_texte(onglet)
        self.label_etat_can = ttk.Label(onglet, text="État décodé : —", padding=8)
        self.label_etat_can.pack(anchor="w")

    def _onglet_freins(self) -> None:
        onglet = ttk.Frame(self.onglets)
        self.onglets.add(onglet, text="Freins / VDC")
        ttk.Label(onglet, text=TEXTE_FREINS, wraplength=900, justify=tk.LEFT,
                  padding=8).pack(anchor="w")
        boutons = ttk.Frame(onglet)
        boutons.pack(anchor="w", padx=8)
        ttk.Button(boutons, text="Lire l'état freins / VDC",
                   command=self._lire_freins).pack(side=tk.LEFT)
        ttk.Button(boutons, text="Rechercher les modules SSM (VDC…)",
                   command=self._rechercher_ssm).pack(side=tk.LEFT, padx=6)
        lecture = ttk.Frame(onglet, padding=(8, 6))
        lecture.pack(anchor="w")
        ttk.Label(lecture, text="Lecture SSM (A8) — module (hex) :").pack(side=tk.LEFT)
        self.var_ssm_module = tk.StringVar(value="7E2")
        ttk.Entry(lecture, textvariable=self.var_ssm_module, width=6).pack(side=tk.LEFT, padx=4)
        ttk.Label(lecture, text="adresses mémoire (hex, virgules) :").pack(side=tk.LEFT)
        self.var_ssm_adresses = tk.StringVar(value="")
        ttk.Entry(lecture, textvariable=self.var_ssm_adresses, width=34).pack(side=tk.LEFT, padx=4)
        ttk.Button(lecture, text="Lire", command=self._lire_ssm).pack(side=tk.LEFT)
        self.texte_freins = self._zone_texte(onglet)

    def _onglet_historique(self) -> None:
        onglet = ttk.Frame(self.onglets)
        self.onglets.add(onglet, text="Historique")
        boutons = ttk.Frame(onglet, padding=8)
        boutons.pack(fill=tk.X)
        ttk.Button(boutons, text="Rafraîchir l'historique",
                   command=self._afficher_historique).pack(side=tk.LEFT)
        ttk.Label(boutons, text="Comparer :").pack(side=tk.LEFT, padx=(12, 2))
        self.var_comp_a = tk.StringVar()
        self.var_comp_b = tk.StringVar()
        self.combo_comp_a = ttk.Combobox(boutons, textvariable=self.var_comp_a,
                                         state="readonly", width=22)
        self.combo_comp_a.pack(side=tk.LEFT)
        self.combo_comp_b = ttk.Combobox(boutons, textvariable=self.var_comp_b,
                                         state="readonly", width=22)
        self.combo_comp_b.pack(side=tk.LEFT, padx=4)
        ttk.Button(boutons, text="Comparer", command=self._comparer).pack(side=tk.LEFT)
        self.texte_historique = self._zone_texte(onglet)

    def _onglet_avance(self) -> None:
        onglet = ttk.Frame(self.onglets)
        self.onglets.add(onglet, text="Avancé")
        ttk.Label(onglet,
                  text="⚠ Console UDS manuelle — tu parles directement aux modules. "
                       "Chaque requête est journalisée. Aucune commande d'actionneur "
                       "ne devrait être envoyée sans séquence documentée.",
                  foreground="#B00020", wraplength=900, justify=tk.LEFT,
                  padding=8).pack(anchor="w")
        ligne = ttk.Frame(onglet, padding=8)
        ligne.pack(fill=tk.X)
        ttk.Label(ligne, text="Adresse (hex) :").pack(side=tk.LEFT)
        self.var_adresse = tk.StringVar(value="7E0")
        ttk.Entry(ligne, textvariable=self.var_adresse, width=6).pack(side=tk.LEFT, padx=4)
        ttk.Label(ligne, text="Requête (hex) :").pack(side=tk.LEFT)
        self.var_requete = tk.StringVar(value="3E 00")
        ttk.Entry(ligne, textvariable=self.var_requete, width=40).pack(side=tk.LEFT, padx=4)
        ttk.Button(ligne, text="Envoyer", command=self._envoyer_uds).pack(side=tk.LEFT, padx=6)
        self.texte_avance = self._zone_texte(onglet)

    # --- Files d'interface (thread → UI) --------------------------------

    def _traiter_file_ui(self) -> None:
        try:
            while True:
                fonction = self._file_ui.get_nowait()
                fonction()
        except queue.Empty:
            pass
        self.after(100, self._traiter_file_ui)

    def _poster(self, fonction) -> None:
        self._file_ui.put(fonction)

    def _en_arriere_plan(self, travail, succes=None, echec=None) -> None:
        def boucle():
            try:
                resultat = travail()
            except Exception as e:  # rapporté à l'interface
                if echec:
                    self._poster(lambda e=e: echec(e))
                else:
                    self._poster(lambda e=e: self._statut(f"Échec : {e}"))
                return
            if succes:
                self._poster(lambda: succes(resultat))
        threading.Thread(target=boucle, daemon=True).start()

    def _statut(self, texte: str) -> None:
        self.label_statut.config(text=texte)

    @staticmethod
    def _remplir(texte_widget: tk.Text, contenu: str) -> None:
        texte_widget.delete("1.0", tk.END)
        texte_widget.insert(tk.END, contenu)

    def _ouvrir_dossier(self, dossier: Path) -> None:
        try:
            import os
            os.startfile(str(dossier))  # Windows seulement
        except Exception as e:
            self._statut(f"Dossier : {dossier} ({e})")

    # --- Ports et connexion ----------------------------------------------

    def _rafraichir_ports(self) -> None:
        ports = lister_ports()
        self.combo_port["values"] = [p[0] for p in ports]
        if ports and not self.var_port.get():
            self.var_port.set(ports[0][0])
        self._statut(f"{len(ports)} port(s) COM détecté(s)." if ports
                     else "Aucun port COM détecté — branche l'adaptateur.")

    def _basculer_connexion(self) -> None:
        if self.session.connecte:
            self._terminer_session()
            self.session.fermer()
            self.bouton_connexion.config(text="Connecter")
            self._statut("Déconnecté.")
            return
        port = self.var_port.get().strip()
        if not port:
            messagebox.showwarning(buildinfo.APP_NAME, "Choisis un port COM d'abord.")
            return
        self._statut(f"Connexion à {port}…")

        def travail():
            return self.session.ouvrir(port)

        def succes(message):
            self.bouton_connexion.config(text="Déconnecter")
            self.label_tension.config(
                text=f"Tension : {self.session.derniere_tension or '—'}")
            self.vin_lu = self.session.vin
            self.journal.metadonnees(vehicule=self._nom_vehicule_courant())
            self._apres_connexion()
            self._statut(message)
            self._afficher_infos_vehicule()

        self._en_arriere_plan(travail, succes)

    def _apres_connexion(self) -> None:
        """Reconnaissance du véhicule par le VIN lu."""
        self.session_historique = {
            "debut": datetime.now().astimezone().isoformat(timespec="seconds"),
            "vin": self.vin_lu or "",
            "kilometrage_km": self.session.kilometrage_km,
            "tension": self.session.derniere_tension,
            "modules": [],
            "codes": [],
            "actions": [],
        }
        if self.vin_lu:
            connu = self.registre.par_vin(self.vin_lu)
            if connu is not None:
                self.vehicule_courant = connu
                self.var_vehicule.set(connu.libelle())
                self._statut(f"Véhicule reconnu par son VIN : {connu.libelle()}")
            elif (self.vehicule_courant is not None
                    and not self.vehicule_courant.vin):
                # Fiche sélectionnée créée à la main avant la connexion :
                # on lui rattache le VIN lu plutôt que créer un doublon.
                self.vehicule_courant.vin = self.vin_lu
                self.registre.enregistrer()
                self._statut(
                    f"VIN rattaché à la fiche existante : "
                    f"{self.vehicule_courant.libelle()}")
            else:
                if messagebox.askyesno(
                        buildinfo.APP_NAME,
                        f"VIN lu : {self.vin_lu}\n"
                        "Ce véhicule n'est pas dans ton garage. "
                        "Créer sa fiche maintenant ?"):
                    self._dialogue_ajout_vehicule(vin_prefill=self.vin_lu)
        registry.fusionner_doublons(self.registre)
        # Journal en écriture continue dès que le dossier est connu.
        try:
            self.journal.definir_fichier(self._dossier_courant() / "sessions")
        except Exception:
            pass
        self._sauvegarder_session_historique()

    def _nom_vehicule_courant(self) -> str:
        return self.vehicule_courant.nom if self.vehicule_courant else "Sans véhicule"

    def _dossier_courant(self) -> Path:
        if self.vehicule_courant is not None:
            return self.registre.dossier_vehicule(self.vehicule_courant)
        dossier = self.racine_donnees / "Sans vehicule"
        for sous in ("", "sessions", "rapports", "captures"):
            (dossier / sous).mkdir(parents=True, exist_ok=True)
        return dossier

    def _sauvegarder_session_historique(self) -> None:
        if self.session_historique is not None:
            registry.upsert_session(self._dossier_courant(), self.session_historique)

    def _terminer_session(self) -> None:
        try:
            if self.session_historique is not None:
                fichier = self.journal.enregistrer(self._dossier_courant() / "sessions")
                self._sauvegarder_session_historique()
                self._statut(f"Journal de session enregistré : {fichier.name}")
        except Exception:
            pass

    def _boucle_tension(self) -> None:
        if self.session.connecte and not self.session.moniteur_actif:
            def travail():
                if self.session.moniteur_actif:
                    return None
                self.session.maj_tension()
                return self.session.derniere_tension
            self._en_arriere_plan(
                travail,
                lambda t: self.label_tension.config(text=f"Tension : {t or '—'}"))
        self.after(5000, self._boucle_tension)

    # --- Véhicules ---------------------------------------------------------

    def _rafraichir_vehicules(self) -> None:
        self.combo_vehicule["values"] = [v.libelle() for v in self.registre.vehicules]
        if self.vehicule_courant is not None:
            self.var_vehicule.set(self.vehicule_courant.libelle())

    def _vehicule_choisi(self, _evt=None) -> None:
        choix = self.var_vehicule.get()
        for v in self.registre.vehicules:
            if v.libelle() == choix:
                self.vehicule_courant = v
                break
        self._afficher_historique()

    def _dialogue_ajout_vehicule(self, vin_prefill: str = "") -> None:
        fenetre = tk.Toplevel(self)
        fenetre.title("Ajouter un véhicule")
        fenetre.geometry("420x320")
        champs = {}
        etiquettes = [("nom", "Nom libre (ex. Forester)"), ("annee", "Année"),
                      ("marque", "Marque"), ("modele", "Modèle"),
                      ("vin", "VIN"), ("notes", "Notes")]
        for i, (cle, etiquette) in enumerate(etiquettes):
            ttk.Label(fenetre, text=etiquette).grid(row=i, column=0, sticky="w",
                                                    padx=8, pady=4)
            var = tk.StringVar(value=vin_prefill if cle == "vin" else "")
            ttk.Entry(fenetre, textvariable=var, width=34).grid(row=i, column=1, padx=8)
            champs[cle] = var

        def valider():
            nom = champs["nom"].get().strip()
            if not nom:
                messagebox.showwarning("Ajouter un véhicule",
                                       "Le nom libre est obligatoire.", parent=fenetre)
                return
            vehicule = registry.Vehicule(
                nom=nom, annee=champs["annee"].get().strip(),
                marque=champs["marque"].get().strip(),
                modele=champs["modele"].get().strip(),
                vin=champs["vin"].get().strip().upper(),
                notes=champs["notes"].get().strip())
            self.registre.ajouter(vehicule)
            self.vehicule_courant = vehicule
            self._rafraichir_vehicules()
            self.var_vehicule.set(vehicule.libelle())
            fenetre.destroy()
            self._statut(f"Véhicule ajouté : {vehicule.libelle()}")

        ttk.Button(fenetre, text="Ajouter", command=valider).grid(
            row=len(etiquettes), column=1, pady=10, sticky="e")

    # --- Véhicule / recensement ----------------------------------------------

    def _exiger_connexion(self) -> bool:
        if not self.session.connecte:
            messagebox.showwarning(buildinfo.APP_NAME, "Connecte l'adaptateur d'abord.")
            return False
        return True

    def _afficher_infos_vehicule(self) -> None:
        lignes = [
            f"VIN : {self.session.vin or '—'}",
            f"Protocole : {self.session.protocole or '—'}",
            f"Kilométrage : {self.session.kilometrage_km if self.session.kilometrage_km is not None else '—'}",
            f"Tension : {self.session.derniere_tension or '—'}",
            f"Véhicule sélectionné : {self._nom_vehicule_courant()}",
        ]
        self._remplir(self.texte_vehicule, "\n".join(lignes))

    def _recenser(self) -> None:
        if not self._exiger_connexion():
            return
        self._statut("Recensement des modules…")

        def travail():
            return self.session.recensement()

        def succes(modules):
            lignes = [f"VIN : {self.session.vin or '—'}",
                      f"Protocole : {self.session.protocole or '—'}", ""]
            lignes += [m.ligne_affichage() for m in modules]
            self._remplir(self.texte_vehicule, "\n".join(lignes))
            if self.session_historique is not None:
                self.session_historique["modules"] = [
                    m.adresse_hex for m in modules if m.repond]
                self._sauvegarder_session_historique()
            self._statut("Recensement terminé.")

        self._en_arriere_plan(travail, succes)

    # --- Codes -----------------------------------------------------------------

    def _lire_codes(self) -> None:
        if not self._exiger_connexion():
            return
        self._statut("Lecture des codes…")

        def travail():
            codes = self.session.lire_codes()
            gel = self.session.lire_freeze_frame()
            return codes, gel

        def succes(resultat):
            codes, gel = resultat
            lignes = [f"CODES ({len(codes)})", ""]
            if not codes:
                lignes.append("Aucun code lu.")
            for c in codes:
                lignes.append(f"{c.ligne_affichage()}  [{c.origine}]")
            if gel:
                lignes += ["", "FREEZE FRAME (mode 02)", ""] + gel
            self._remplir(self.texte_codes, "\n".join(lignes))
            if self.session_historique is not None:
                self.session_historique["codes"] = sorted({c.code for c in codes})
                self._sauvegarder_session_historique()
            self._statut(f"{len(codes)} code(s) lu(s).")

        self._en_arriere_plan(travail, succes)

    def _vin_correspond(self) -> bool:
        """Faux si le véhicule sélectionné à la main a un VIN différent
        du VIN lu — bloque l'effacement."""
        if self.vehicule_courant is None:
            return True
        vin_fiche = (self.vehicule_courant.vin or "").strip().upper()
        if not vin_fiche or not self.vin_lu:
            return True
        return vin_fiche == self.vin_lu.strip().upper()

    def _effacer_codes(self) -> None:
        if not self._exiger_connexion():
            return
        if self.session.moniteur_actif:
            messagebox.showwarning(buildinfo.APP_NAME,
                                   "Arrête le moniteur CAN avant d'effacer.")
            return
        if not self._vin_correspond():
            messagebox.showerror(
                buildinfo.APP_NAME,
                "EFFACEMENT BLOQUÉ — le VIN lu "
                f"({self.vin_lu}) ne correspond pas au véhicule "
                f"sélectionné ({self.vehicule_courant.libelle()}, "
                f"VIN {self.vehicule_courant.vin}).\n\n"
                "Sélectionne le bon véhicule ou corrige sa fiche.")
            self.journal.evenement("effacement_bloque", {"motif": "vin_different"})
            return
        if not messagebox.askyesno(
                buildinfo.APP_NAME,
                "Effacer les codes de défaut ?\n\n"
                "Un rapport complet sera archivé automatiquement "
                "AVANT l'effacement, dans le dossier du véhicule."):
            return
        self._statut("Vérification d'immobilité, archivage, effacement…")

        def travail():
            if not self.session.verifier_immobile():
                raise IOError("Véhicule en mouvement (≥ 0,5 km/h) — effacement refusé.")
            if not self.session.derniers_codes:
                self.session.lire_codes()
            gel = self.session.lire_freeze_frame()
            lignes = ["RECENSEMENT"]
            lignes += [m.ligne_affichage() for m in self.session.dernier_recensement]
            lignes += ["", f"CODES ({len(self.session.derniers_codes)})"]
            lignes += [f"{c.ligne_affichage()}  [{c.origine}]"
                       for c in self.session.derniers_codes]
            if gel:
                lignes += ["", "FREEZE FRAME"] + gel
            rapport = "\n".join(lignes)
            fichier = self.journal.archiver_rapport(
                self._dossier_courant() / "rapports", rapport,
                "avant effacement des codes")
            resultats = self.session.effacer_codes()
            return fichier, resultats

        def succes(resultat):
            fichier, resultats = resultat
            lignes = [f"Rapport archivé : {fichier}", "", "RÉSULTATS DE L'EFFACEMENT"]
            lignes += resultats
            lignes.append("")
            lignes.append("Relis les codes pour constater ce qui reste ou revient.")
            self._remplir(self.texte_codes, "\n".join(lignes))
            if self.session_historique is not None:
                self.session_historique.setdefault("actions", []).append("effacement")
                self._sauvegarder_session_historique()
            self._statut("Effacement terminé (rapport archivé avant).")

        self._en_arriere_plan(travail, succes)

    # --- Données en direct --------------------------------------------------------

    def _basculer_direct(self) -> None:
        if self._direct_en_cours:
            self._direct_en_cours = False
            self.bouton_direct.config(text="Démarrer la lecture en direct")
            return
        if not self._exiger_connexion():
            return
        self._direct_en_cours = True
        self.bouton_direct.config(text="Arrêter la lecture en direct")

        def boucle():
            while self._direct_en_cours and self.session.connecte:
                for definition in pids_mod.DEFINITIONS:
                    if not self._direct_en_cours:
                        break
                    try:
                        valeur = self.session.lire_pid(definition)
                    except Exception:
                        valeur = None
                    texte = (pids_mod.formater(definition, valeur)
                             if valeur is not None else "—")
                    iid = self._lignes_direct[definition.pid]
                    self._poster(lambda iid=iid, t=texte:
                                 self.arbre_direct.item(iid, values=(t,)))
                time.sleep(0.3)

        threading.Thread(target=boucle, daemon=True).start()

    # --- Moniteur CAN ---------------------------------------------------------------

    def _basculer_moniteur(self) -> None:
        if self._moniteur_en_cours:
            self.session.arreter_moniteur()
            self._moniteur_en_cours = False
            self.bouton_moniteur.config(text="Démarrer l'écoute")
            self.journal.evenement("moniteur_bilan", {
                "trames_enregistrees": self.session.moniteur_nb_trames,
                "erreur": self.session.moniteur_erreur,
                "lignes_brutes": list(self.session.moniteur_lignes_brutes),
            })
            if self.session.moniteur_erreur:
                self._statut(
                    f"Moniteur arrêté — erreur : {self.session.moniteur_erreur}")
            elif self.session.moniteur_nb_trames == 0:
                self._statut(
                    "Moniteur arrêté — aucune trame enregistrée. "
                    "Le bilan dans le journal de session montre ce que "
                    "l'adaptateur a envoyé.")
            else:
                self._statut(
                    f"Moniteur arrêté — {self.session.moniteur_nb_trames} "
                    "trames dans la capture.")
            return
        if not self._exiger_connexion():
            return
        filtres = set()
        for jeton in self.var_filtres.get().split():
            try:
                filtres.add(int(jeton, 16))
            except ValueError:
                messagebox.showwarning(buildinfo.APP_NAME,
                                       f"Filtre invalide : « {jeton} » (hex attendu).")
                return
        horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
        chemin = self._dossier_courant() / "captures" / f"capture-{horodatage}.csv"
        self._trames_vue.clear()
        self._remplir(self.texte_moniteur, "")

        def rappel(trame, etat):
            self._file_moniteur.put((trame, etat))

        def travail():
            self.session.demarrer_moniteur(filtres, chemin, rappel)
            return chemin

        def succes(chemin):
            self._moniteur_en_cours = True
            self.bouton_moniteur.config(text="Arrêter l'écoute")
            self.label_capture.config(text=f"Capture : {chemin.name}")
            self._statut("Écoute CAN en cours (écoute seule)…")

        self._en_arriere_plan(travail, succes)

    def _traiter_file_moniteur(self) -> None:
        dernier_etat = None
        nb = 0
        try:
            while True:
                trame, etat = self._file_moniteur.get_nowait()
                self._trames_vue.append(trame)
                dernier_etat = etat
                nb += 1
        except queue.Empty:
            pass
        if nb:
            lignes = [f"{t.horodatage_ms}  {t.id:03X}  {vers_texte(t.octets)}"
                      for t in list(self._trames_vue)[-40:]]
            self._remplir(self.texte_moniteur, "\n".join(lignes))
            if dernier_etat is not None:
                e = dernier_etat
                morceaux = []
                if e.vitesse_kmh is not None:
                    morceaux.append(f"vitesse {e.vitesse_kmh:.1f} km/h")
                if e.regime_tr_min is not None:
                    morceaux.append(f"régime {e.regime_tr_min} tr/min")
                if e.roue_avg is not None:
                    morceaux.append(
                        f"roues {e.roue_avg:.1f}/{e.roue_avd:.1f}/"
                        f"{e.roue_arg:.1f}/{e.roue_ard:.1f} km/h")
                if e.frein_actif is not None:
                    morceaux.append("frein actif" if e.frein_actif else "frein relâché")
                self.label_etat_can.config(
                    text="État décodé : " + (" · ".join(morceaux) or "—"))
        self.after(500, self._traiter_file_moniteur)

    # --- Freins / VDC ------------------------------------------------------------------

    def _lire_freins(self) -> None:
        if not self._exiger_connexion():
            return
        self._statut("Lecture du système de freins (VDC)…")

        def travail():
            if not self.session.dernier_recensement:
                self.session.recensement()
            if not self.session.derniers_codes:
                self.session.lire_codes()
            return self.session.dernier_recensement, self.session.derniers_codes

        def succes(resultat):
            modules, codes = resultat
            chassis = [c for c in codes if c.code.startswith(("C", "U"))]
            lignes = ["MODULES"]
            lignes += [m.ligne_affichage() for m in modules]
            lignes += ["", f"CODES CHÂSSIS ET RÉSEAU ({len(chassis)})"]
            if not chassis:
                lignes.append("Aucun code châssis/réseau lu.")
            lignes += [f"{c.ligne_affichage()}  [{c.origine}]" for c in chassis]
            self._remplir(self.texte_freins, "\n".join(lignes))
            self._statut("Écran freins mis à jour (lecture seule).")

        self._en_arriere_plan(travail, succes)

    def _rechercher_ssm(self) -> None:
        if not self._exiger_connexion():
            return
        self._statut("Recherche des modules SSM (init AA, 7E0–7E4)…")

        def travail():
            modules = ssm_mod.recensement_ssm(self.session)
            sondes = ssm_mod.sondes_uds_dormantes(self.session)
            return modules, sondes

        def succes(resultat):
            modules, sondes = resultat
            lignes = ["MODULES SSM (init AA)"]
            lignes += [m.ligne_affichage() for m in modules]
            vdc = next((m for m in modules if m.adresse == 0x7E2), None)
            lignes.append("")
            if vdc is not None and vdc.repond:
                lignes.append("VDC TROUVÉ en SSM à 0x7E2. Prochaine "
                              "étape : sa carte d'adresses DTC.")
            else:
                lignes.append("Le VDC n'a pas répondu à l'init SSM "
                              "à 0x7E2 — voir les sondes ci-dessous.")
            lignes += ["", *sondes.lignes_affichage()]
            self._remplir(self.texte_freins, "\n".join(lignes))
            self._statut("Recherche SSM terminée (journalisée).")

        self._en_arriere_plan(travail, succes)

    def _lire_ssm(self) -> None:
        if not self._exiger_connexion():
            return
        try:
            module = int(self.var_ssm_module.get().strip(), 16)
            adresses = [int(morceau.strip(), 16)
                        for morceau in self.var_ssm_adresses.get().split(",")
                        if morceau.strip()]
        except ValueError:
            messagebox.showwarning(buildinfo.APP_NAME,
                                   "Module et adresses en hexadécimal "
                                   "(ex. module 7E2, adresses 000056, 000057).")
            return
        if not adresses:
            messagebox.showwarning(buildinfo.APP_NAME,
                                   "Donne au moins une adresse mémoire à lire.")
            return
        self._statut(f"Lecture SSM A8 → {module:03X}…")

        def travail():
            return ssm_mod.lire_adresses(self.session, module, adresses)

        def succes(resultat):
            lignes = [f"LECTURE SSM — module {module:03X}"]
            if resultat is None:
                lignes.append("Pas de réponse de lecture (E8) — le module "
                              "n'a pas répondu ou ne parle pas SSM.")
            else:
                lignes += [f"  {adresse:06X} = {valeur:02X} ({valeur})"
                           for adresse, valeur in resultat]
                if len(resultat) < len(adresses):
                    lignes.append(f"({len(adresses) - len(resultat)} "
                                  "adresse(s) sans valeur retournée)")
            self._remplir(self.texte_freins, "\n".join(lignes))
            self._statut("Lecture SSM terminée.")

        self._en_arriere_plan(travail, succes)

    # --- Historique -----------------------------------------------------------------------

    def _historique_courant(self) -> dict:
        return registry.charger_historique(self._dossier_courant())

    def _afficher_historique(self) -> None:
        historique = self._historique_courant()
        sessions = historique.get("sessions", [])
        self.combo_comp_a["values"] = [s.get("debut", "?") for s in sessions]
        self.combo_comp_b["values"] = [s.get("debut", "?") for s in sessions]
        lignes = [f"HISTORIQUE — {self._nom_vehicule_courant()}",
                  f"{len(sessions)} session(s), jamais effacé automatiquement.", ""]
        for s in sessions:
            lignes.append(
                f"{s.get('debut', '?')} · VIN {s.get('vin') or '—'} · "
                f"{s.get('kilometrage_km') if s.get('kilometrage_km') is not None else '—'} km · "
                f"modules {', '.join(s.get('modules', [])) or '—'} · "
                f"codes {', '.join(s.get('codes', [])) or 'aucun'} · "
                f"actions {', '.join(s.get('actions', [])) or '—'}")
        chrono = registry.chronologie_codes(historique)
        if chrono:
            lignes += ["", "CHRONOLOGIE PAR CODE"]
            for code in sorted(chrono):
                e = chrono[code]
                morceau = (f"{code} : première vue {e['premiere_vue']}, "
                           f"dernière vue {e['derniere_vue']}, "
                           f"présent dans {e['nb_sessions_present']} session(s)")
                if e["effacements"]:
                    morceau += f", effacé {len(e['effacements'])} fois"
                if e["reapparitions"]:
                    morceau += f", RÉAPPARU {len(e['reapparitions'])} fois"
                lignes.append(morceau)
        self._remplir(self.texte_historique, "\n".join(lignes))

    def _comparer(self) -> None:
        historique = self._historique_courant()
        sessions = {s.get("debut"): s for s in historique.get("sessions", [])}
        a = sessions.get(self.var_comp_a.get())
        b = sessions.get(self.var_comp_b.get())
        if a is None or b is None:
            messagebox.showwarning(buildinfo.APP_NAME,
                                   "Choisis deux sessions à comparer.")
            return
        diff = registry.comparer_sessions(a, b)
        lignes = [f"COMPARAISON {a.get('debut')} → {b.get('debut')}", "",
                  "APPARUS : " + (", ".join(diff["apparus"]) or "aucun"), "",
                  "DISPARUS : " + (", ".join(diff["disparus"]) or "aucun"), "",
                  "PERSISTANTS : " + (", ".join(diff["persistants"]) or "aucun")]
        self._remplir(self.texte_historique, "\n".join(lignes))

    # --- Console UDS (Avancé) --------------------------------------------------------------

    def _envoyer_uds(self) -> None:
        if not self._exiger_connexion():
            return
        try:
            adresse = int(self.var_adresse.get().strip(), 16)
        except ValueError:
            messagebox.showwarning(buildinfo.APP_NAME, "Adresse hex invalide.")
            return
        requete_texte = self.var_requete.get().strip()
        if not est_hex(requete_texte) or not requete_texte:
            messagebox.showwarning(buildinfo.APP_NAME, "Requête hex invalide.")
            return
        requete = vers_octets(requete_texte)
        self._statut(f"UDS → {adresse:03X}…")

        def travail():
            return self.session.uds(adresse, requete, 4.0)

        def succes(resultat):
            if resultat.classe == "positive":
                detail = f"POSITIVE : {vers_texte(resultat.octets)}"
            elif resultat.classe == "refus":
                detail = (f"REFUS — service 0x{resultat.service:02X}, "
                          f"NRC 0x{resultat.nrc:02X} ({resultat.description_nrc})")
            elif resultat.classe == "erreur_adaptateur":
                detail = f"ERREUR ADAPTATEUR : {resultat.message}"
            else:
                detail = "SILENCE (aucune réponse)"
            ligne = (f"{datetime.now().strftime('%H:%M:%S')}  → {adresse:03X}  "
                     f"{vers_texte(requete)}   ⇒   {detail}\n")
            self.texte_avance.insert(tk.END, ligne)
            self.texte_avance.see(tk.END)
            self._statut("Requête UDS classée : " + resultat.classe)

        self._en_arriere_plan(travail, succes)

    # --- Mise à jour (bouton visible, barre principale) --------------------------------------

    def _verifier_maj(self) -> None:
        self.bouton_maj.config(state=tk.DISABLED)
        self.label_maj.config(text="Vérification en cours…")

        def travail():
            return maj.derniere_release()

        def succes(release):
            self.bouton_maj.config(state=tk.NORMAL)
            etat = maj.comparer(buildinfo.BUILD_NUMBER, release["numero"])
            if etat == "nouveau":
                self.label_maj.config(
                    text=f"Nouveau : build {release['numero']} disponible !")
                self._proposer_maj(release)
            elif etat == "a_jour":
                self.label_maj.config(
                    text=f"À jour — {buildinfo.STAMP}")
                messagebox.showinfo(
                    buildinfo.APP_NAME,
                    f"Lecteur OSBD est à jour.\n\n"
                    f"Version installée : {buildinfo.STAMP}\n"
                    f"Dernière release : {release['tag']}")
            else:
                self.label_maj.config(text=f"Version : {buildinfo.STAMP}")
                messagebox.showwarning(
                    buildinfo.APP_NAME,
                    "Impossible de déterminer le numéro de build de la "
                    f"dernière release ({release['tag']}).")

        def echec(e):
            self.bouton_maj.config(state=tk.NORMAL)
            self.label_maj.config(text=f"Version : {buildinfo.STAMP}")
            messagebox.showwarning(
                buildinfo.APP_NAME,
                f"Vérification impossible (réseau ou dépôt injoignable) :\n{e}")

        self._en_arriere_plan(travail, succes, echec)

    def _proposer_maj(self, release: dict) -> None:
        fenetre = tk.Toplevel(self)
        fenetre.title("Mise à jour disponible")
        fenetre.geometry("460x210")
        ttk.Label(fenetre,
                  text=f"Un build plus récent de Lecteur OSBD existe :\n\n"
                       f"Installé : {buildinfo.STAMP}\n"
                       f"Disponible : build {release['numero']} ({release['tag']})",
                  padding=10).pack(anchor="w")

        def telecharger():
            fenetre.destroy()
            exe = release["exe"]
            if exe is None:
                webbrowser.open(release["page"])
                return
            if maj.est_fige():
                # Bascule en place : téléchargement en « .new » à côté
                # de l'exe courant, renommages, relance (build 3).
                exe_courant = maj.chemin_exe_courant()
                destination = maj.chemin_nouveau(exe_courant)
                self._statut(f"Téléchargement de {exe['nom']}…")

                def travail_bascule():
                    maj.telecharger(exe["url"], destination)
                    return destination

                def succes_bascule(chemin):
                    if not messagebox.askyesno(
                            buildinfo.APP_NAME,
                            f"Build {release['numero']} téléchargé.\n\n"
                            "Redémarrer Lecteur OSBD maintenant pour "
                            "terminer la mise à jour ?"):
                        self._statut(
                            "Mise à jour téléchargée ; elle s'appliquera "
                            "au prochain appui sur « Mettre à jour l'app ».")
                        return
                    try:
                        cible = maj.preparer_bascule(exe_courant, chemin)
                    except OSError as exc:
                        messagebox.showerror(
                            buildinfo.APP_NAME,
                            f"La bascule a échoué : {exc}\n\n"
                            "L'app continue sur la version actuelle.")
                        return
                    maj.relancer(cible)
                    self._fermer()

                self._en_arriere_plan(travail_bascule, succes_bascule)
                return
            destination = Path.home() / "Downloads" / exe["nom"]
            self._statut(f"Téléchargement de {exe['nom']}…")

            def travail():
                maj.telecharger(exe["url"], destination)
                return destination

            def succes(chemin):
                self._statut(f"Nouvel exe téléchargé : {chemin}")
                messagebox.showinfo(
                    buildinfo.APP_NAME,
                    f"Nouvel exe téléchargé :\n{chemin}\n\n"
                    "Ferme Lecteur OSBD, puis lance le nouveau fichier.")

            self._en_arriere_plan(travail, succes)

        boutons = ttk.Frame(fenetre, padding=10)
        boutons.pack(fill=tk.X)
        if release["exe"] is not None:
            ttk.Button(boutons, text="Télécharger le nouvel exe",
                       command=telecharger).pack(side=tk.LEFT)
        ttk.Button(boutons, text="Ouvrir la page GitHub",
                   command=lambda: (webbrowser.open(release["page"]),
                                    fenetre.destroy())).pack(side=tk.LEFT, padx=6)
        ttk.Button(boutons, text="Plus tard",
                   command=fenetre.destroy).pack(side=tk.RIGHT)

    # --- Fermeture ----------------------------------------------------------------------------

    def _fermer(self) -> None:
        self._direct_en_cours = False
        if self.session.moniteur_actif:
            self.session.arreter_moniteur()
            time.sleep(0.3)
        if self.session.connecte:
            self._terminer_session()
        self.session.fermer()
        self.destroy()


def main() -> None:
    Application().mainloop()


if __name__ == "__main__":
    main()
