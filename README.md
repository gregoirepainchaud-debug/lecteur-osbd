# Lecteur OSBD

App Windows de diagnostic OBD pour les véhicules de Grégoire —
pendant PC de l'app Android « Diag Forester » (bac à sable, build 1
du 2026-11-20), dont elle reprend la logique et les données
(décodage DTC, descriptions hors-ligne dont les codes VDC Subaru du
bulletin 06-77-20R, recensement UDS, sous-ensemble DBC Subaru
Global d'opendbc, effacement toujours archivé, journaux JSON).

Adaptateur visé : **OBDLink EX** (USB, puce STN2230, pont FTDI),
qui apparaît sous Windows comme un port COM. USB seulement,
aucun Bluetooth.

## Utilisation

1. Télécharge `LecteurOSBD.exe` depuis la dernière
   [Release GitHub](../../releases) et lance-le (aucune installation).
2. Branche l'OBDLink EX au véhicule et au PC, choisis le port COM,
   clique **Connecter**.
3. L'app lit le VIN et sélectionne automatiquement la fiche du
   véhicule dans ton garage.

**Mise à jour** : le bouton **« Mettre à jour l'app »**, dans la
barre principale de la fenêtre (toujours visible), vérifie la
dernière Release GitHub, compare avec le tampon de build affiché,
propose le téléchargement du nouvel exe s'il y en a un plus récent,
et dit clairement si l'app est à jour. Jamais de mise à jour
silencieuse.

## Données (jamais effacées automatiquement)

Tout vit dans `%USERPROFILE%\Documents\Lecteur OSBD\` :

- `vehicules.json` — le garage (nom libre, année/marque/modèle, VIN, notes) ;
- `<véhicule>\historique.json` — l'historique permanent : chaque
  session (date, VIN, km, tension, modules, codes, actions),
  chronologie par code (première vue / effacé / réapparu) ;
- `<véhicule>\sessions\` — journaux de session JSON ;
- `<véhicule>\rapports\` — rapports complets (JSON + texte) archivés
  **avant** chaque effacement de codes ;
- `<véhicule>\captures\` — captures du moniteur CAN (CSV compatible
  SavvyCAN, diffusées en continu sur le disque, sans plafond).

Tous ces fichiers sont lisibles sans l'app — c'est le format que
Grégoire passe à Muse pour analyse (voir `METHODE-BYPASS.md` dans
le projet Android : l'humain capture, l'IA lit).

## Portée du build 1

- Connexion : sélecteur de port COM (liste + rafraîchir), essais de
  débits (115200 → 38400 → 9600 → 230400 → 500000), init ELM/STN
  (ATE0/ATL0/ATH0, protocole auto puis repli ATSP6), tension batterie
  (ATRV) rafraîchie aux 5 s.
- Infos véhicule : VIN (mode 09), protocole (ATDP), kilométrage
  PID 0xA6 si publié.
- Garage de véhicules : sélecteur, ajout de fiche, reconnaissance
  automatique par VIN à la connexion ; VIN inconnu → proposition de
  création. Données rangées par véhicule.
- Recensement UDS ISO-TP 0x7E0–0x7E7 (TesterPresent + DID 0xF187 /
  0xF190) : répond / refuse (NRC traduit en français) / silence.
- Codes : modes OBD 03/07/0A + UDS 0x19 par module ; descriptions
  hors-ligne (base Android ~90 codes + codes diesel Mercedes
  DPF/EGR/DEF normalisés) ; **code inconnu = affiché brut, jamais
  de description inventée**. Freeze frame mode 02.
- Effacement : mode 04 + UDS 0x14 par module, **toujours** précédé
  de l'archivage automatique du rapport complet, confirmation
  explicite, journalisé. **Refusé** si le véhicule roule
  (≥ 0,5 km/h) ou si le VIN lu ne correspond pas au véhicule
  sélectionné.
- Données en direct : 14 PID mode 01, unités métriques.
- Moniteur CAN : écoute seule (ATMA), filtres logiciels par ID
  (+ filtre matériel AT CF/CM si un seul ID), décodage DBC Subaru
  (0x002 volant, 0x040 régime/pédale, 0x139 frein, 0x13A vitesses
  de roue, 0x13C statut de frein), vue bornée aux 5 000 dernières
  trames, capture complète sur disque en CSV SavvyCAN.
- Historique par véhicule : sessions, chronologie par code,
  comparaison entre deux sessions (apparus / disparus / persistants).
- Console UDS manuelle (onglet « Avancé », avertissement, adresse +
  requête hex libres, réponse classée positive / NRC / silence,
  tout est journalisé).
- Bouton « Ouvrir le dossier des données ».

## Exclusions (sécurité, non négociables)

- **AUCUNE commande active EPB** (ni mode maintenance, ni
  appliquer/relâcher), aucune écriture autre que l'effacement de
  codes. L'onglet Freins / VDC est en lecture seule, avec
  l'explication du lien EPB↔VDC.
- Aucun envoi automatique des journaux.

## Développement

- Python 3.12 + Tkinter + pyserial. Aucune dépendance lourde.
- Tests des couches pures : `python -m unittest discover -s tests`
  (hex/ELM, DTC, formules PID, ISO-TP, classification UDS/NRC,
  analyse 0x19, DBC sur trames construites, garage + historique,
  logique de mise à jour).
- CI GitHub Actions : tests (Linux) → build Windows (PyInstaller,
  un seul fichier) → Release `build-N` avec `LecteurOSBD.exe` ;
  journal et erreurs publiés sur la branche `ci-logs` (patron
  scanrecus).
- Tampon de build : `lecteur_osbd/buildinfo.py`, « build N · date »
  où N = nombre de commits sur main (calculé avant de commiter,
  +1). La CI vérifie la cohérence. Le compteur ne monte que pour
  un build vert ; CI rouge = on réécrit le même commit.

## Notes pour le build 2 (rien de ceci n'est dans le build 1)

- Endpoint serveur « diag » sur le VPS + envoi silencieux des
  journaux (comme la sauvegarde du Métronome), pour que Muse lise
  les logs sans transfert manuel de fichiers.
- Commandes actives EPB **seulement** après le travail de terrain
  de la méthode Beards (voir `METHODE-BYPASS.md` du projet
  Android) : porte UDS du VDC testée (session étendue, demande de
  seed SecurityAccess), référence saine d'un Subaru de la même
  plateforme en écoute passive — jamais de capture en parallèle
  avec l'outil d'un garagiste (rayé par Grégoire le 2026-11-20).
- Données constructeur Mercedes enrichies (DID UDS pour charge de
  suie DPF, niveau DEF, statut de régénération du Sprinter).
- Journal de session horodaté par action de l'utilisateur
  (bouton testé, cycle d'ignition) — leçon Beards : sans marqueurs
  d'action, un log peut mentir.

## Build 4 (2026-11-26) — chasse au VDC par le SSM

- Constat terrain : la prise OBD du Forester (plateforme globale
  Subaru) est derrière une passerelle — aucun trafic libre n'y
  circule, l'écoute passive y est un corridor vide (ATMA et STMA
  muets, diagnostic parfait). Détail : `NOTES-TERRAIN.md`.
- `ssm.py` : SSM-sur-CAN (protocole constructeur Subaru encapsulé
  dans ISO-TP) — init AA → EA, lecture A8, recensement 7E0–7E4
  (VDC présumé à 7E2 d'après la table d'adressage SSM), sondes
  UDS dormantes (19 02 FF direct + fonctionnel). Onglet
  Freins / VDC : bouton de recherche SSM et outil de lecture A8.
  Lecture seule, comme tout l'onglet.
- Détection STN à la connexion (commande STI) ; le moniteur
  utilise STMA sur les puces ScanTool (filtre matériel ouvert,
  manuel FRPM OBDLink §11.2), ATMA sinon.

## Build 5 (2026-11-26) — le VDC est trouvé, en UDS à 0x7B0

- Percée terrain : la sonde fonctionnelle du build 4 (19 02 FF à
  0x7DF) a fait répondre six modules — dont le VDC à l'adresse
  physique UDS **0x7B0** (réponse 0x7B8), hors de la plage
  0x7E0–0x7E7 du recensement classique. Ses codes confirmés :
  C1954 (actionneur EPB droit), C1955 (actionneur EPB gauche),
  C1984 (mode maintenance des freins actif). L'init SSM-sur-CAN
  est muette partout sur cette génération, témoins inclus : la
  voie SSM est fermée, la voie UDS propriétaire est la bonne.
- `decouverte.py` : analyse des lignes fonctionnelles (réassemblage
  ISO-TP par ID de réponse, NRC 0x78 traversé), cartographie des
  modules mémorisée par véhicule (onglet Véhicule), identité DID
  (F187/F189/F190) de chaque module découvert — 0x7C4 identifié
  comme la climatisation par son code B14A1 (capteur
  d'ensoleillement, faux positif classique à l'ombre).
- Onglet Freins / VDC branché sur 0x7B0 : identité et codes du
  module (descriptions VDC/EPB Subaru ajoutées à la base),
  **effacement de ses codes** (0x14, rapport archivé avant,
  relecture après — procédure d'atelier C1984 : effacer, appliquer
  le frein de stationnement plusieurs fois, relire), et sondes
  d'accès en observation (session étendue 10 03, graine
  SecurityAccess 27 01 — aucune clé n'est calculée ni envoyée).
- Toujours aucune commande d'actionneur : la routine de sortie
  du mode maintenance n'est publiée nulle part (recherche du
  2026-11-26) — elle ne sera pas devinée.
