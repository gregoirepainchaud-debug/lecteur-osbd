"""Tests de la découverte fonctionnelle et de l'accès ciblé aux
modules (decouverte.py) — build 5.

La fixture LIGNES_REELLES est la capture EXACTE de la sonde
fonctionnelle du 2026-11-26 21:25 sur le Forester de Grégoire
(session-20261126-212125.json) : c'est elle qui a révélé le VDC à
0x7B0 avec C1954/C1955/C1984. Si le parseur casse un jour, ce test
le voit contre la réalité, pas contre un exemple inventé.

Lancer : python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lecteur_osbd import codes_base, decouverte
from lecteur_osbd.journal import JournalSession
from lecteur_osbd.uds import ResultatUds

LIGNES_REELLES = [
    '7CC 07 59 02 0A 94 A1 00 0A',
    '7E8 10 FB 59 02 7E 00 01 25',
    '7E8 21 50 00 00 11 40 00 00',
    '7E8 22 21 40 00 04 59 40 00',
    '7E8 23 01 41 20 00 04 20 40',
    '7E8 24 00 04 56 40 00 01 11',
    '7E8 25 40 00 01 28 40 00 00',
    '7E8 26 68 40 00 01 01 40 00',
    '7E8 27 11 60 40 00 21 03 40',
    '7E8 28 00 01 96 40 00 00 18',
    '7E8 29 40 00 00 16 40 00 00',
    '78B 03 59 02 0A',
    '7E8 2A 19 40 00 00 17 40 00',
    '7E8 2B 16 04 20 00 21 9C 40',
    '7E8 2C 00 21 9D 40 00 05 0A',
    '7E8 2D 40 00 24 20 40 00 01',
    '7E8 2E 5B 40 00 01 5A 40 00',
    '7E8 2F 01 4D 40 00 01 4C 40',
    '7E8 20 00 14 51 40 00 14 49',
    '7E8 21 40 00 04 55 40 00 04',
    '7E8 22 41 40 00 24 04 40 00',
    '7E8 23 24 02 40 00 01 3F 40',
    '7E8 24 00 01 3E 40 00 01 3A',
    '7E8 25 40 00 00 0A 40 00 00',
    '7E8 26 0B 40 00 00 0C 40 00',
    '7E8 27 00 0D 40 00 21 96 40',
    '7E8 28 00 21 95 40 00 01 16',
    '7E8 29 40 00 06 0A 40 00 00',
    '7E8 2A 71 40 00 21 9E 40 00',
    '7E8 2B 21 9F 40 00 06 85 40',
    '7E8 2C 00 05 9F 40 00 05 A0',
    '7E8 2D 40 00 05 A1 40 00 05',
    '7E8 2E A6 40 00 05 C0 40 00',
    '7E8 2F 05 9A 40 00 05 A2 40',
    '7E8 20 00 22 70 40 00 22 71',
    '7E8 21 40 00 06 06 40 00 26',
    '7E8 22 A5 40 00 21 83 40 00',
    '7E8 23 04 01 40 00 04 02 40',
    '73D 03 59 02 0A',
    '75A 03 59 02 0A',
    '7B8 03 7F 19 78',
    '7B8 10 0F 59 02 0A 59 54 00',
    '7B8 21 08 59 55 00 0A 59 84',
    '7B8 22 00 0A 00 00 00 00 00',
]



class FausseSession:
    """Session simulée : fonctionnelle fixe, réponses UDS par
    (adresse, requête exacte) ou par fonction de dispatch."""

    def __init__(self, fonctionnelle=None, dispatch=None):
        self.fonctionnelle = fonctionnelle or []
        self.dispatch = dispatch
        self.journal = JournalSession()
        self.journal.demarrer()  # comme à la connexion réelle
        self.derniere_decouverte = None
        self.appels_uds = []

    def requete_fonctionnelle(self, requete, delai_s=3.0):
        return list(self.fonctionnelle)

    def uds(self, adresse, requete, delai_s=4.0):
        self.appels_uds.append((adresse, bytes(requete)))
        if self.dispatch is not None:
            return self.dispatch(adresse, bytes(requete))
        return ResultatUds.silence()


class TestAnalyseFonctionnelle(unittest.TestCase):
    def setUp(self):
        self.modules = decouverte.analyser_lignes_fonctionnelles(LIGNES_REELLES)
        self.par_reponse = {m.reponse: m for m in self.modules}

    def test_six_modules_decouverts(self):
        self.assertEqual(set(self.par_reponse),
                         {0x7CC, 0x7E8, 0x78B, 0x73D, 0x75A, 0x7B8})

    def test_vdc_trouve_a_7b0(self):
        vdc = self.par_reponse[0x7B8]
        self.assertEqual(vdc.requete, 0x7B0)
        self.assertEqual(vdc.nom, "VDC / ABS — freins")
        self.assertTrue(vdc.attente_vue)  # le NRC 0x78 a précédé la réponse
        reels = [(c.code, c.statut) for c in vdc.codes_reels]
        self.assertEqual(reels, [("C1954", 0x08), ("C1955", 0x0A),
                                 ("C1984", 0x0A)])

    def test_climatisation_et_son_capteur_de_soleil(self):
        clim = self.par_reponse[0x7CC]
        self.assertEqual(clim.requete, 0x7C4)
        self.assertEqual(clim.nom, "Climatisation (A/C)")
        self.assertEqual([c.code for c in clim.codes_reels], ["B14A1"])

    def test_ecm_dictionnaire_filtre(self):
        ecm = self.par_reponse[0x7E8]
        self.assertEqual(len(ecm.codes), 62)  # dictionnaire complet
        self.assertEqual({c.code for c in ecm.codes_reels},
                         {"P0001", "P0016"})  # seuls historiques réels

    def test_modules_sans_codes(self):
        for reponse in (0x78B, 0x73D, 0x75A):
            self.assertEqual(self.par_reponse[reponse].codes, [])
            self.assertEqual(self.par_reponse[reponse].codes_reels, [])

    def test_bruit_ignore(self):
        modules = decouverte.analyser_lignes_fonctionnelles(
            ["SEARCHING...", "19 02 FF", "", "STOPPED", "7E8"])
        self.assertEqual(modules, [])

    def test_refus_sec_enregistre(self):
        modules = decouverte.analyser_lignes_fonctionnelles(
            ["7B8 03 7F 19 31"])
        self.assertEqual(len(modules), 1)
        self.assertEqual(modules[0].refus_nrc, 0x31)
        self.assertFalse(modules[0].attente_vue)


class TestUdsAttente(unittest.TestCase):
    def test_traverse_les_reponses_en_attente(self):
        sequence = [ResultatUds.refus(0x19, 0x78),
                    ResultatUds.refus(0x19, 0x78),
                    ResultatUds.positive(b"\x59\x02\x0a")]
        session = FausseSession(dispatch=lambda a, r: sequence.pop(0))
        resultat = decouverte.uds_attente(session, 0x7B0,
                                          b"\x19\x02\xff",
                                          essais=6, pause_s=0)
        self.assertEqual(resultat.classe, "positive")
        self.assertEqual(len(session.appels_uds), 3)

    def test_epuisement_des_essais(self):
        session = FausseSession(
            dispatch=lambda a, r: ResultatUds.refus(0x19, 0x78))
        resultat = decouverte.uds_attente(session, 0x7B0,
                                          b"\x19\x02\xff",
                                          essais=2, pause_s=0)
        self.assertEqual(resultat.classe, "refus")
        self.assertEqual(resultat.nrc, 0x78)
        self.assertEqual(len(session.appels_uds), 3)  # 1 + 2 réessais

    def test_refus_sec_sans_reessai(self):
        session = FausseSession(
            dispatch=lambda a, r: ResultatUds.refus(0x19, 0x31))
        resultat = decouverte.uds_attente(session, 0x7B0,
                                          b"\x19\x02\xff", pause_s=0)
        self.assertEqual(resultat.nrc, 0x31)
        self.assertEqual(len(session.appels_uds), 1)


def _dispatch_identite(adresse, requete):
    """Le VDC (0x7B0) répond aux DID d'identité ; le reste se tait."""
    if adresse != 0x7B0:
        return ResultatUds.silence()
    if requete == b"\x22\xf1\x87":
        return ResultatUds.positive(b"\x62\xf1\x87" + b"PIECE-TEST-123")
    if requete == b"\x22\xf1\x89":
        return ResultatUds.positive(b"\x62\xf1\x89" + b"V9.9")
    if requete == b"\x22\xf1\x90":
        return ResultatUds.positive(b"\x62\xf1\x90" + b"JF2SKEBC0KH580816")
    return ResultatUds.silence()


