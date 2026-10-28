"""Uma trava só para o trabalho pesado de CPU (Whisper e modelo de fonemas).

Com 4 núcleos, rodar os dois ao mesmo tempo deixa os dois lentos. A análise de pronúncia
em segundo plano pega a trava por pedaços curtos, então uma fala sua espera no máximo um
pedaço (~2 s) para ser transcrita.
"""
import threading

HEAVY = threading.Lock()
