"""Treinos dirigidos por som: como fazer o som, o erro típico de quem fala português e itens.

Cada item tem o texto para ler e as palavras-alvo: o retorno do treino olha só o som
treinado nessas palavras, para a resposta ser clara ("think: saiu s").
"""
import random
from datetime import date

from . import db, llm, pron

# how: como produzir. trap: o que o português costuma fazer. check: um jeito de conferir sozinho.
TIPS = {
    "th-voiceless": {
        "how": "Ponha a ponta da língua entre os dentes, aparecendo um pouco, e sopre o ar sem voz. "
               "O som sai pelo vão entre a língua e os dentes de cima.",
        "trap": "Encostar a língua atrás dos dentes vira t (tree) ou s (sink). Usar os lábios vira f.",
        "check": "Ponha o dedo na frente da boca: a língua tem que tocar no dedo.",
    },
    "th-voiced": {
        "how": "A mesma posição do th de think, mas com voz: a garganta vibra. É um 'd' feito com a "
               "língua entre os dentes, sem bater.",
        "trap": "Bater a língua atrás dos dentes vira d: mother sai 'mãder'.",
        "check": "Ponha a mão na garganta: tem que vibrar o tempo todo, e a língua continua entre os dentes.",
    },
    "i-short-long": {
        "how": "O iː de sheep é o nosso i, mais longo, com os lábios esticados num sorriso. O ɪ de ship "
               "não existe em português: é um i relaxado e aberto, quase um ê bem curto.",
        "trap": "Usar o nosso i nos dois: ship vira sheep, sit vira seat, live vira leave.",
        "check": "Em ship, a boca fica solta e o som é curto. Em sheep, os lábios esticam e o som dura mais.",
    },
    "ae-e": {
        "how": "O æ de bad é mais aberto que o nosso é: baixe bem o queixo, como se fosse dizer á e é "
               "ao mesmo tempo. O ɛ de bed é o nosso é.",
        "trap": "Usar o nosso é nos dois: bad vira bed, man vira men.",
        "check": "Na frente do espelho: em bad o queixo desce bem mais do que em bed.",
    },
    "ed": {
        "how": "O -ed tem três sons. Vira t depois de som surdo (k, p, s, sh, ch, f): worked = 'workt'. "
               "Vira d depois de som sonoro (vogal, l, n, m, g, b, v, z): played = 'playd'. "
               "Só ganha sílaba (ɪd) depois de t ou d: wanted, needed, visited.",
        "trap": "Pôr vogal no -ed de toda palavra: worked vira 'work-ed', walked vira 'walk-ed'.",
        "check": "Antes do -ed a palavra termina em t ou d? Se não termina, ela não ganha sílaba nenhuma.",
    },
    "dark-l": {
        "how": "No fim da palavra, encoste a ponta da língua atrás dos dentes de cima e deixe lá até o "
               "som acabar.",
        "trap": "O l final do português vira u: people sai 'pipou', school sai 'skuu'.",
        "check": "Termine a palavra e não solte a língua: ela tem que estar grudada no céu da boca.",
    },
    "final-s": {
        "how": "Termine a palavra com um s ou z que dê para ouvir. Depois de som sonoro sai z (needs, plays); "
               "depois de surdo, s (works, maps).",
        "trap": "Engolir o s final. No inglês isso muda o sentido: work e works, map e maps.",
        "check": "Grave e escute: o s final aparece como um chiado curto no fim da palavra?",
    },
    "aspiration": {
        "how": "No começo da palavra, p, t e k saem com um sopro. Diga 'tank' com a mão na frente da boca "
               "e sinta o ar bater.",
        "trap": "Sem sopro, o nativo ouve b, d e g: tank vira dank, pig vira big.",
        "check": "Segure uma folha de papel na frente da boca: em tank, park e key ela tem que mexer.",
    },
    "final-vowel": {
        "how": "Termine a palavra na consoante e corte o som ali, sem vogal de apoio.",
        "trap": "Pôr um i depois da consoante: big vira 'bigui', dog vira 'dógui'.",
        "check": "A última coisa que sai da sua boca tem que ser a consoante, não uma vogal.",
    },
    "r-initial": {
        "how": "A língua sobe sem encostar em nada e os lábios se arredondam um pouco.",
        "trap": "Usar o rr de carro: red sai 'hed'.",
        "check": "A língua não pode tocar o céu da boca em nenhum momento.",
    },
    "h": {
        "how": "Só ar saindo da garganta, como quando você embaça um vidro.",
        "trap": "Engolir o h: hat vira 'at'.",
        "check": "Com a mão na frente da boca, você sente o ar quente antes da vogal.",
    },
    "s-cluster": {
        "how": "Comece direto no s, sem vogal antes.",
        "trap": "Pôr um e na frente: school vira 'eschool'.",
        "check": "O primeiro som é o chiado do s, não uma vogal.",
    },
    "t-d-palatal": {
        "how": "t e d antes de i continuam t e d, com a língua batendo atrás dos dentes.",
        "trap": "Virar tch e dj, como no português do Sudeste: city vira 'cidji'.",
        "check": "Em city, a língua bate e solta rápido, sem chiado.",
    },
    "final-nasal": {
        "how": "Feche de verdade no fim: lábios juntos no m (team), língua no céu da boca no n (plan).",
        "trap": "Deixar só a vogal nasal, como em 'tim' do português.",
        "check": "No m final os lábios se encostam; no n a língua encosta atrás dos dentes.",
    },
}

