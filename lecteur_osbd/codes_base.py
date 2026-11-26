"""Base embarquée hors-ligne de descriptions de codes.

Portage de CodesBase.kt (Diag Forester, build 1) + ajouts Mercedes /
diesel (DPF, EGR, DEF/AdBlue) normalisés SAE pour le Sprinter.

Règle d'honnêteté : seuls les codes normalisés (SAE/ISO) et les codes
constructeur documentés publiquement sont décrits. Un code inconnu
retourne une chaîne vide — l'app affiche alors le code brut, sans
inventer de description.
"""

SPECIFIQUES = {
    # --- Moteur / émissions (P0xxx normalisés et fréquents) ---
    "P0011": "Position d'arbre à cames A — calage trop avancé ou performance (rangée 1)",
    "P0014": "Position d'arbre à cames B — calage trop avancé (rangée 1)",
    "P0016": "Corrélation position vilebrequin / arbre à cames (rangée 1, capteur A)",
    "P0017": "Corrélation position vilebrequin / arbre à cames (rangée 1, capteur B)",
    "P0021": "Position d'arbre à cames A — calage trop avancé ou performance (rangée 2)",
    "P0026": "Solénoïde de commande des soupapes d'admission — performance (rangée 1)",
    "P0028": "Solénoïde de commande des soupapes d'admission — performance (rangée 2)",
    "P0101": "Débitmètre d'air (MAF) — signal hors plage ou performance",
    "P0102": "Débitmètre d'air (MAF) — signal faible",
    "P0103": "Débitmètre d'air (MAF) — signal élevé",
    "P0113": "Température d'air d'admission — signal élevé",
    "P0118": "Température du liquide de refroidissement — signal élevé",
    "P0128": "Thermostat — température sous le seuil de régulation",
    "P0131": "Sonde O2 rangée 1 capteur 1 — tension faible",
    "P0133": "Sonde O2 rangée 1 capteur 1 — réponse lente",
    "P0134": "Sonde O2 rangée 1 capteur 1 — aucune activité",
    "P0137": "Sonde O2 rangée 1 capteur 2 — tension faible",
    "P0141": "Sonde O2 rangée 1 capteur 2 — circuit de chauffage",
    "P0171": "Mélange trop pauvre (rangée 1)",
    "P0172": "Mélange trop riche (rangée 1)",
    "P0174": "Mélange trop pauvre (rangée 2)",
    "P0175": "Mélange trop riche (rangée 2)",
    "P0300": "Ratés d'allumage aléatoires ou multiples",
    "P0301": "Ratés d'allumage — cylindre 1",
    "P0302": "Ratés d'allumage — cylindre 2",
    "P0303": "Ratés d'allumage — cylindre 3",
    "P0304": "Ratés d'allumage — cylindre 4",
    "P0327": "Capteur de cliquetis 1 — signal faible",
    "P0335": "Capteur de position du vilebrequin A — circuit",
    "P0340": "Capteur de position d'arbre à cames A — circuit (rangée 1)",
    "P0401": "Recirculation des gaz d'échappement (EGR) — débit insuffisant",
    "P0420": "Efficacité du catalyseur sous le seuil (rangée 1)",
    "P0441": "Système EVAP — débit de purge incorrect",
    "P0442": "Système EVAP — petite fuite détectée",
    "P0455": "Système EVAP — grosse fuite détectée",
    "P0456": "Système EVAP — très petite fuite détectée",
    "P0463": "Capteur de niveau de carburant — signal élevé",
    "P0500": "Capteur de vitesse du véhicule — dysfonctionnement",
    "P0506": "Ralenti plus bas que prévu",
    "P0507": "Ralenti plus haut que prévu",
    "P0600": "Liaison de communication série — dysfonctionnement",
    "P0700": "Système de commande de transmission — demande d'allumage du témoin (code compagnon : lire les codes de la transmission)",
    "P0705": "Capteur de plage de transmission — circuit",
    "P0715": "Capteur de vitesse d'entrée / turbine — circuit",
    "P0720": "Capteur de vitesse de sortie — circuit",
    "P0730": "Rapport de transmission incorrect",
    "P0851": "Interrupteur de point mort (Park/Neutral) — signal faible",
    "P2096": "Correction de carburant après catalyseur — trop pauvre (rangée 1)",
    "P2098": "Correction de carburant après catalyseur — trop pauvre (rangée 2)",
    "P2757": "Solénoïde de pression d'embrayage du convertisseur — performance (CVT Subaru)",
    "P2762": "Solénoïde de pression d'embrayage du convertisseur — signal hors plage (CVT Subaru)",
    "P2763": "Solénoïde de pression d'embrayage du convertisseur — signal élevé (CVT Subaru, code connu sur TR690)",
    "P2764": "Solénoïde de pression d'embrayage du convertisseur — signal faible (CVT Subaru, code connu sur TR690)",
    "P2769": "Solénoïde d'embrayage du convertisseur — signal faible (CVT Subaru)",
    "P2770": "Solénoïde d'embrayage du convertisseur — signal élevé (CVT Subaru)",

    # --- Diesel : DPF, EGR, DEF/AdBlue (normalisés SAE, fréquents Sprinter BlueTEC) ---
    "P0402": "Recirculation des gaz d'échappement (EGR) — débit excessif détecté",
    "P0403": "Commande EGR — circuit",
    "P0404": "Commande EGR — signal hors plage ou performance",
    "P0405": "Capteur de position EGR A — signal faible",
    "P0406": "Capteur de position EGR A — signal élevé",
    "P2002": "Efficacité du filtre à particules diesel (DPF) sous le seuil (rangée 1)",
    "P2003": "Efficacité du filtre à particules diesel (DPF) sous le seuil (rangée 2)",
    "P2031": "Capteur de température des gaz d'échappement, rangée 1 capteur 2 — circuit",
    "P2032": "Capteur de température des gaz d'échappement, rangée 1 capteur 2 — signal faible",
    "P2033": "Capteur de température des gaz d'échappement, rangée 1 capteur 2 — signal élevé",
    "P2080": "Capteur de température des gaz d'échappement, rangée 1 capteur 1 — signal hors plage",
    "P2084": "Capteur de température des gaz d'échappement, rangée 1 capteur 2 — signal hors plage",
    "P242F": "Restriction du filtre à particules diesel — accumulation de cendres",
    "P2452": "Capteur de pression différentielle du DPF — circuit",
    "P2453": "Capteur de pression différentielle du DPF — signal hors plage ou performance",
    "P2454": "Capteur de pression différentielle du DPF — signal faible",
    "P2455": "Capteur de pression différentielle du DPF — signal élevé",
    "P2458": "Durée de régénération du filtre à particules diesel",
    "P2459": "Fréquence de régénération du filtre à particules diesel",
    "P2463": "Restriction du filtre à particules diesel — accumulation de suie",
    "P203B": "Capteur de niveau du liquide réducteur (DEF/AdBlue) — signal hors plage ou performance",
    "P203C": "Capteur de niveau du liquide réducteur (DEF/AdBlue) — signal faible",
    "P203D": "Capteur de niveau du liquide réducteur (DEF/AdBlue) — signal élevé",
    "P2047": "Injecteur de liquide réducteur (DEF) rangée 1 unité 1 — circuit ouvert",
    "P2048": "Injecteur de liquide réducteur (DEF) rangée 1 unité 1 — signal faible",
    "P2049": "Injecteur de liquide réducteur (DEF) rangée 1 unité 1 — signal élevé",
    "P20E8": "Pression du liquide réducteur (DEF) trop faible",
    "P20E9": "Pression du liquide réducteur (DEF) trop élevée",
    "P20EE": "Efficacité du catalyseur SCR / NOx sous le seuil (rangée 1)",
    "P207F": "Qualité du liquide réducteur (DEF/AdBlue)",
    "P2201": "Capteur NOx rangée 1 capteur 1 — signal hors plage ou performance",
    "P2202": "Capteur NOx rangée 1 capteur 1 — signal faible",
    "P2203": "Capteur NOx rangée 1 capteur 1 — signal élevé",
    "P229F": "Capteur NOx rangée 1 capteur 2 — signal hors plage ou performance",
    "P2BA9": "Qualité du liquide réducteur insuffisante (NOx au-dessus du seuil)",

    # --- Châssis normalisés SAE (C0xxx) ---
    "C0035": "Capteur de vitesse de roue avant gauche — circuit",
    "C0038": "Capteur de vitesse de roue avant gauche — signal erratique",
    "C0041": "Capteur de vitesse de roue avant droit — circuit",
    "C0044": "Capteur de vitesse de roue avant droit — signal erratique",
    "C0047": "Capteur de vitesse de roue arrière gauche — circuit",
    "C0050": "Capteur de vitesse de roue arrière droit — circuit",
    "C0053": "Capteur de vitesse de roue arrière droit — signal erratique",
    "C0061": "Capteur d'accélération latérale — circuit",
    "C0063": "Capteur de lacet (yaw) — circuit",
    "C0071": "Capteur d'angle de direction — circuit",
    "C0081": "Indicateur du système ABS — circuit",
    "C0110": "Moteur de pompe ABS — circuit",
    "C0121": "Relais de soupapes ABS — circuit",
    "C0131": "Circuit de pression ABS / antipatinage",
    "C0161": "Interrupteur de frein ABS / antipatinage — circuit",
    "C0196": "Capteur de lacet (yaw) — circuit",
    "C0221": "Capteur de vitesse de roue avant droit — circuit ouvert",
    "C0222": "Capteur de vitesse de roue avant gauche — signal manquant",
    "C0223": "Capteur de vitesse de roue avant droit — signal manquant",
    "C0225": "Capteur de vitesse de roue avant gauche — fréquence anormale",
    "C0226": "Capteur de vitesse de roue avant droit — fréquence anormale",
    "C0227": "Capteur de vitesse de roue arrière gauche — fréquence anormale",
    "C0229": "Capteur de vitesse de roue arrière droit — fréquence anormale",
    "C0245": "Erreur de fréquence des capteurs de vitesse de roue",
    "C0265": "Relais du module de frein électronique — circuit",
    "C0550": "Module de commande — performance interne",
    "C0561": "Système désactivé — information enregistrée",

    # --- Châssis Subaru documentés (module VDC, bulletins publics) ---
    "C1411": "Module de commande électrique VDC — la demande de pression du frein de stationnement électronique ne s'exécute pas (symptômes possibles : ABS, VDC, aide au démarrage en côte et EyeSight inopérants)",
    "C1531": "VDC — le module juge une anomalie quand une légère pression sur la pédale persiste après le relâchement du frein de stationnement électronique (bulletin Subaru 06-77-20R)",
    "C1741": "VDC — variante du C1531 : pression légère sur la pédale sans allumer les feux stop, jugée anomalie par le module (bulletin Subaru 06-77-20R)",

    # --- Réseau (U0xxx normalisés fréquents) ---
    "U0100": "Perte de communication avec le module moteur (ECM)",
    "U0101": "Perte de communication avec le module de transmission (TCM)",
    "U0121": "Perte de communication avec le module ABS",
    "U0126": "Perte de communication avec le capteur d'angle de direction",
    "U0155": "Perte de communication avec le tableau de bord",
    "U0401": "Données invalides reçues du module moteur",
    "U0415": "Données invalides reçues du module ABS",
}


