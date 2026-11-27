"""Tests des couches pures de Lecteur OSBD (aucun matériel requis).

Lancer : python -m unittest discover -s tests -v
"""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lecteur_osbd import canbus, codes_base, dtc, maj, pids, registry, uds
from lecteur_osbd.hexutil import (erreur_connue, lignes_utiles,
                                  octets_depuis_lignes, vers_octets,
                                  vers_texte)
from lecteur_osbd.journal import JournalSession


class TestHexUtil(unittest.TestCase):
    def test_vers_octets(self):
        self.assertEqual(vers_octets("7F 19 31"), bytes([0x7F, 0x19, 0x31]))
        self.assertEqual(vers_octets("7f1931"), bytes([0x7F, 0x19, 0x31]))
        with self.assertRaises(ValueError):
            vers_octets("7F1")
        with self.assertRaises(ValueError):
            vers_octets("ZZ")

    def test_vers_texte(self):
        self.assertEqual(vers_texte(bytes([0x0A, 0xFF])), "0A FF")

    def test_lignes_utiles(self):
        brut = "0100\rSEARCHING...\r41 00 BE 3E B8 11\r\r>"
        lignes = lignes_utiles(brut, "0100")
        self.assertEqual(lignes, ["41 00 BE 3E B8 11"])

    def test_erreur_connue(self):
        self.assertIn("NO DATA", erreur_connue(["NO DATA"]))
        self.assertIn("CAN ERROR", erreur_connue(["CAN ERROR"]))
        self.assertIsNone(erreur_connue(["41 0D 00"]))

    def test_octets_depuis_lignes_avec_compteur(self):
        lignes = ["0: 49 02 01 4A 46", "1: 42 43 44"]
        self.assertEqual(octets_depuis_lignes(lignes),
                         bytes([0x49, 0x02, 0x01, 0x4A, 0x46, 0x42, 0x43, 0x44]))


class TestDtc(unittest.TestCase):
    def test_decoder(self):
        self.assertEqual(dtc.decoder(0x03, 0x00), "P0300")
        self.assertEqual(dtc.decoder(0x43, 0x35), "C0035"[:0] or "C0335")
        self.assertEqual(dtc.decoder(0xC1, 0x11), "U0111")

    def test_analyser_reponse_mode(self):
        octets = bytes([0x43, 0x03, 0x00, 0x01, 0x71, 0x00, 0x00])
        codes = dtc.analyser_reponse_mode(octets, "Moteur")
        self.assertEqual([c.code for c in codes], ["P0300", "P0171"])

    def test_kilometrage_a6(self):
        # 1 543 210 dixièmes de km = 154 321,0 km
        valeur = 1543210
        octets = bytes([0x41, 0xA6, (valeur >> 24) & 0xFF, (valeur >> 16) & 0xFF,
                        (valeur >> 8) & 0xFF, valeur & 0xFF])
        self.assertAlmostEqual(dtc.kilometrage_pid_a6(octets), 154321.0)
        self.assertIsNone(dtc.kilometrage_pid_a6(bytes([0x41])))


class TestCodesBase(unittest.TestCase):
    def test_codes_subaru_vdc_documentes(self):
        self.assertIn("06-77-20R", codes_base.decrire("C1531"))
        self.assertIn("06-77-20R", codes_base.decrire("C1741"))
        self.assertIn("VDC", codes_base.decrire("C1411"))

    def test_diesel_sprinter(self):
        self.assertIn("particules", codes_base.decrire("P2002"))
        self.assertIn("DEF", codes_base.decrire("P20E8"))

    def test_inconnu_jamais_invente(self):
        self.assertEqual(codes_base.decrire("P1234"), "")   # constructeur
        self.assertEqual(codes_base.decrire("C1999"), "")
        self.assertNotEqual(codes_base.decrire("P0401"), "")  # normalisé connu


