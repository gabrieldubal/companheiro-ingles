"""Detector de pronúncia por fonemas.

Pipeline:
  1. o wav2vec2 de fonemas (Meta) escuta o áudio e devolve os sons que você produziu;
  2. o dicionário CMU dá os sons esperados de cada palavra (inglês americano);
  3. um alinhamento (Needleman-Wunsch) casa esperado com ouvido, som a som;
  4. regras por som dizem o que aconteceu com cada alvo (th, ɪ/iː, -ed, l no fim...).

Validado em 27/10 com 214 falas de nativos reais (lab/nativos.py): depois do ajuste das
regras, o ruído ficou em no máximo 2,5% por som. As taxas dos nativos estão em NATIVE_RATE.

Se o PyTorch não estiver instalado, available() devolve False e o app segue sem pronúncia.
"""
import queue
import re
import threading
import time
import traceback

from . import config
from .cpu import HEAVY

MODEL = "facebook/wav2vec2-lv-60-espeak-cv-ft"
SR = 16000

# --- 1. O modelo ---------------------------------------------------------------------

_model = None
_load_lock = threading.Lock()
_load_error = None


def available() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


def status() -> str:
    if not available():
        return "desligado (falta o PyTorch: veja requirements.txt)"
    if _load_error:
        return f"erro ao carregar: {_load_error}"
    return "pronto" if _model else "carregando"


def load():
    global _model, _load_error
    with _load_lock:
        if _model is None and _load_error is None:
            try:
                from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC, Wav2Vec2PhonemeCTCTokenizer

                t0 = time.time()
                fe = Wav2Vec2FeatureExtractor.from_pretrained(MODEL)
                tok = Wav2Vec2PhonemeCTCTokenizer.from_pretrained(MODEL, do_phonemize=False)
                model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval()
                _model = (fe, tok, model)
                print(f"[pron] modelo de fonemas carregado em {time.time() - t0:.0f}s")
            except Exception as e:  # sem internet na primeira vez, disco cheio...
                _load_error = str(e)[:200]
                print(f"[pron] não carregou: {_load_error}")
    return _model


# Alguns sons vêm grudados num token só ("ɑːɹ"); separo para casar com o dicionário.
_SPLIT = {"ɑːɹ": ["ɑː", "ɹ"], "ɔːɹ": ["ɔː", "ɹ"], "ɪɹ": ["ɪ", "ɹ"], "ɛɹ": ["ɛ", "ɹ"],
          "ʊɹ": ["ʊ", "ɹ"], "aɪɚ": ["aɪ", "ɚ"], "aɪə": ["aɪ", "ə"],
          "əl": ["ə", "l"]}  # l silábico de "vegetable": sem separar, parecia "l sumiu"


def recognize(samples) -> list[str]:
    import torch

    loaded = load()
    if loaded is None:
        raise RuntimeError(status())
    fe, tok, model = loaded
    with HEAVY, torch.inference_mode():
        logits = model(fe(samples, sampling_rate=SR, return_tensors="pt").input_values).logits
    phones = tok.decode(logits.argmax(-1)[0]).split()
    return [q for p in phones for q in _SPLIT.get(p, [p])]


# --- 2. A pronúncia esperada ---------------------------------------------------------

ARPA = {
    "AA": "ɑː", "AE": "æ", "AW": "aʊ", "AY": "aɪ", "EH": "ɛ", "EY": "eɪ", "OW": "oʊ", "OY": "ɔɪ",
    "UH": "ʊ", "UW": "uː", "AO": "ɔː", "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "F": "f", "G": "ɡ",
    "HH": "h", "JH": "dʒ", "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ", "P": "p", "R": "ɹ",
    "S": "s", "SH": "ʃ", "T": "t", "TH": "θ", "V": "v", "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ",
}
_EXTRA = {"machu": "m ɑː tʃ uː", "picchu": "p iː tʃ uː"}
_DIGITS = "zero one two three four five six seven eight nine".split()
_cmu = None


