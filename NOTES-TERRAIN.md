
## 2026-11-26 au soir — écoute CAN : synthèse des tests terminaux
- Adaptateur : OBDLink EX **r2.7.1**, puce **STN2232 v5.10.3** (STI), série **23230298977** (STSN, lu sur photo).
- Avis OBDLink « CAN ERROR » (17 nov. 2026) : EX r2.7.1 fabriqués après juin 2026, série > 223230440700, USB > 5,10 V → coupures de communication. Notre cas : série sous le seuil publié (tel que lu) et symptôme différent (diagnostic impeccable, seule l'écoute passive est muette) → lot rappelé probablement PAS l'explication.
- Terminal direct (PowerShell/COM5) : ATMA **et** STMA (manuel FRPM : STMA = ATMA + filtre matériel « pass all ») ne renvoient QUE l'écho de la commande, moteur en marche, après ATZ/ATSP6/ATH1/0100. Notre app est innocentée.
- Hypothèse dominante : Forester SK (plateforme globale Subaru) = prise OBD derrière une **passerelle centrale** ; aucun trafic libre ne circule sur le segment DLC entre les requêtes de diagnostic. L'écoute passive à la prise serait un corridor vide.
- Suite (recherche à faire au chaud) : joindre le VDC par diagnostic routé — essayer ISO-TP 29 bits (adresses type 18DAxxF1), protocole SSM Subaru, adresses au-delà de 7E0-7E7.

## 2026-11-26 au soir — recherche VDC et build 4
- Hypothèse passerelle CONFIRMÉE dans les faits : comma.ai/openpilot se branche en dérivation à la caméra EyeSight sur tous les SGP (le DLC ne sert qu'à l'alimentation) ; le DBC Subaru Global est documenté à partir de captures prises derrière ce point. Le silence ATMA/STMA au DLC est le comportement attendu de l'architecture — pas un défaut.
- Voie VDC identifiée (recherche sourcée) : le VDC parle **SSM-sur-CAN** (ISO-TP), pas UDS. Table SSM : dst 0x10 ECM → CAN 7E0, 0x18 TCM → 7E1, **0x20 ABS/VDC → 7E2 (présumé)**, 0x28 airbag → 7E3, 0x30 BIU → 7E4. Opcodes CAN : init AA → EA ; lecture A8 00 + adresses 3 octets → E8 (1 octet/adresse). Aucune implémentation publique ne dépasse ECM/TCM : le 7E2 reste à prouver au terrain.
- Point dur connu : le SSM n'a pas de service DTC ; les codes vivent à des adresses mémoire propres au module, non publiées pour le VDC SGP. Si l'init répond à 7E2, l'étape suivante = trouver cette carte (définitions FreeSSM historiques du module ABS dst 0x20, ou autre source).
- Build 4 (v1.3) : module ssm.py (init AA, lecture A8, recensement 7E0–7E4, sondes UDS dormantes 19 02 FF directes + fonctionnelle 7DF avec en-têtes) ; onglet Freins/VDC : bouton « Rechercher les modules SSM » + outil de lecture A8 ; détection STN à la connexion (STI) ; moniteur en STMA si STN. 58 tests + smoke complet (EA simulé à 7E2) + smoke GUI.
- Test terrain build 4 : onglet Freins/VDC → « Rechercher les modules SSM ». Attendu si l'hypothèse est juste : 7E0/7E1 RÉPOND (témoins), 7E2 RÉPOND = VDC trouvé. Envoyer le journal de session.

## 2026-11-26 21:25 — PERCÉE : le VDC trouvé par la sonde fonctionnelle (build 4)
Journal : session-20261126-212125.json.
- Init SSM (AA) : silence PARTOUT, témoins 7E0/7E1 inclus → le SSM-CAN brut (charge utile AA seule) ne passe pas sur cette génération. Hypothèse SSM morte en l'état.
- Sondes UDS directes 19 02 FF à 7E2–7E7 : silence (comme le recensement 3E).
- **Sonde FONCTIONNELLE 19 02 FF à 7DF : SIX modules répondent** — la carte diagnostique réelle de l'auto :
  - 7E0→7E8 ECM : aucun code actif/confirmé (P0001, P0016 historiques 0x20 ; le reste = dictionnaire statuts 0x40).
  - **7B0→7B8 : LE VDC** (UDS, adresse propriétaire hors plage 7E0–7E7 ; répond après un NRC 0x78 « en cours »). 3 DTC, tous confirmés :
    - **C1954** (0x08) — actionneur EPB DROIT défaillant (manuel Subaru VDC : coincement mécanique ou fonctionnement anormal de l'étrier arrière droit).
    - **C1955** (0x0A) — actionneur EPB GAUCHE défaillant.
    - **C1984** (0x0A) — MODE MAINTENANCE DES FREINS ACTIF (« stored when the brake maintenance mode is in progress » ; symptôme : le frein de stationnement ne fonctionne pas).
  - 7C4→7CC : **B14A1** confirmé (0x0A) — module carrosserie à identifier.
  - 735→73D, 752→75A, 783→78B : vivants, zéro DTC.
- Lecture du cas : freins arrière faits au garage → mode maintenance engagé/jamais refermé + les deux actionneurs vus anormaux pendant l'opération (connecteurs cassés réparés par Grégoire, moteurs OK au 12 V). Aucun code de capteur de roue : l'ABS/antipatinage éteints seraient l'état dégradé du VDCCM, pas des capteurs.
- Procédure manuelle C1954 (Legacy BN/BS, même famille VDC) : continuité faisceau VDCCM (B310 broches 34/35) ↔ étrier (R153), courts-circuits, contacts, puis résistance étrier broches 1–2 (< 100 Ω → VDCCM ; sinon étrier).
- Suite : build 5 = découverte fonctionnelle intégrée + lecture ciblée 7B0 (identité DID F187/F189/F190 pour confirmer « VDC ») ; la SORTIE du mode maintenance est une COMMANDE (routine à identifier, probablement UDS 0x31 à 7B0) — territoire nouveau, accord explicite de Grégoire requis avant tout envoi.

## 2026-11-26 21:32 — Résultats de la recherche « routine mode maintenance » (rapport sourcé)
- **La séquence exacte (service/RID/session) de « Brake Maintenance Mode » n'est publiée NULLE PART** (ni capture, ni code, ni doc d'outil ; GitHub/forums/drive2 muets). Pistes restantes si elle devient indispensable : VXDIAG + SSM4 (voie usine accessible), analyse des paquets de définitions Autel/Launch, abonnement STIS + J2534. Ne jamais deviner une routine sur un module de frein.
- **Procédure d'atelier C1984, étape 2 (textuelle)** : « Perform the Clear Memory Mode. Apply the electronic parking brake several times. Read the DTC. » → effacer + cycler le bouton + relire = le test de vérité OFFICIEL. Et : « If the system returns from the brake maintenance mode to the normal mode, the EPB warning light goes off, and DTC is cleared. »
- **Condition d'usine (manuel Forester 2024)** : « When DTC other than C1984 is detected, repair or replace the faulty parts and perform the brake maintenance mode » — avec C1954/C1955 présents, la sortie peut légitimement refuser tant que le module voit une faute d'actionneur.
- **Anecdote utile (Forester 2020, outil Snap-on)** : la sortie du mode exigeait une pression sur la pédale de frein, appliquée FORT et VITE (détection par le capteur de pression maître-cylindre) ; C1984 s'est alors effacé de lui-même, EPB fonctionnel. Même pattern Outback 2016 : échec « no brake pressure received ». → Pendant les cycles du bouton : pédale de frein appuyée fermement.
- **B14A1 identifié** : « Sunload Sensor Circuit Low/Open », surveillé par le module de CLIMATISATION → **0x7C4 = module A/C**. Le manuel avertit : à l'ombre/en intérieur, le capteur peut être diagnostiqué « ouvert » à tort ; test en plein soleil. Le code « confirmé » de 21 h 25 est donc très probablement circonstanciel (tests du soir). À re-vérifier de jour.
- **Données courantes du VDC (liste SSM)** : vitesses de roue, pression maître-cylindre, états et COMPTEURS d'opérations EPB — mais aucun paramètre « courant d'actionneur », et **aucune carte de DID 0x22 publiée** pour le VDC SGP. Découverte des DID = balayage en lecture seule (piste build ultérieur). L'état du mode maintenance se lit sans ambiguïté : c'est C1984 lui-même.
- 0x735 / 0x752 / 0x783 : non identifiés dans les sources ; méthode propre = lire leurs DID d'identité (F187/F189/F190) — intégré à la cartographie du build 5.
- Contexte connecteurs : Subaru a étendu la garantie de la languette de verrouillage du connecteur EPB à 15 ans/km illimité (bulletin 06-87-22R, Legacy/Outback 2015-18, WRX CVT) — le défaut réparé par Grégoire est reconnu dans la famille (son Forester SK n'est pas dans la liste du bulletin).