class TestPids(unittest.TestCase):
    def test_formules(self):
        regime = pids.par_pid(0x0C)
        # 41 0C 1A F8 → (0x1AF8)/4 = 1726 tr/min
        self.assertAlmostEqual(regime.decoder_reponse(
            bytes([0x41, 0x0C, 0x1A, 0xF8]), 0x01), 1726.0)
        temp = pids.par_pid(0x05)
        self.assertAlmostEqual(temp.decoder_reponse(
            bytes([0x41, 0x05, 0x7B]), 0x01), 83.0)
        vitesse = pids.par_pid(0x0D)
        self.assertAlmostEqual(vitesse.decoder_reponse(
            bytes([0x41, 0x0D, 0x64]), 0x01), 100.0)

    def test_freeze_frame_offset(self):
        regime = pids.par_pid(0x0C)
        self.assertAlmostEqual(regime.decoder_reponse(
            bytes([0x41, 0x0C, 0x00, 0x1A, 0xF8]), 0x02), 1726.0)

    def test_pid_supportes(self):
        # 41 00 BE 3E B8 11 : le bit du PID 0x0D (vitesse) est levé
        supportes = pids.pid_supportes(bytes([0x41, 0x00, 0xBE, 0x3E, 0xB8, 0x11]), 0x00)
        self.assertIn(0x0D, supportes)
        self.assertIn(0x0C, supportes)

    def test_formater(self):
        self.assertEqual(pids.formater(pids.par_pid(0x0D), 100.0), "100 km/h")
        self.assertEqual(pids.formater(pids.par_pid(0x42), 12.6), "12.6 V")


class TestUds(unittest.TestCase):
    def test_classifier(self):
        self.assertEqual(uds.classifier(bytes([0x50, 0x03]), 0x10).classe, "positive")
        r = uds.classifier(bytes([0x7F, 0x19, 0x31]), 0x19)
        self.assertEqual(r.classe, "refus")
        self.assertEqual(r.nrc, 0x31)
        self.assertIn("hors plage", r.description_nrc)
        self.assertEqual(uds.classifier(b"", 0x19).classe, "silence")

    def test_nrc_francais(self):
        self.assertEqual(uds.decrire_nrc(0x33), "accès de sécurité refusé")
        self.assertEqual(uds.decrire_nrc(0x7F),
                         "service non supporté dans cette session")

    def test_analyser_dtc_19(self):
        # 59 02 FF | enregistrements de 4 octets : C1531 = 55 31 (+ type 00, statut 09)
        octets = bytes([0x59, 0x02, 0xFF, 0x55, 0x31, 0x00, 0x09,
                        0x01, 0x71, 0x00, 0x08])
        codes = uds.analyser_dtc(octets, "Module 7E5")
        self.assertEqual([c.code for c in codes], ["C1531", "P0171"])
        self.assertEqual(codes[0].statut, 0x09)
        self.assertIn("06-77-20R", codes[0].description)

    def test_analyser_lire_did(self):
        octets = bytes([0x62, 0xF1, 0x90]) + b"JF2SKAAC6KH000000"[:17]
        did, donnees = uds.analyser_lire_did(octets)
        self.assertEqual(did, 0xF190)
        self.assertTrue(uds.texte_did(donnees).startswith("JF2"))

    def test_isotp_roundtrip(self):
        payload = bytes(range(20))
        trames = uds.isotp_encadrer(payload)
        self.assertEqual(trames[0][0], 0x10)
        reassembleur = uds.ReassembleurIsotp()
        resultat = None
        for trame in trames:
            r = reassembleur.nourrir(trame)
            if r is not None:
                resultat = r
        self.assertEqual(resultat, payload)

    def test_isotp_trame_unique(self):
        trames = uds.isotp_encadrer(bytes([0x3E, 0x00]))
        self.assertEqual(trames, [bytes([0x02, 0x3E, 0x00])])
        self.assertEqual(uds.ReassembleurIsotp().nourrir(trames[0]),
                         bytes([0x3E, 0x00]))


