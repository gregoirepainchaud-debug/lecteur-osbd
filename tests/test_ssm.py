"""Tests de la couche SSM-sur-CAN (ssm.py) avec une session simulée.

Lancer : python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lecteur_osbd import ssm
from lecteur_osbd.journal import JournalSession
from lecteur_osbd.uds import ResultatUds


class FausseSession:
    """Session simulée : reponses_brutes[adresse] = octets ou None ;
    reponses_uds[adresse] = classe ; fonctionnelle = lignes brutes."""

    def __init__(self, reponses_brutes=None, reponses_uds=None,
                 fonctionnelle=None):
        self.reponses_brutes = reponses_brutes or {}
        self.reponses_uds = reponses_uds or {}
        self.fonctionnelle = fonctionnelle or []
        self.journal = JournalSession()
        self.appels_bruts = []
        self.appels_uds = []

    def requete_brute(self, adresse, requete, delai_s=4.0):
        self.appels_bruts.append((adresse, requete))
        return self.reponses_brutes.get(adresse)

    def uds(self, adresse, requete, delai_s=4.0):
        self.appels_uds.append((adresse, requete))
        classe = self.reponses_uds.get(adresse, "silence")
        if classe == "positive":
            return ResultatUds.positive(b"\x59\x02\xff")
        if classe == "refus":
            return ResultatUds.refus(requete[0], 0x31)
        return ResultatUds.silence()

    def requete_fonctionnelle(self, requete, delai_s=3.0):
        return list(self.fonctionnelle)


class TestConstructionLecture(unittest.TestCase):
    def test_une_adresse(self):
        # Exemple réel reproduit publiquement (Torque/ActiveOBD, TCM) :
        # A8 00 + adresse 0x000056.
        self.assertEqual(ssm.construire_lecture([0x000056]),
                         bytes([0xA8, 0x00, 0x00, 0x00, 0x56]))

    def test_plusieurs_adresses(self):
        self.assertEqual(
            ssm.construire_lecture([0x000001, 0xABCDEF]),
            bytes([0xA8, 0x00, 0x00, 0x00, 0x01, 0xAB, 0xCD, 0xEF]))

    def test_adresse_hors_plage(self):
        with self.assertRaises(ValueError):
            ssm.construire_lecture([0x1000000])


class TestAnalyseLecture(unittest.TestCase):
    def test_reponse_complete(self):
        reponse = bytes([0xE8, 0x7A, 0x00])
        self.assertEqual(
            ssm.analyser_reponse_lecture(reponse, [0x10, 0x11]),
            [(0x10, 0x7A), (0x11, 0x00)])

    def test_mauvais_opcode(self):
        self.assertIsNone(
            ssm.analyser_reponse_lecture(bytes([0x7F, 0xA8]), [0x10]))

    def test_silence(self):
        self.assertIsNone(ssm.analyser_reponse_lecture(None, [0x10]))
        self.assertIsNone(ssm.analyser_reponse_lecture(b"", [0x10]))

    def test_reponse_courte(self):
        reponse = bytes([0xE8, 0x42])
        self.assertEqual(
            ssm.analyser_reponse_lecture(reponse, [0x10, 0x11]),
            [(0x10, 0x42)])


class TestRecensementSsm(unittest.TestCase):
    def test_vdc_trouve(self):
        session = FausseSession(reponses_brutes={
            0x7E0: bytes([0xEA, 0x10, 0xAA]),
            0x7E1: bytes([0xEA, 0x18]),
            0x7E2: bytes([0xEA, 0x20, 0x55]),
        })
        resultats = ssm.recensement_ssm(session)
        par_adresse = {r.adresse: r for r in resultats}
        self.assertTrue(par_adresse[0x7E0].repond)
        self.assertTrue(par_adresse[0x7E1].repond)
        self.assertTrue(par_adresse[0x7E2].repond)
        self.assertFalse(par_adresse[0x7E3].repond)
        self.assertFalse(par_adresse[0x7E4].repond)
        # Chaque init a bien envoyé l'opcode AA seul.
        self.assertTrue(all(req == b"\xAA"
                            for _adr, req in session.appels_bruts))

    def test_reponse_non_ssm_ne_compte_pas(self):
        session = FausseSession(reponses_brutes={
            0x7E2: bytes([0x7F, 0x10, 0x11]),  # refus UDS, pas un EA
        })
        resultats = ssm.recensement_ssm(session)
        vdc = next(r for r in resultats if r.adresse == 0x7E2)
        self.assertFalse(vdc.repond)


class TestLectureAdresses(unittest.TestCase):
    def test_lecture(self):
        session = FausseSession(reponses_brutes={
            0x7E2: bytes([0xE8, 0x99]),
        })
        self.assertEqual(ssm.lire_adresses(session, 0x7E2, [0x000056]),
                         [(0x000056, 0x99)])
        self.assertEqual(session.appels_bruts[0][1],
                         bytes([0xA8, 0x00, 0x00, 0x00, 0x56]))


class TestSondesDormantes(unittest.TestCase):
    def test_sondes(self):
        session = FausseSession(
            reponses_uds={0x7E2: "positive"},
            fonctionnelle=["7EA 59 02 FF C1 23 28"],
        )
        resultat = ssm.sondes_uds_dormantes(session)
        self.assertEqual(resultat.directes[0], (0x7E2, "positive"))
        self.assertTrue(all(classe == "silence"
                            for _a, classe in resultat.directes[1:]))
        self.assertEqual(resultat.fonctionnelle,
                         ["7EA 59 02 FF C1 23 28"])
        lignes = resultat.lignes_affichage()
        self.assertTrue(any("7EA" in l for l in lignes))


if __name__ == "__main__":
    unittest.main()