def decrire(code: str) -> str:
    """Description d'un code, ou chaîne vide si inconnu de la base."""
    if code in SPECIFIQUES:
        return SPECIFIQUES[code]
    return _generique(code)


def _generique(code: str) -> str:
    """Familles normalisées : un libellé de famille honnête vaut mieux
    qu'une fausse précision. Les codes constructeur (x1xxx et plus,
    hors entrées spécifiques) restent sans description."""
    if len(code) < 2:
        return ""
    if code[1] != "0":
        return ""  # code constructeur : pas de description inventée
    if code[0] == "P":
        troisieme = code[2] if len(code) > 2 else ""
        return {
            "0": "Code moteur normalisé (groupe mesure carburant et air)",
            "1": "Code moteur normalisé (groupe carburant et air)",
            "2": "Code moteur normalisé (groupe injecteurs / admission)",
            "3": "Code moteur normalisé (groupe allumage / ratés)",
            "4": "Code moteur normalisé (groupe contrôle d'émissions auxiliaire)",
            "5": "Code moteur normalisé (groupe vitesse et ralenti)",
            "6": "Code moteur normalisé (groupe module de commande)",
            "7": "Code normalisé (groupe transmission)",
            "8": "Code normalisé (groupe transmission)",
            "9": "Code normalisé (groupe transmission)",
        }.get(troisieme, "Code moteur normalisé")
    if code[0] == "C":
        return "Code châssis normalisé"
    if code[0] == "B":
        return "Code carrosserie normalisé"
    if code[0] == "U":
        return "Code réseau normalisé (communication entre modules)"
    return ""