class TestCanDbc(unittest.TestCase):
    @staticmethod
    def _trame_le(valeurs_bits):
        le = 0
        for debut, longueur, valeur in valeurs_bits:
            le |= (valeur & ((1 << longueur) - 1)) << debut
        return le.to_bytes(8, "little")

    def test_vitesses_roue_13a(self):
        brut = 1000  # 1000 × 0,057 = 57,0 km/h
        donnees = self._trame_le([(12, 13, brut), (25, 13, brut),
                                  (38, 13, brut), (51, 13, brut)])
        etat = canbus.appliquer(canbus.EtatCan(), 0x13A, donnees)
        self.assertAlmostEqual(etat.roue_avg, 57.0)
        self.assertAlmostEqual(etat.vitesse_roue_max(), 57.0)
        self.assertIsNotNone(canbus.decrire(0x13A, donnees))

    def test_frein_139(self):
        donnees = self._trame_le([(16, 12, 1600), (34, 1, 1), (36, 12, 200)])
        etat = canbus.appliquer(canbus.EtatCan(), 0x139, donnees)
        self.assertAlmostEqual(etat.vitesse_kmh, 90.0)  # 1600 × 0,05625
        self.assertTrue(etat.feux_stop)
        self.assertEqual(etat.pedale_frein_brute, 200)

    def test_volant_002_signe(self):
        donnees = bytes([0xFF, 0x9C, 0, 0, 0, 0, 0, 0])  # -100 → -10,0°
        etat = canbus.appliquer(canbus.EtatCan(), 0x002, donnees)
        self.assertAlmostEqual(etat.angle_volant_deg, -10.0)

    def test_regime_040(self):
        donnees = self._trame_le([(16, 13, 1726), (32, 8, 55)])
        etat = canbus.appliquer(canbus.EtatCan(), 0x040, donnees)
        self.assertEqual(etat.regime_tr_min, 1726)
        self.assertEqual(etat.pedale_accel_brute, 55)

    def test_analyser_ligne(self):
        self.assertEqual(canbus.analyser_ligne("13A 0F 1E 22"),
                         (0x13A, bytes([0x0F, 0x1E, 0x22])))
        self.assertIsNone(canbus.analyser_ligne("pas une trame"))
        self.assertIsNone(canbus.analyser_ligne("13A"))

    def test_ligne_savvycan(self):
        trame = canbus.TrameCan(0x13A, bytes([1, 2, 3]), 1500)
        ligne = canbus.ligne_savvycan(trame, 1.0)
        self.assertTrue(ligne.startswith("0.500000,13A,false,Rx,0,3,1,2,3"))


class TestRegistreHistorique(unittest.TestCase):
    def test_garage_et_vin(self):
        with tempfile.TemporaryDirectory() as tmp:
            registre = registry.Registre.charger(Path(tmp))
            v = registre.ajouter(registry.Vehicule(
                nom="Forester", marque="Subaru", modele="Forester",
                annee="2019", vin="JF2SKAAC6KH000000"))
            self.assertEqual(v.marque_simple, "subaru")
            self.assertIs(registre.par_vin("jf2skaac6kh000000"), v)
            self.assertTrue((Path(tmp) / "Forester" / "sessions").exists())
            sprinter = registry.Vehicule(nom="Sprinter", marque="Mercedes-Benz",
                                         modele="Sprinter 2500")
            self.assertEqual(sprinter.marque_simple, "mercedes")

    def test_upsert_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp)
            s = {"debut": "2026-11-26T10:00:00", "codes": ["P0300"]}
            registry.upsert_session(dossier, s)
            s2 = {"debut": "2026-11-26T10:00:00", "codes": ["P0300", "C1531"]}
            historique = registry.upsert_session(dossier, s2)
            self.assertEqual(len(historique["sessions"]), 1)
            self.assertEqual(historique["sessions"][0]["codes"], ["P0300", "C1531"])

    def test_chronologie_reapparition(self):
        historique = {"sessions": [
            {"debut": "2026-11-01", "codes": ["P0300"], "actions": ["effacement"]},
            {"debut": "2026-11-05", "codes": [], "actions": []},
            {"debut": "2026-11-10", "codes": ["P0300"], "actions": []},
        ]}
        chrono = registry.chronologie_codes(historique)
        self.assertEqual(chrono["P0300"]["premiere_vue"], "2026-11-01")
        self.assertEqual(chrono["P0300"]["effacements"], ["2026-11-01"])
        self.assertEqual(chrono["P0300"]["reapparitions"], ["2026-11-10"])

    def test_comparer_sessions(self):
        a = {"codes": ["P0300", "C1531"]}
        b = {"codes": ["P0300", "P0171"]}
        diff = registry.comparer_sessions(a, b)
        self.assertEqual(diff["apparus"], ["P0171"])
        self.assertEqual(diff["disparus"], ["C1531"])
        self.assertEqual(diff["persistants"], ["P0300"])