# (texto, palavras-alvo). Ordem: pares mínimos, palavras soltas, frases.
ITEMS = {
    "th-voiceless": [
        ("think, sink", ["think"]), ("three, tree", ["three"]), ("thank, tank", ["thank"]),
        ("math, mass", ["math"]), ("both", ["both"]), ("month", ["month"]),
        ("I think three things are worth it.", ["think", "three", "things", "worth"]),
        ("Thanks for both maps.", ["thanks", "both"]),
        ("The theory is thin, I think.", ["theory", "thin", "think"]),
        ("Earth has a thick, healthy forest.", ["earth", "thick", "healthy"]),
    ],
    "th-voiced": [
        ("they, day", ["they"]), ("then, den", ["then"]), ("this", ["this"]), ("mother", ["mother"]),
        ("This is the other one.", ["this", "other"]),
        ("They gathered there together.", ["they", "gathered", "there", "together"]),
        ("My mother likes this weather.", ["mother", "this", "weather"]),
    ],
    "i-short-long": [
        ("ship, sheep", ["ship", "sheep"]), ("live, leave", ["live", "leave"]), ("sit, seat", ["sit", "seat"]),
        ("fill, feel", ["fill", "feel"]), ("bit, beat", ["bit", "beat"]), ("it, eat", ["it", "eat"]),
        ("Sit in this seat.", ["sit", "seat"]),
        ("I live here, but I leave tomorrow.", ["live", "leave"]),
        ("Fill the cup and feel the heat.", ["fill", "feel", "heat"]),
        ("The big ship needs green trees.", ["big", "ship", "green", "trees"]),
    ],
    "ae-e": [
        ("bad, bed", ["bad", "bed"]), ("man, men", ["man", "men"]), ("had, head", ["had", "head"]),
        ("sad, said", ["sad", "said"]), ("pan, pen", ["pan", "pen"]),
        ("The bad man had a red bed.", ["bad", "man", "red", "bed"]),
        ("Pat sat on the mat.", ["pat", "sat", "mat"]),
        ("Ten men said it was bad.", ["ten", "men", "said", "bad"]),
        ("I have a map of the land.", ["map", "land"]),
    ],
    "ed": [
        ("worked", ["worked"]), ("walked", ["walked"]), ("stopped", ["stopped"]), ("talked", ["talked"]),
        ("played", ["played"]), ("called", ["called"]), ("wanted", ["wanted"]), ("needed", ["needed"]),
        ("I worked late and walked home.", ["worked", "walked"]),
        ("We stopped, talked, and laughed.", ["stopped", "talked", "laughed"]),
        ("She played, called, and wanted more.", ["played", "called", "wanted"]),
        ("I trained the model and checked the results.", ["trained", "checked"]),
    ],
    "dark-l": [
        ("people", ["people"]), ("feel", ["feel"]), ("school", ["school"]), ("small", ["small"]),
        ("model", ["model"]), ("all", ["all"]), ("full", ["full"]),
        ("I feel well at school.", ["feel", "well", "school"]),
        ("All the people are small.", ["all", "people", "small"]),
        ("The model is simple and useful.", ["model", "simple", "useful"]),
    ],
    "final-s": [
        ("works", ["works"]), ("needs", ["needs"]), ("uses", ["uses"]), ("maps", ["maps"]), ("plays", ["plays"]),
        ("She works and he plays.", ["works", "plays"]),
        ("The model needs more data.", ["needs"]),
        ("It uses less memory and runs fast.", ["uses", "runs"]),
    ],
    "aspiration": [
        ("ten, den", ["ten"]), ("pig, big", ["pig"]), ("coat, goat", ["coat"]), ("tank", ["tank"]),
        ("park", ["park"]), ("key", ["key"]), ("time", ["time"]),
        ("Take time to park the car.", ["take", "time", "park", "car"]),
        ("Ten people came to the party.", ["ten", "people", "came", "party"]),
    ],
    "final-vowel": [
        ("big", ["big"]), ("dog", ["dog"]), ("job", ["job"]), ("stop", ["stop"]), ("garden", ["garden"]),
        ("I have a big dog.", ["big", "dog"]), ("My job is good.", ["job", "good"]),
    ],
    "r-initial": [("red", ["red"]), ("road", ["road"]), ("river", ["river"]), ("The red river runs right.",
                                                                              ["red", "river", "runs", "right"])],
    "h": [("hat", ["hat"]), ("house", ["house"]), ("He had a hat in his hand.", ["hat", "hand"])],
    "s-cluster": [("school", ["school"]), ("study", ["study"]), ("Spain", ["spain"]),
                  ("I study at a school in Spain.", ["study", "school", "spain"])],
    "t-d-palatal": [("city", ["city"]), ("pretty", ["pretty"]), ("different", ["different"]),
                    ("It is a pretty city.", ["pretty", "city"])],
    "final-nasal": [("team", ["team"]), ("plan", ["plan"]), ("long", ["long"]),
                    ("The team has a long plan.", ["team", "long", "plan"])],
}


