# Procédure C1955 — actionneur EPB arrière GAUCHE (Forester 2019)

Source : manuel d'atelier Subaru, procédure « DTC C1955 LH ACTUATOR »
(famille Legacy BN/BS, sulegacy.com — même VDCCM avec EPB intégré que le
Forester SK ; recoupée avec le manuel Legacy 2020 : arbre et seuils
identiques, seuls les numéros de connecteurs changent selon la génération).

État de départ (2026-11-26) : C1954 (droit) RÉGLÉ — l'effacement a tenu et
l'actionneur droit passe son test. Restent C1955 (gauche, faute vivante) et
C1984 (mode maintenance, qui ne peut pas tomber tant que C1955 est actif).

## Avant de commencer

- Auto sur le plat, en P, **roues calées** — le frein de stationnement ne
  fonctionne pas, rien ne retient l'auto à part la transmission.
- Ignition **OFF** avant de débrancher quoi que ce soit.
- Le connecteur de l'étrier arrière gauche : 2 bornes seulement (nº 1 et
  nº 2) — c'est la paire du moteur de l'actionneur. Accès : roue arrière
  gauche retirée, ou par derrière l'étrier selon la place.
- **Ton meilleur outil de comparaison : le côté DROIT.** C'est un circuit
  jumeau, prouvé bon ce soir. À chaque mesure, la même mesure à droite te
  donne la valeur « saine » de TON auto — ça tranche tous les doutes de
  numéros de broches entre générations de manuels.

## Étape 0 — Les yeux avant le multimètre (le suspect nº 1)

Le connecteur gauche est celui que tu as réparé. Regarde-le comme un
étranger : languette de verrouillage cassée ou qui ne clique plus (Subaru
a un bulletin et un kit de réparation juste pour ces languettes — le
connecteur peut sembler branché et ne pas tenir), broches reculées,
vert-de-gris, fil coupé au ras du connecteur, réparation qui a lâché.
Bouge le faisceau pendant que quelqu'un regarde le voyant : si ça
clignote, tu as trouvé. La moitié des C1955 finit ici.

## Étape 1 — Le moteur de l'actionneur gauche, seul

Connecteur de l'étrier gauche DÉBRANCHÉ, ignition OFF.
Multimètre en résistance (Ω) entre les bornes **1 et 2 de l'étrier**
(côté étrier, pas côté faisceau).

- **Moins de 100 Ω** (en pratique, un enroulement de moteur sain lit
  quelques Ω à quelques dizaines d'Ω) → le moteur est électriquement
  intact → la faute est EN AMONT : faisceau, connecteur ou VDCCM.
  Continue à l'étape 2.
- **100 Ω et plus, ou OL (circuit ouvert)** → l'actionneur lui-même est
  mort ou coincé → le manuel dit : remplacer l'étrier arrière gauche
  (l'actionneur se vend avec l'étrier sur cette génération). Arrête ici,
  on discute pièces.

Variante que tu connais déjà : le 12 V direct sur ces deux bornes,
un sens puis l'autre (fils volants fuselés, bref contact). Tu l'avais
fait il y a un an — les deux tournaient. Si le gauche tourne encore
franchement dans les deux sens, son moteur est bon ; s'il grogne,
force ou ne bouge plus, c'est mécanique — et le texte du code dit
exactement ça : « coincement mécanique ou fonctionnement anormal ».

## Étape 2 — Le faisceau, vu du connecteur d'étrier

Connecteur d'étrier gauche toujours débranché, côté FAISCEAU cette fois.

a) **Court-circuit à la masse** — résistance entre chaque borne (1, puis
   2) et une bonne masse châssis (métal nu) : il faut **1 MΩ et plus**
   (OL convient). Moins → le fil frotte quelque part entre l'étrier et
   le VDCCM : réparer le faisceau.
b) **Court-circuit au positif** — ignition ON, multimètre en volts :
   entre chaque borne et la masse : il faut **moins de 1 V**. Plus →
   un fil touche une alimentation quelque part : réparer le faisceau.

## Étape 3 — Continuité bout en bout (seulement si 1 et 2 passent)

Ignition OFF. Débrancher AUSSI le gros connecteur du VDCCM (le module
ABS/VDC dans le compartiment moteur). Résistance entre le VDCCM et le
connecteur d'étrier gauche, fil par fil : il faut **moins de 1 Ω** par fil.

- Référence du manuel BN/BS : VDCCM **(B310) nº 44 ↔ étrier (R154) nº 1**
  et **nº 45 ↔ nº 2** (le droit, lui, est en 34/35). Sur le Forester SK,
  les numéros peuvent différer : fie-toi aux **couleurs des deux fils**
  au connecteur d'étrier, retrouve les mêmes au connecteur VDCCM — et
  valide ta méthode en mesurant d'abord le côté DROIT (34/35 chez
  BN/BS), dont le circuit est prouvé : tu dois y lire < 1 Ω.
- Un fil ouvert ou résistif → réparer le faisceau ou le connecteur
  entre VDCCM et étrier gauche. C'est le verdict le plus probable si
  l'étape 1 a dit « moteur bon » et l'étape 0 n'a rien montré.

## Étape 4 — Verdict

- Étapes 1–3 toutes bonnes, contacts propres → le manuel conclut :
  **remplacer le VDCCM&H/U** (son étage de sortie gauche ne pilote plus
  l'actionneur alors que tout le reste est prouvé). C'est le verdict
  « module » — on en reparle avant toute dépense, il y a la voie
  VXDIAG/SSM4 à considérer pour le confirmer.
- Tout rebrancher, puis le test de vérité avec Lecteur OSBD :
  **effacer les codes du VDC → cycler le bouton EPB (pédale de frein
  appuyée fermement) → cartographier**. C1955 absent = réparé. Ensuite
  seulement, C1984 peut tomber : même séquence, et le mode maintenance
  se termine quand plus aucun autre code ne bloque.

## Seuils à retenir

| Mesure | Où | Bon | Mauvais |
|---|---|---|---|
| Résistance moteur | étrier G, bornes 1–2 | < 100 Ω | ≥ 100 Ω / OL |
| Continuité par fil | VDCCM ↔ étrier G | < 1 Ω | ≥ 1 Ω / OL |
| Fuite à la masse | chaque fil ↔ châssis | ≥ 1 MΩ | < 1 MΩ |
| Tension parasite | chaque fil ↔ masse, ign. ON | < 1 V | ≥ 1 V |