def _arpa(sym: str) -> str:
    base, stress = re.match(r"([A-Z]+)(\d?)", sym).groups()
    if base == "AH":
        return "ə" if stress == "0" else "ʌ"
    if base == "ER":
        return "ɚ" if stress == "0" else "ɜː"
    if base == "IY":
        return "i" if stress == "0" else "iː"
    if base == "IH":
        return "ɪ"
    return ARPA[base]


# Palavra fora do dicionário (nome, sigla): soletração grosseira só para "ocupar o lugar"
# no alinhamento. Essas palavras nunca geram checagem.
_G2P = [("tch", ["tʃ"]), ("sh", ["ʃ"]), ("ch", ["tʃ"]), ("th", ["θ"]), ("ph", ["f"]), ("ng", ["ŋ"]),
        ("ck", ["k"]), ("qu", ["k", "w"]), ("ee", ["iː"]), ("oo", ["uː"]), ("a", ["æ"]), ("e", ["ɛ"]),
        ("i", ["ɪ"]), ("o", ["ɑː"]), ("u", ["ʌ"]), ("y", ["i"]), ("x", ["k", "s"]), ("c", ["k"]),
        ("g", ["ɡ"]), ("j", ["dʒ"]), ("r", ["ɹ"])]


def _crude(token: str) -> list[str]:
    out, t = [], token.lower()
    while t:
        for pat, ph in _G2P:
            if t.startswith(pat):
                out += ph
                t = t[len(pat):]
                break
        else:
            if t[0].isalpha():
                out.append(t[0])
            t = t[1:]
    return out


def _word(raw: str) -> dict:
    """Uma palavra (como o Whisper ou a frase a escreve) -> fonemas esperados."""
    global _cmu
    if _cmu is None:
        import cmudict

        _cmu = cmudict.dict()
    phones, stressed, oov = [], set(), False
    for tok in re.findall(r"[A-Za-z']+|\d", raw):
        key = tok.lower().strip("'")
        if tok.isdigit():
            key = _DIGITS[int(tok)]
            oov = True
        if key in _EXTRA:
            phones += _EXTRA[key].split()
        elif key in _cmu:
            arpa = _cmu[key][0]
            stressed |= {len(phones) + i for i, s in enumerate(arpa) if s.endswith(("1", "2"))}
            phones += [_arpa(s) for s in arpa]
        else:
            phones += _crude(key)
            oov = True
    return {"word": re.sub(r"[^\w'-]", "", raw), "phones": phones, "stressed": stressed, "oov": oov}


def expected(text_or_words) -> list[dict]:
    raw = text_or_words.split() if isinstance(text_or_words, str) else text_or_words
    return [w for w in (_word(r) for r in raw) if w["phones"]]


# --- 3. Alinhamento -------------------------------------------------------------------

_VOWEL_CHARS = set("aeiouæɑɒɔəɛɜɪʊʌɐᵻɚɝ")
# Diferenças que não são erro: variantes do mesmo som, o flap americano (city = "ciɾy").
_CANON = {"ɑ": "ɑː", "ɔ": "ɔː", "u": "uː", "ɐ": "ə", "ʌ": "ə", "ᵻ": "ə", "ɜː": "ɚ", "ɝ": "ɚ",
          "o": "oʊ", "əʊ": "oʊ"}
_FLAP = {"ɾ", "t", "d"}
GAP = 0.7


def is_vowel(p: str) -> bool:
    return any(ch in _VOWEL_CHARS for ch in p)


def _canon(p: str) -> str:
    return _CANON.get(p, p)


def _cost(a: str, b: str) -> float:
    if _canon(a) == _canon(b) or ({a, b} <= _FLAP and "ɾ" in (a, b)):
        return 0.0
    if is_vowel(a) and is_vowel(b):
        return 0.5
    if not is_vowel(a) and not is_vowel(b):
        return 0.6
    return 1.0