class TestMaj(unittest.TestCase):
    def test_numero_build_depuis_tag(self):
        self.assertEqual(maj.numero_build_depuis_tag("build-12"), 12)
        self.assertEqual(maj.numero_build_depuis_tag("v3"), 3)
        self.assertIsNone(maj.numero_build_depuis_tag(""))

    def test_comparer(self):
        self.assertEqual(maj.comparer(1, 2), "nouveau")
        self.assertEqual(maj.comparer(2, 2), "a_jour")
        self.assertEqual(maj.comparer(1, None), "inconnu")


class TestJournal(unittest.TestCase):
    def test_archivage_avant_effacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = JournalSession()
            journal.demarrer()
            journal.evenement("lecture_codes", {"codes": []})
            fichier = journal.archiver_rapport(Path(tmp), "rapport de test",
                                               "avant effacement des codes")
            self.assertTrue(fichier.exists())
            self.assertIn("avant effacement", fichier.read_text(encoding="utf-8"))
            self.assertTrue(list(Path(tmp).glob("rapport-*.json")))


if __name__ == "__main__":
    unittest.main()


class TestBuild2Codes(unittest.TestCase):
    """Correctifs du build 2, prouvés sur les réponses réelles du
    Forester du 2026-11-26."""

    def test_statut_reel(self):
        # Dictionnaire : jamais en panne
        self.assertFalse(dtc.est_reel(0x40))  # testNotCompletedThisCycle
        self.assertFalse(dtc.est_reel(0x50))  # + notCompletedSinceClear
        self.assertFalse(dtc.est_reel(0x00))
        self.assertFalse(dtc.est_reel(None))
        # Pannes : historique, actif, confirmé, en attente
        self.assertTrue(dtc.est_reel(0x60))   # failedSinceLastClear (P0016)
        self.assertTrue(dtc.est_reel(0x01))
        self.assertTrue(dtc.est_reel(0x08))
        self.assertTrue(dtc.est_reel(0x04))

    def test_texte_statut(self):
        self.assertIn("historique", dtc.texte_statut(0x60))
        self.assertIn("actif", dtc.texte_statut(0x01))
        self.assertIn("confirmé", dtc.texte_statut(0x08))

    def test_uds_filtre_sur_reponse_type_denso(self):
        # 59 02 7E puis : P0016 historique (0x60), P2764 dictionnaire (0x40)
        octets = bytes([0x59, 0x02, 0x7E,
                        0x00, 0x16, 0x04, 0x60,
                        0x27, 0x64, 0x00, 0x40])
        tous = uds.analyser_dtc(octets, "Module 7E0")
        self.assertEqual(len(tous), 2)
        reels = [c for c in tous if dtc.est_reel(c.statut)]
        self.assertEqual([c.code for c in reels], ["P0016"])
        self.assertEqual(reels[0].statut, 0x60)

    def test_mode_aligne_normal(self):
        octets = bytes([0x43, 0x01, 0x16, 0x00, 0x00])
        codes = dtc.analyser_reponse_mode(octets, "Moteur (confirmés)")
        self.assertEqual([c.code for c in codes], ["P0116"])

    def test_mode_decalage_terrain(self):
        # Le bogue du 2026-11-26 : un octet parasite avant l'octet de
        # réponse produisait P0043/P0047/P004A. Réponse « aucun code »
        # décalée -> aucun code ; vraie réponse décalée -> le vrai code.
        self.assertEqual(
            dtc.analyser_reponse_mode(bytes([0x00, 0x43, 0x00, 0x00]),
                                        "Moteur (confirmés)"), [])
        codes = dtc.analyser_reponse_mode(
            bytes([0x00, 0x47, 0x01, 0x16]), "Moteur (en attente)")
        self.assertEqual([c.code for c in codes], ["P0116"])

    def test_mode_sans_octet_reponse(self):
        self.assertEqual(
            dtc.analyser_reponse_mode(bytes([0x11, 0x22, 0x33, 0x44]),
                                        "Moteur (confirmés)"), [])


class TestBuild2JournalContinu(unittest.TestCase):
    def test_ecriture_a_chaque_evenement(self):
        with tempfile.TemporaryDirectory() as tmp:
            j = JournalSession()
            j.demarrer()
            chemin = j.definir_fichier(Path(tmp) / "sessions")
            self.assertTrue(chemin.exists())
            j.evenement("recensement", {"modules": []})
            contenu = chemin.read_text(encoding="utf-8")
            self.assertIn("recensement", contenu)
            j.evenement("lecture_codes", {"codes": []})
            contenu = chemin.read_text(encoding="utf-8")
            self.assertIn("lecture_codes", contenu)


