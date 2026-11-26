
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
