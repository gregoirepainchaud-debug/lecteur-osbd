"""Tampon de build — règle de Grégoire (2026-10-20) :
« build N · date », où N = nombre de commits sur main calculé AVANT
de commiter (+1). Le compteur ne monte que pour un build passé au
vert en CI ; si la CI est rouge, on réécrit le même commit.
"""

BUILD_NUMBER = 6
BUILD_DATE = "2026-11-26"
VERSION = "1.5"

STAMP = f"build {BUILD_NUMBER} · {BUILD_DATE}"

APP_NAME = "Lecteur OSBD"
GITHUB_REPO = "gregoirepainchaud-debug/lecteur-osbd"