def align(exp: list[str], rec: list[str]) -> list[tuple]:
    """Needleman-Wunsch: lista de pares (índice esperado ou None, índice ouvido ou None)."""
    # Guarda a direção de cada célula (0 = diagonal, 1 = só esperado, 2 = só ouvido) em vez de
    # recalcular na volta: comparar floats com == falhava por arredondamento (0,7 * 3 != 0,7 * 2 + 0,7).
    n, m = len(exp), len(rec)
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    move = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        score[i][0], move[i][0] = score[i - 1][0] + GAP, 1
    for j in range(1, m + 1):
        score[0][j], move[0][j] = score[0][j - 1] + GAP, 2
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            options = (score[i - 1][j - 1] + _cost(exp[i - 1], rec[j - 1]),
                       score[i - 1][j] + GAP, score[i][j - 1] + GAP)
            best = min(range(3), key=options.__getitem__)
            score[i][j], move[i][j] = options[best], best
    pairs, i, j = [], n, m
    while i > 0 or j > 0:
        mv = move[i][j]
        if mv == 0:
            pairs.append((i - 1, j - 1)); i -= 1; j -= 1
        elif mv == 1:
            pairs.append((i - 1, None)); i -= 1
        else:
            pairs.append((None, j - 1)); j -= 1
    return pairs[::-1]


def _starts_s_cluster(phones: list[str]) -> bool:
    return len(phones) > 1 and phones[0] == "s" and not is_vowel(phones[1])


def by_word(words: list[dict], rec: list[str]) -> list[dict]:
    """Distribui o que foi ouvido pelas palavras esperadas.

    Som inserido vai para a palavra anterior (é onde mora a vogal extra do fim: "bigi"),
    exceto vogal logo antes de "s + consoante", que é o "e" de "eschool".
    """
    flat, owner = [], []
    for wi, w in enumerate(words):
        for p in w["phones"]:
            flat.append(p); owner.append(wi)
    out = [{**w, "exp": w["phones"], "pairs": [], "before": []} for w in words]
    pairs = align(flat, rec)
    last = 0
    for k, (i, j) in enumerate(pairs):
        if i is not None:
            last = owner[i]
            out[last]["pairs"].append((flat[i], rec[j] if j is not None else None))
            continue
        nxt = next((owner[ii] for ii, _ in pairs[k + 1:] if ii is not None), None)
        if (nxt is not None and is_vowel(rec[j]) and _starts_s_cluster(words[nxt]["phones"])
                and not out[nxt]["pairs"]):
            out[nxt]["before"].append(rec[j])
        else:
            out[last]["pairs"].append((None, rec[j]))
    return out


# --- 4. Regras por som -------------------------------------------------------------------
# Ajustadas com nativos reais (lab/nativos.py, 27/10): o que nativo também faz não conta como erro.

# Formas fracas: no meio da frase, nativo diz "əd", "ən", "əv", "iz" e engole o h.
FUNCTION_WORDS = {
    "a", "an", "and", "the", "of", "to", "at", "as", "had", "has", "have", "his", "her", "him",
    "himself", "herself", "he", "them", "than", "that", "then", "there", "where", "were", "was",
    "is", "it", "its", "in", "on", "for", "from", "can", "could", "would", "should", "but", "or",
    "us", "we", "you", "your", "some", "just", "this", "these", "those", "with", "into", "upon",
}
# Duas pronúncias válidas: "with" e "without" se falam com /θ/ ou /ð/.
TH_EITHER = {"with", "within", "without", "withdraw", "withstand"}


def _before_r(exp_pairs, k) -> bool:
    """Vogal antes de r muda de cor ("where", "spare", "near"): não dá para julgar."""
    return k + 1 < len(exp_pairs) and exp_pairs[k + 1][0] in ("ɹ", "ɚ")