def session(tag: str, size: int = 8) -> dict:
    """Um treino: itens do banco (ordem varia por dia) + até 3 frases geradas para você."""
    if tag not in ITEMS:
        raise KeyError(tag)
    base = ITEMS[tag]
    rnd = random.Random(f"{tag}-{date.today()}")
    pairs = [it for it in base if "," in it[0] and not it[0].endswith(".")]
    rest = [it for it in base if it not in pairs]
    rnd.shuffle(pairs)
    rnd.shuffle(rest)
    mine = [(it["text"], it["targets"]) for it in db.drill_items(tag)[:3]]
    picked = (pairs[:3] + mine + rest)[:size]
    return {
        "tag": tag, "label": pron.LABEL[tag], "symbol": pron.SYMBOL[tag], "example": pron.EXAMPLE[tag],
        "tip": TIPS[tag], "items": [{"text": t, "targets": tg} for t, tg in picked],
    }


# --- O que fazer diferente, conforme o que saiu no lugar do som ----------------------------------
# (som, esperado ou None, o que saiu) -> conselho. A primeira regra que bate vale.
_S, _F, _T = {"s", "z", "ʃ", "ʒ"}, {"f", "v"}, {"t", "d", "ts", "dz", "tʃ", "dʒ", "ɾ"}
_FIXES = [
    ("th-voiceless", None, _S, "Saiu s: a ponta da língua ficou atrás dos dentes. Ponha a ponta para fora, entre os "
     "dentes, antes de soltar o ar, e só tire depois que o som acabar."),
    ("th-voiceless", None, _F, "Saiu f: o lábio de baixo encostou nos dentes de cima. Deixe o lábio solto, longe dos "
     "dentes: quem toca os dentes de cima é a língua. No espelho, você tem que ver a língua, não o lábio."),
    ("th-voiceless", None, _T, "Saiu t: a língua bateu e soltou. No θ ela fica parada entre os dentes e o ar sai sem "
     "parar: dá para esticar, θθθθ. Se não dá para esticar, saiu t."),
    ("th-voiceless", None, {"∅"}, "O θ sumiu: comece pelo sopro, com a língua entre os dentes (θθθ), e só depois diga o resto."),
    ("th-voiced", None, _T, "Saiu d: a língua bateu e soltou. No ð ela fica entre os dentes e a voz vibra sem parar, "
     "como um zumbido: ðððð."),
    ("th-voiced", None, _S, "Saiu z: a língua ficou atrás dos dentes. Ponha a ponta entre os dentes e mantenha a voz ligada."),
    ("th-voiced", None, _F, "Saiu v: foi o lábio. Lábio solto; quem toca os dentes de cima é a língua."),
    ("th-voiced", None, {"∅"}, "O ð sumiu: comece com a língua entre os dentes e a voz ligada, ððð, e só depois o resto."),
    ("i-short-long", "ɪ", {"i", "iː", "i5"}, "Saiu o i do português, longo e esticado (sheep). O ɪ é curto e relaxado, "
     "entre o i e o ê: boca menos esticada, sem sorriso, e mais rápido."),
    ("i-short-long", "ɪ", {"eɪ", "e", "ɛ", "ei5"}, "Saiu ê ou ei. O ɪ fica mais perto do i: curto, relaxado, sem escorregar para outro som."),
    ("i-short-long", "iː", None, "Saiu curto. O iː é longo e esticado, com um meio sorriso: segure o som (sheep, seat)."),
    ("ae-e", "æ", {"ɛ", "e", "eɪ"}, "Saiu é. O æ abre mais: desça o queixo como no a, mas deixe a língua na frente, como no é."),
    ("ae-e", "æ", None, "Saiu a. O æ fica entre o a e o é: queixo baixo, como no a, e a língua para a frente."),
    ("ae-e", "ɛ", {"æ"}, "Abriu demais e saiu æ. O ɛ é o é do português (café): queixo mais alto."),
    ("ae-e", "ɛ", None, "Fechou demais. O ɛ é o é aberto do português (café)."),
    ("dark-l", None, None, "O l virou u, como em 'Brasil'. Termine com a ponta da língua encostada atrás dos dentes de "
     "cima e segure um instante: goal, não 'gou'."),
    ("ed", None, None, "Ganhou vogal no -ed. Depois de k, p, s, sh, ch e f, o -ed é só um t colado (walked soa 'walkt'); "
     "depois de vogal ou de b, g, l, m, n, v, z, só um d. Vira sílaba só depois de t ou d."),
    ("final-vowel", None, None, "Ganhou vogal no fim (big-i). Termine fechando a consoante, sem soltar som nenhum depois."),
    ("s-cluster", None, None, "Ganhou um i antes do s (iscool). Comece direto no sss, sem vogal antes: ssss-chool."),
    ("r-initial", None, None, "Saiu o r de 'rato', da garganta. O r do inglês é na boca: ponta da língua um pouco para "
     "trás, sem tocar em nada, lábios um pouco redondos."),
    ("h", None, None, "O h sumiu: solte um sopro leve antes da vogal, como um r de 'rato' bem suave."),
    ("aspiration", None, None, "Faltou o sopro: no começo da palavra, p, t e k soltam ar. Ponha a mão na frente da boca e "
     "sinta o ar (ten, não den)."),
    ("final-nasal", None, None, "O som do fim virou vogal nasal. Feche de verdade: no m os lábios se tocam, no n a língua "
     "toca atrás dos dentes, no ŋ a parte de trás da língua sobe."),
    ("final-s", None, None, "O s do fim sumiu: segure o sss até o fim da palavra."),
    ("t-d-palatal", None, None, "Saiu tchi. Em inglês o t antes de i continua t: ponta da língua atrás dos dentes, sem chiar."),
]