class TestDecouvrir(unittest.TestCase):
    def test_cartographie_complete(self):
        session = FausseSession(fonctionnelle=LIGNES_REELLES,
                                dispatch=_dispatch_identite)
        modules = decouverte.decouvrir(session)
        vdc = next(m for m in modules if m.requete == 0x7B0)
        self.assertEqual(vdc.piece, "PIECE-TEST-123")
        self.assertEqual(vdc.logiciel, "V9.9")
        self.assertEqual(vdc.vin_lu, "JF2SKEBC0KH580816")
        self.assertIs(session.derniere_decouverte, modules)
        types = [e["type"] for e in session.journal._evenements]
        self.assertIn("decouverte_fonctionnelle", types)


class TestSondesAcces(unittest.TestCase):
    def test_observation_seule_jamais_de_cle(self):
        def dispatch(adresse, requete):
            if requete == b"\x10\x03":
                return ResultatUds.positive(b"\x50\x03\x00\x32\x01\xf4")
            if requete == b"\x27\x01":
                return ResultatUds.positive(b"\x67\x01\xab\xcd\xef\x01")
            if requete == b"\x10\x01":
                return ResultatUds.positive(b"\x50\x01")
            return ResultatUds.silence()

        session = FausseSession(dispatch=dispatch)
        sondes = decouverte.sondes_acces(session, 0x7B0)
        self.assertEqual([nom for nom, _r in sondes], [
            "Session étendue (10 03)",
            "Graine SecurityAccess (27 01)",
            "Retour à la session par défaut (10 01)",
        ])
        requetes = [req for _a, req in session.appels_uds]
        # Aucune clé (27 02) ni aucune autre écriture n'est partie.
        self.assertEqual(requetes,
                         [b"\x10\x03", b"\x27\x01", b"\x10\x01"])
        types = [e["type"] for e in session.journal._evenements]
        self.assertIn("sondes_acces", types)


class TestDescriptionsVdc(unittest.TestCase):
    def test_codes_du_dossier(self):
        for code in ("C1954", "C1955", "C1984", "B14A1"):
            self.assertTrue(codes_base.decrire(code),
                            f"{code} devrait être décrit")
        self.assertIn("maintenance", codes_base.decrire("C1984"))
        self.assertIn("DROIT", codes_base.decrire("C1954"))
        self.assertIn("GAUCHE", codes_base.decrire("C1955"))


if __name__ == "__main__":
    unittest.main()