def findings(words: list[dict]) -> list[tuple]:
    """(índice da palavra, som, palavra, o que aconteceu, ok?) para cada alvo encontrado."""
    res = []
    for wi, w in enumerate(words):
        if w.get("oov"):
            continue
        word, pairs = w["word"].lower(), w["pairs"]
        heard_only = [h for e, h in pairs if h is not None]
        exp_pairs = [p for p in pairs if p[0] is not None]
        weak = word in FUNCTION_WORDS
        # th
        for k, (e, h) in enumerate(exp_pairs):
            if e in ("θ", "ð"):
                tag = "th-voiceless" if e == "θ" else "th-voiced"
                ok = h == e or (word in TH_EITHER and h in ("θ", "ð"))
                # "months", "fifth": th espremido entre consoantes some na fala nativa também
                squeezed = (k > 0 and not is_vowel(exp_pairs[k - 1][0])
                            and (k + 1 == len(exp_pairs) or not is_vowel(exp_pairs[k + 1][0])))
                ok = ok or (h is None and squeezed) or (weak and h is None)
                res.append((wi, tag, word, f"{e}→{h or '∅'}", ok))
        # ɪ e iː em sílaba forte; æ e ɛ. Fora: palavras fracas e vogal antes de r.
        for idx, (e, h) in enumerate(exp_pairs):
            if weak or _before_r(exp_pairs, idx):
                continue
            if e in ("ɪ", "iː") and idx in w["stressed"]:
                ok = (h == "ɪ") if e == "ɪ" else (h in ("iː", "i"))
                res.append((wi, "i-short-long", word, f"{e}→{h or '∅'}", ok))
            if e in ("æ", "ɛ"):
                res.append((wi, "ae-e", word, f"{e}→{h or '∅'}", h == e))
        # -ed: só a vogal a mais ("work-ed") conta. Engolir o -d/-t nativo também faz.
        if word.endswith("ed") and len(word) > 3:
            exp_vowel_end = len(w["exp"]) > 1 and is_vowel(w["exp"][-2])
            tail = heard_only[-3:]
            extra = not exp_vowel_end and len(tail) >= 2 and is_vowel(tail[-2]) and tail[-1] in ("t", "d")
            what = f"{''.join(w['exp'])}→{''.join(heard_only)}" + (" (vogal a mais)" if extra else "")
            res.append((wi, "ed", word, what, not extra))
        # vogal extra depois da consoante final
        if w["exp"] and not is_vowel(w["exp"][-1]) and pairs and any(e for e, _ in pairs):
            last_e = max(k for k, (e, _) in enumerate(pairs) if e is not None)
            inserted = [h for e, h in pairs[last_e + 1:] if e is None and h and is_vowel(h)]
            res.append((wi, "final-vowel", word, f"+{''.join(inserted)}" if inserted else "sem vogal extra",
                        not inserted))
        # "e" antes de s + consoante
        if _starts_s_cluster(w["exp"]):
            res.append((wi, "s-cluster", word, f"+{''.join(w['before'])}" if w["before"] else "sem 'e'",
                        not w["before"]))
        # começo de palavra: r, h, e p/t/k sem aspiração (ouvidos como b/d/g)
        first = exp_pairs[0] if exp_pairs else None
        if first:
            e, h = first
            if e == "ɹ":
                res.append((wi, "r-initial", word, f"ɹ→{h or '∅'}", h == "ɹ"))
            if e == "h" and not weak:
                res.append((wi, "h", word, f"h→{h or '∅'}", h == "h"))
            if e in ("p", "t", "k"):
                voiced = {"p": "b", "t": "d", "k": "ɡ"}[e]
                res.append((wi, "aspiration", word, f"{e}→{h or '∅'}", h != voiced))
        # fim de palavra: l, m/n/ŋ, s/z
        last = exp_pairs[-1] if exp_pairs else None
        if last:
            e, h = last
            if e == "l" and len(w["exp"]) > 1:
                res.append((wi, "dark-l", word, f"l→{h or '∅'}", h == "l"))
            if e in ("m", "n", "ŋ") and len(w["exp"]) > 2:
                res.append((wi, "final-nasal", word, f"{e}→{h or '∅'}", h in ("m", "n", "ŋ")))
            if e in ("s", "z") and word.endswith("s") and len(w["exp"]) > 2:
                res.append((wi, "final-s", word, f"{e}→{h or '∅'}", h in ("s", "z")))
        # t e d antes de i virando tch e dj
        for k in range(len(exp_pairs) - 1):
            (e1, h1), (e2, _) = exp_pairs[k], exp_pairs[k + 1]
            if e1 in ("t", "d") and e2 in ("i", "iː", "ɪ"):
                res.append((wi, "t-d-palatal", word, f"{e1}→{h1 or '∅'}", h1 not in ("tʃ", "dʒ")))
    return res