def fix_for(c: dict) -> str:
    """Conselho para a troca que aconteceu ("saiu f" diz o que o lábio fez), ou vazio se não houver."""
    if c.get("ok"):
        return ""
    what = c.get("what") or ""
    exp, heard = (what.split("→", 1) + [""])[:2] if "→" in what else ("", "")
    heard = heard.split(" ")[0]
    for tag, want_exp, heard_in, text in _FIXES:
        if tag == c.get("tag") and (want_exp is None or exp == want_exp) and (heard_in is None or heard in heard_in):
            return text
    return ""


def parts(tag: str, word: str) -> list[str]:
    """O som em partes, para quando a palavra inteira não sai: do som sozinho até a palavra."""
    w = word.lower()
    if tag in ("th-voiceless", "th-voiced"):
        s, mode = ("θ", "sopre, sem voz") if tag == "th-voiceless" else ("ð", "com a voz ligada, como um zumbido")
        if w.startswith("th"):
            stretched = f"{s}{s}{s}… {w[2:]}"
        elif w.endswith("th"):
            stretched = f"{w[:-2]}… {s}{s}{s}"
        else:
            stretched = w.replace("th", f"-{s}{s}{s}-")
        return [f"Só o som, sem palavra: língua entre os dentes, {mode}: {s}{s}{s}{s} por 2 segundos. Três vezes, no espelho.",
                f"O som com vogal, sem tirar a língua antes da vogal: {s}a, {s}i, {s}u.",
                f"Esticado, juntando o resto: {stretched}",
                f"A palavra inteira, devagar e depois no ritmo normal: {w}."]
    if tag == "dark-l":
        return ["Só a língua: encoste a ponta atrás dos dentes de cima e diga llll por 2 segundos.",
                "Vogal e l, sem virar u: a-llll, o-llll, i-llll.",
                f"A palavra devagar, segurando o l: {w}-llll.",
                f"A palavra inteira: {w}."]
    if tag == "ed" and w.endswith("ed"):
        return [f"Só a palavra sem o -ed: {w[:-2]}.",
                f"Junte o fim colado, sem abrir a boca: {w[:-2]}-t (ou -d).",
                f"A palavra inteira, numa sílaba a menos do que parece: {w}."]
    if tag == "r-initial":
        return ["Só o r: ponta da língua para trás, sem tocar em nada: rrrr, como um motor fraco.",
                "O r com vogal: ra, ri, ru.",
                f"A palavra devagar: {w}."]
    if tag == "s-cluster" and w.startswith("s"):
        return ["Só o s: ssss.", f"O s esticado e o resto, sem vogal antes: ssss-{w[1:]}.", f"A palavra: {w}."]
    return []