class TestBuild2Registre(unittest.TestCase):
    def test_fusion_doublon_vin(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = registry.Registre(Path(tmp))
            r.ajouter(registry.Vehicule(nom="Forester Greg", vin=""))
            r.ajouter(registry.Vehicule(
                nom="Forester Greg", vin="JF2SKEBC0KH580816"))
            self.assertEqual(registry.fusionner_doublons(r), 1)
            self.assertEqual(len(r.vehicules), 1)
            self.assertEqual(r.vehicules[0].vin, "JF2SKEBC0KH580816")

    def test_pas_de_fusion_si_deux_vin(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = registry.Registre(Path(tmp))
            r.ajouter(registry.Vehicule(nom="Auto", vin="VIN1"))
            r.ajouter(registry.Vehicule(nom="Auto", vin="VIN2"))
            self.assertEqual(registry.fusionner_doublons(r), 0)
            self.assertEqual(len(r.vehicules), 2)


class TestBuild3(unittest.TestCase):
    def test_bascule_maj(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "LecteurOSBD.exe"
            exe.write_bytes(b"ANCIEN")
            nouveau = maj.chemin_nouveau(exe)
            nouveau.write_bytes(b"NOUVEAU")
            cible = maj.preparer_bascule(exe, nouveau)
            self.assertEqual(cible, exe)
            self.assertEqual(exe.read_bytes(), b"NOUVEAU")
            self.assertEqual(exe.with_suffix(".old").read_bytes(), b"ANCIEN")
            self.assertFalse(nouveau.exists())
            maj.nettoyer_restes(exe)
            self.assertFalse(exe.with_suffix(".old").exists())
            self.assertEqual(exe.read_bytes(), b"NOUVEAU")

    def test_journal_un_seul_fichier(self):
        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp) / "sessions"
            j = JournalSession()
            j.demarrer()
            continu = j.definir_fichier(dossier)
            j.evenement("recensement", {"modules": []})
            final = j.enregistrer(dossier)
            self.assertEqual(final, continu)
            fichiers = list(dossier.glob("session-*.json"))
            self.assertEqual(len(fichiers), 1)

    def test_modes_par_reponse_pas_de_faux_code_a_la_couture(self):
        # Deux modules répondent « 43 00 » (aucun code) : fusionnés,
        # leurs octets fabriquaient P0043 ; décodés séparément : rien.
        from lecteur_osbd.session import SessionObd
        from lecteur_osbd.journal import JournalSession as JS
        s = SessionObd(JS())
        s.dernier_recensement = []
        reponses = {"03": ["43 00", "43 00"], "07": ["47 00"],
                    "0A": ["4A 00"]}
        s.commande = lambda cmd, delai=5.0: reponses.get(cmd, [])
        s._retour_mode_obd = lambda: None
        # dernier_recensement vide -> recensement() serait appelé ;
        # on le neutralise aussi.
        s.recensement = lambda: []
        codes = s.lire_codes()
        self.assertEqual(codes, [])

    def test_modes_par_reponse_vrai_code(self):
        from lecteur_osbd.session import SessionObd
        from lecteur_osbd.journal import JournalSession as JS
        s = SessionObd(JS())
        reponses = {"03": ["43 01 16 00 00"], "07": [], "0A": []}
        s.commande = lambda cmd, delai=5.0: reponses.get(cmd, [])
        s._retour_mode_obd = lambda: None
        s.recensement = lambda: []
        codes = s.lire_codes()
        self.assertEqual([c.code for c in codes], ["P0116"])


class TestBuild6(unittest.TestCase):
    """Build 6 — terrain du 2026-11-26 au soir : le piège du NRC
    0x78, le journal qui perdait les NRC, le faux verdict « module
    propre », et le nettoyage d'installation qui échouait."""

    def test_refus_conserve_octets_et_nrc(self):
        # Avant le build 6, un refus ne gardait pas ses octets : le
        # journal affichait une réponse vide pour CHAQUE refus.
        r = uds.classifier(bytes([0x7F, 0x19, 0x78]), 0x19)
        self.assertEqual(r.classe, "refus")
        self.assertEqual(r.nrc, 0x78)
        self.assertEqual(r.octets, bytes([0x7F, 0x19, 0x78]))
        r = uds.classifier(bytes([0x7F, 0x22, 0x31]), 0x22)
        self.assertEqual(r.nrc, 0x31)
        self.assertEqual(r.octets, bytes([0x7F, 0x22, 0x31]))

    def test_reponse_tardive_reassemblee(self):
        # La mécanique de l'écoute tardive (session._attendre_reponse_
        # tardive) : trames brutes filtrées par ID de réponse, un
        # premier payload 7F 19 78 à TRAVERSER, puis la vraie réponse
        # ISO-TP multi-trames — ici la capture réelle du VDC.
        lignes = ["7B8 03 7F 19 78",
                  "7B8 10 0F 59 02 0A 59 54 00",
                  "7B8 21 08 59 55 00 0A 59 84",
                  "7B8 22 00 0A 00 00 00 00 00",
                  "7E8 03 59 02 0A"]  # un autre module : ignoré
        reasm = uds.ReassembleurIsotp()
        definitif = None
        for ligne in lignes:
            analyse = canbus.analyser_ligne(ligne)
            self.assertIsNotNone(analyse)
            can_id, donnees = analyse
            if can_id != 0x7B8:
                continue
            payload = reasm.nourrir(donnees)
            if payload is None:
                continue
            r = uds.classifier(payload, 0x19)
            if r.classe == "refus" and r.nrc == 0x78:
                continue
            definitif = r
            break
        self.assertIsNotNone(definitif)
        self.assertEqual(definitif.classe, "positive")
        codes = uds.analyser_dtc(definitif.octets, "Module 7B0")
        self.assertEqual([c.code for c in codes],
                         ["C1954", "C1955", "C1984"])

    def test_nettoyage_robuste_reessaie_en_arriere_plan(self):
        # « L'effacement de l'installation a failed » (Grégoire,
        # 2026-11-26) : le .old verrouillé au premier essai doit être
        # réessayé en arrière-plan jusqu'à disparition, en silence.
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "LecteurOSBD.exe"
            exe.write_bytes(b"NOUVEAU")
            vieux = exe.with_suffix(".old")
            vieux.write_bytes(b"ANCIEN")
            original = Path.unlink
            appels = {"n": 0}

            def capricieux(cible, *a, **k):
                if cible == vieux and appels["n"] == 0:
                    appels["n"] += 1
                    raise OSError("fichier verrouillé (simulé)")
                return original(cible, *a, **k)

            Path.unlink = capricieux
            try:
                survivants = maj.nettoyer_restes(exe, delais=(0.2, 0.4))
                self.assertEqual(survivants, [vieux])  # 1er essai raté
                limite = time.time() + 3.0
                while vieux.exists() and time.time() < limite:
                    time.sleep(0.05)
            finally:
                Path.unlink = original
            self.assertFalse(vieux.exists())  # le réessai a fini le travail
            self.assertEqual(exe.read_bytes(), b"NOUVEAU")

    def test_bascule_avec_vieux_old_impossible_a_supprimer(self):
        # Un .old d'une bascule encore plus ancienne, impossible à
        # supprimer (verrouillé), ne doit pas bloquer la mise à
        # jour : il est écarté sous un nom « .reste-… » que le
        # nettoyage sait retrouver et finir par supprimer.
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "LecteurOSBD.exe"
            exe.write_bytes(b"ANCIEN")
            fige = exe.with_suffix(".old")
            fige.write_bytes(b"TRES VIEUX")
            nouveau = maj.chemin_nouveau(exe)
            nouveau.write_bytes(b"NOUVEAU")
            original = Path.unlink

            def bloque(cible, *a, **k):
                if cible == fige:
                    raise OSError("fichier verrouillé (simulé)")
                return original(cible, *a, **k)

            Path.unlink = bloque
            try:
                cible = maj.preparer_bascule(exe, nouveau)
            finally:
                Path.unlink = original
            self.assertEqual(cible, exe)
            self.assertEqual(exe.read_bytes(), b"NOUVEAU")
            self.assertEqual(exe.with_suffix(".old").read_bytes(), b"ANCIEN")
            restes = maj.nettoyer_restes(exe, delais=())
            self.assertEqual(restes, [])
            self.assertFalse(exe.with_suffix(".old").exists())
            self.assertEqual(list(Path(tmp).glob("*.reste-*")), [])