LABEL = {
    "th-voiceless": "th sem voz", "th-voiced": "th com voz", "i-short-long": "ɪ curto e iː longo",
    "ae-e": "æ e ɛ", "ed": "terminação -ed", "final-vowel": "vogal extra no fim",
    "s-cluster": "e antes de s", "r-initial": "r no começo", "h": "h aspirado",
    "aspiration": "sopro do p, t e k", "dark-l": "l no fim", "final-nasal": "m, n e ng no fim",
    "final-s": "s final", "t-d-palatal": "t e d antes de i",
}
SYMBOL = {
    "th-voiceless": "θ", "th-voiced": "ð", "i-short-long": "ɪ", "ae-e": "æ", "ed": "-ed",
    "final-vowel": "+i", "s-cluster": "sk", "r-initial": "ɹ", "h": "h", "aspiration": "tʰ",
    "dark-l": "ɫ", "final-nasal": "ŋ", "final-s": "-s", "t-d-palatal": "ti",
}
EXAMPLE = {
    "th-voiceless": "think, three", "th-voiced": "this, mother", "i-short-long": "ship × sheep",
    "ae-e": "bad × bed", "ed": "worked, played", "final-vowel": "big, dog", "s-cluster": "school, study",
    "r-initial": "red, road", "h": "hat, house", "aspiration": "tank, park", "dark-l": "people, school",
    "final-nasal": "team, long", "final-s": "needs, works", "t-d-palatal": "city, different",
}
# Taxa de "diferente" em nativos reais (214 falas, CMU ARCTIC + LibriSpeech, regras de 27/10).
NATIVE_RATE = {
    "th-voiceless": (1, 102), "dark-l": (3, 123), "ed": (5, 287), "ae-e": (10, 394),
    "i-short-long": (5, 386), "final-s": (3, 311), "aspiration": (0, 410), "th-voiced": (2, 340),
    "final-vowel": (2, 1845), "r-initial": (0, 46), "h": (0, 50), "final-nasal": (0, 209),
    "t-d-palatal": (0, 145), "s-cluster": (0, 62),
}
# Quanto cada som pesa para ser entendido (ordem de treino quando as taxas empatam).
WEIGHT = {"th-voiceless": 1.0, "i-short-long": 1.0, "ed": 1.0, "ae-e": 0.9, "final-s": 0.9,
          "dark-l": 0.8, "final-vowel": 0.7, "aspiration": 0.6, "th-voiced": 0.6}


# --- 5. Análise de uma gravação --------------------------------------------------------

def _norm(token: str) -> str:
    return re.sub(r"[^a-z0-9']", "", token.lower())


def _ref_times(ref_tokens: list[str], words: list[dict]) -> list:
    """Para cada palavra da frase esperada, o (início, fim) da palavra que o Whisper ouviu."""
    import difflib

    hyp = [w for w in words if _norm(w["w"])]
    times = [None] * len(ref_tokens)
    sm = difflib.SequenceMatcher(a=[_norm(t) for t in ref_tokens], b=[_norm(w["w"]) for w in hyp],
                                 autojunk=False)
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op == "equal" or (op == "replace" and a2 - a1 == b2 - b1):
            for k in range(a2 - a1):
                times[a1 + k] = (hyp[b1 + k]["start"], hyp[b1 + k]["end"])
        elif op == "replace" and b2 > b1:
            for k in range(a1, a2):
                times[k] = (hyp[b1]["start"], hyp[b2 - 1]["end"])
    return times