def judge(tag: str, targets: list[str], checks: list[dict]) -> list[dict]:
    """Só o som treinado, só nas palavras-alvo: o que o retorno do treino mostra."""
    wanted = {t.lower() for t in targets}
    return [{**c, "fix": fix_for(c)} for c in checks if c["tag"] == tag and c["word"].lower() in wanted]


_GEN_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"text": {"type": "string"}, "targets": {"type": "array", "items": {"type": "string"}}},
        "required": ["text", "targets"], "additionalProperties": False,
    }}},
    "required": ["items"], "additionalProperties": False,
}


def sound_words(tag: str, text: str) -> list[str]:
    """As palavras do texto que têm o som, conferidas no dicionário de pronúncia."""
    words = list(dict.fromkeys(w.lower().strip(".,!?;:\"'") for w in text.split()))
    fake = [{**w, "exp": w["phones"], "pairs": [(p, p) for p in w["phones"]], "before": []}
            for w in pron.expected(" ".join(words))]
    real = {word for _, t, word, _, _ in pron.findings(fake) if t == tag}
    return [w for w in words if w in real]


def generate(tag: str, profile: str) -> list[dict]:
    """Frases do seu mundo para treinar o som (Claude), filtradas pelo detector."""
    system = ("You write short English sentences for pronunciation practice for a Brazilian learner. "
              "Sentences must be natural, 6 to 12 words, about the learner's own life and work.")
    prompt = (
        f"Target sound: {pron.LABEL[tag]} (examples: {pron.EXAMPLE[tag]}).\n"
        f"Learner profile (Portuguese):\n{profile}\n\n"
        "Write 5 sentences. Each must contain at least 2 words with the target sound, and list those "
        "words in 'targets' exactly as written in the sentence (lowercase)."
    )
    data = llm.complete_json(system, prompt, _GEN_SCHEMA)
    good = []
    for it in data.get("items", [])[:5]:
        text = it.get("text", "").strip()
        words = {w.lower().strip(".,!?;:\"'") for w in text.split()}
        targets = [t.lower() for t in it.get("targets", []) if t.lower() in words]
        real = set(sound_words(tag, " ".join(targets)))  # o modelo às vezes erra qual palavra tem o som
        targets = [t for t in targets if t in real]
        if text and targets:
            good.append({"text": text, "targets": targets})
    db.add_drill_items(tag, good)
    return good