def _judge(exp_words, rec, times, offset=0.0) -> tuple[list[dict], list[dict]]:
    """Checagens por som e o raio-x de cada palavra (sons esperados e ouvidos, lado a lado)."""
    expected_len = sum(len(w["phones"]) for w in exp_words)
    if not exp_words or len(rec) < max(3, 0.5 * expected_len):
        return [], []  # gravação vazia ou cortada: não dá para julgar som nenhum
    if len(rec) > max(14, 2.2 * expected_len):
        return [], []  # bem mais som do que a frase tem: leu outra coisa, e o alinhamento inventaria erros
    aligned = by_word(exp_words, rec)

    def when(wi):
        t = times[wi] if wi < len(times) else None
        return (round(t[0] + offset, 2), round(t[1] + offset, 2)) if t else (None, None)

    checks = []
    for wi, tag, word, what, ok in findings(aligned):
        start, end = when(wi)
        checks.append({"tag": tag, "word": word, "what": what, "ok": bool(ok), "start": start, "end": end, "wi": wi})
    words_out = []
    for wi, w in enumerate(aligned):
        start, end = when(wi)
        heard = list(w["before"]) + [h for _, h in w["pairs"] if h]
        offs = [c for c in checks if c["wi"] == wi and not c["ok"]]
        words_out.append({
            "word": w["word"], "exp": w["exp"], "heard": heard, "oov": w.get("oov", False),
            # [esperado, ouvido, igual?]: igual inclui as variantes que não são erro (flap, ʌ/ə...)
            "pairs": [[e, h, bool(e and h and _cost(e, h) == 0)] for e, h in w["pairs"]],
            "before": list(w["before"]),
            "start": start, "end": end, "ok": not offs, "judged": any(c["wi"] == wi for c in checks),
            "offs": [{"tag": c["tag"], "what": c["what"]} for c in offs],
            "sounds_like": sounds_like(w["word"], heard) if offs else None,
        })
    for c in checks:
        del c["wi"]
    return checks, words_out


def _chunks(words: list[dict]) -> list[list[dict]]:
    chunks, cur = [], []
    for w in words:
        if cur and w["end"] - cur[0]["start"] > 10:
            chunks.append(cur); cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def analyze(samples, words: list[dict], reference: str | None = None) -> dict:
    """Analisa uma gravação inteira.

    Com reference (leitura, treino, "fale certo", frases), compara com a frase esperada.
    Sem reference (conversa), a referência é o que o Whisper entendeu: ele "conserta" as
    palavras pelo contexto, mas o modelo de fonemas ouve o som que saiu de verdade.
    Áudio longo é cortado em pedaços de até ~10 s nas fronteiras de palavra.
    """
    if reference:
        tokens = reference.split()
        exp_words = [_word(t) for t in tokens]
        keep = [i for i, w in enumerate(exp_words) if w["phones"]]
        times = _ref_times(tokens, words)
        rec = recognize(samples)
        checks, aligned = _judge([exp_words[i] for i in keep], rec, [times[i] for i in keep])
        return {"phones": " ".join(rec), "checks": checks, "words": aligned}
    all_phones, checks, aligned = [], [], []
    for chunk in _chunks(words):
        start = max(0.0, chunk[0]["start"] - 0.15)
        end = chunk[-1]["end"] + 0.15
        seg = samples[int(start * SR): int(end * SR)]
        if len(seg) < SR * 0.3:
            continue
        exp_words = [_word(w["w"]) for w in chunk]
        keep = [i for i, w in enumerate(exp_words) if w["phones"]]
        rec = recognize(seg)
        all_phones += rec + ["|"]
        times = [(chunk[i]["start"] - start, chunk[i]["end"] - start) for i in keep]
        c, a = _judge([exp_words[i] for i in keep], rec, times, offset=start)
        checks += c
        aligned += a
    return {"phones": " ".join(all_phones), "checks": checks, "words": aligned}


def realign(rec: dict) -> list[dict]:
    """O raio-x de uma gravação já analisada, refeito a partir dos sons guardados (sem o modelo)."""
    phones = (rec.get("phones") or "").split()
    if not phones:
        return []
    if rec.get("reference"):
        tokens = rec["reference"].split()
        exp_words = [_word(t) for t in tokens]
        keep = [i for i, w in enumerate(exp_words) if w["phones"]]
        times = _ref_times(tokens, rec["words"] or [])
        return _judge([exp_words[i] for i in keep], phones, [times[i] for i in keep])[1]
    # Conversa: os pedaços foram separados por "|", na mesma ordem de _chunks.
    pieces, cur = [], []
    for p in phones:
        if p == "|":
            pieces.append(cur); cur = []
        else:
            cur.append(p)
    out = []
    usable = [c for c in _chunks(rec["words"] or []) if (c[-1]["end"] - c[0]["start"] + 0.3) * SR >= SR * 0.3]
    for chunk, seg_phones in zip(usable, pieces):
        start = max(0.0, chunk[0]["start"] - 0.15)
        exp_words = [_word(w["w"]) for w in chunk]
        keep = [i for i, w in enumerate(exp_words) if w["phones"]]
        times = [(chunk[i]["start"] - start, chunk[i]["end"] - start) for i in keep]
        out += _judge([exp_words[i] for i in keep], seg_phones, times, offset=start)[1]
    return out


# --- "Pra um nativo, soou como..." ----------------------------------------------------------
# Para quem ouve, um som trocado vira outra palavra: think dito com s é "sink".
# Índice reverso do dicionário CMU (sons -> palavras), escolhendo a palavra mais comum.

_LOOK = {"iː": "i", "uː": "u", "ɑː": "ɑ", "ɔː": "ɔ", "ɜː": "ɚ", "ɝ": "ɚ", "ʌ": "ə", "ɐ": "ə", "ᵻ": "ə",
         "ɾ": "t", "o": "oʊ", "əʊ": "oʊ", "e": "eɪ", "r": "ɹ"}
_reverse = None
_reverse_lock = threading.Lock()


def _look_key(phones: list[str]) -> tuple:
    return tuple(_LOOK.get(p, p) for p in phones)


def _reverse_index() -> dict:
    global _reverse, _cmu
    with _reverse_lock:
        if _reverse is None:
            if _cmu is None:
                import cmudict

                _cmu = cmudict.dict()
            idx = {}
            for word, prons in _cmu.items():
                if not word.isalpha():
                    continue
                for arpa in prons[:2]:
                    idx.setdefault(_look_key([_arpa(s) for s in arpa]), []).append(word)
            _reverse = idx
    return _reverse


def sounds_like(word: str, heard: list[str]) -> str | None:
    """A palavra comum do inglês que tem exatamente os sons que você fez, se existir."""
    if not heard:
        return None
    try:
        from wordfreq import zipf_frequency
    except ImportError:
        return None
    candidates = [w for w in _reverse_index().get(_look_key(heard), []) if w != word.lower()]
    scored = sorted(((zipf_frequency(w, "en"), w) for w in candidates), reverse=True)
    if scored and scored[0][0] >= 3.0:  # palavra comum de verdade, não um nome obscuro do dicionário
        return scored[0][1]
    return None


# --- 6. Fila em segundo plano -------------------------------------------------------------

_queue: "queue.Queue[int]" = queue.Queue()
_worker = None


def _process(rid: int):
    from . import db
    from .stt import _decode

    rec = db.get_recording(rid)
    if not rec or rec["pron_status"] == "done":
        return
    try:
        path = config.DATA / rec["path"]
        samples = _decode(path.read_bytes())
        words = rec["words"] or []
        res = analyze(samples, words, rec["reference"])
        db.save_pron(rid, res["phones"], res["checks"], rec["kind"] or "conversa")
    except Exception:
        db.set_pron_status(rid, "error")
        print(f"[pron] erro na gravação {rid}:\n{traceback.format_exc(limit=2)}")


def _loop():
    load()
    while True:
        rid = _queue.get()
        if _model is not None:
            _process(rid)
        _queue.task_done()


def start_worker():
    """Liga a fila e coloca nela as gravações que ainda não foram analisadas."""
    global _worker
    if not available():
        return
    from . import db

    if _worker is None:
        _worker = threading.Thread(target=_loop, daemon=True, name="pron-worker")
        _worker.start()
    for rid in db.recordings_pending_pron():
        _queue.put(rid)


def enqueue(rid: int):
    if _worker is not None:
        _queue.put(rid)


def pending() -> int:
    return _queue.qsize()


def analyze_now(rid: int) -> dict | None:
    """Análise na hora (leitura e treino): você espera o resultado na tela."""
    from . import db

    if not available() or load() is None:
        return None
    _process(rid)
    return db.get_recording(rid)


def summarize_checks(checks: list[dict]) -> dict:
    by = {}
    for c in checks:
        t = by.setdefault(c["tag"], {"tag": c["tag"], "label": LABEL.get(c["tag"], c["tag"]), "n": 0, "off": 0})
        t["n"] += 1
        t["off"] += int(not c["ok"])
    return by


