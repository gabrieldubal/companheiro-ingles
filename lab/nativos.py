"""Validação do detector com falantes nativos reais: quanto ele "acusa" quem não tem sotaque?

Fontes (baixadas para data/nativos/):
  - CMU ARCTIC: 4 falantes americanos (bdl, rms homens; slt, clb mulheres) lendo frases
    foneticamente balanceadas. Uso as 40 frases mais ricas nos sons-alvo, as mesmas para os 4.
  - LibriSpeech (amostra de 73 falas de audiolivro, vários leitores).

Para cada som, compara a taxa de "diferente" nos nativos (o ruído do detector) com a sua
taxa na última rodada de leitura, com intervalo de confiança de Wilson (95%).

Uso (na pasta companheiro-ingles; -I não deixa o Python carregar nada das pastas de dados):
  .venv\\Scripts\\python.exe -I lab\\nativos.py
"""
import io
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # só a raiz do projeto, explicitamente

from app import config  # noqa: E402
from app.stt import _decode  # noqa: E402
from lab import fonemas  # noqa: E402

NATIVOS = config.DATA / "nativos"
CACHE = config.DATA / "fonemas" / "cache_fonemas.json"
SPEAKERS = ["bdl", "rms", "slt", "clb"]
N_PROMPTS = 40

# Sons raros pesam mais na escolha das frases do ARCTIC.
_WEIGHT = {"th-voiceless": 3, "ed": 3, "dark-l": 2, "ae-e": 1, "i-short-long": 1, "aspiration": 1,
           "th-voiced": 1, "final-s": 1}


def _expected_or_none(text):
    words = fonemas.expected(text)
    # Palavra fora do dicionário (nome próprio etc.): a frase fica de fora da validação.
    return None if any(w["oov"] for w in words) else words


def _target_score(text) -> int:
    words = _expected_or_none(text)
    if not words:
        return -1
    # Conta os alvos fingindo que tudo foi ouvido como esperado.
    fake = [{**w, "exp": w["phones"], "pairs": [(p, p) for p in w["phones"]], "before": []} for w in words]
    return sum(_WEIGHT.get(tag, 0) for _, tag, *_ in fonemas.findings(fake))


def arctic_items() -> list[dict]:
    prompts = {}
    txt = next((NATIVOS / "arctic" / "bdl").rglob("txt.done.data"))
    for line in txt.read_text(encoding="utf-8").splitlines():
        m = re.match(r'\(\s*(\S+)\s+"(.*)"\s*\)', line)
        if m:
            prompts[m.group(1)] = m.group(2)
    # A amostra fica congelada depois da primeira vez: ajustar regra não pode mudar quem foi medido.
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    frozen = sorted({k.split("/")[2] for k in cache if k.startswith("arctic/")})
    ranked = frozen or sorted(prompts, key=lambda k: -_target_score(prompts[k]))[:N_PROMPTS]
    items = []
    for spk in SPEAKERS:
        wav_dir = next((NATIVOS / "arctic" / spk).rglob("wav"))
        for pid in ranked:
            items.append({"id": f"arctic/{spk}/{pid}", "corpus": "arctic", "speaker": spk,
                          "text": prompts[pid], "path": str(wav_dir / f"{pid}.wav")})
    return items


def libri_items() -> list[dict]:
    import pyarrow.parquet as pq

    table = pq.read_table(next((NATIVOS / "librispeech").rglob("*.parquet"))).to_pylist()
    items = []
    for row in table:
        if _expected_or_none(row["text"]) is None:
            continue
        items.append({"id": f"libri/{row['id']}", "corpus": "librispeech", "speaker": str(row["speaker_id"]),
                      "text": row["text"].lower(), "audio": row["audio"]["bytes"]})
    return items


def user_items() -> list[dict]:
    text_by_id = {sid: text for sid, text, *_ in fonemas.SENTENCES}
    return [{"id": f"voce/{sid}", "corpus": "voce", "speaker": "voce", "text": text_by_id[sid], "path": str(p)}
            for sid, p in fonemas._latest_run_recordings()]


def recognize_all(items: list[dict]) -> dict:
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    todo = [it for it in items if it["id"] not in cache]
    t0 = time.time()
    for k, it in enumerate(todo, 1):
        audio = it["audio"] if "audio" in it else Path(it["path"]).read_bytes()
        cache[it["id"]] = fonemas.recognize(_decode(audio))
        if k % 20 == 0 or k == len(todo):
            print(f"  {k}/{len(todo)} reconhecidas ({time.time() - t0:.0f}s)", file=sys.stderr, flush=True)
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


def tally(items: list[dict], phones: dict):
    totals, examples = defaultdict(Counter), defaultdict(Counter)
    for it in items:
        words = fonemas.by_word(fonemas.expected(it["text"]), phones[it["id"]])
        for _, tag, word, what, ok in fonemas.findings(words):
            totals[tag]["n"] += 1
            if not ok:
                totals[tag]["off"] += 1
                examples[tag][f"{word} {what.split(' (')[0]}"] += 1
    return totals, examples


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def verdict(user: Counter, native: Counter) -> str:
    un, uk, nn, nk = user["n"], user["off"], native["n"], native["off"]
    if un < 5:
        return "poucos dados seus"
    u_lo, _ = wilson(uk, un)
    _, n_hi = wilson(nk, nn)
    if u_lo > n_hi:
        return "SINAL"
    if uk / un <= n_hi:
        return "dentro do ruído"
    return "provável, falta dado"


def main():
    native = arctic_items() + libri_items()
    mine = user_items()
    print(f"nativos: {len(native)} falas ({sum(i['corpus'] == 'arctic' for i in native)} ARCTIC, "
          f"{sum(i['corpus'] == 'librispeech' for i in native)} LibriSpeech) · você: {len(mine)} frases",
          file=sys.stderr)
    phones = recognize_all(native + mine)
    n_tot, n_ex = tally(native, phones)
    u_tot, _ = tally(mine, phones)
    per_corpus = {c: tally([i for i in native if i["corpus"] == c], phones)[0] for c in ("arctic", "librispeech")}

    rows = []
    for tag in sorted(set(n_tot) | set(u_tot), key=lambda t: -(u_tot[t]["off"] / max(u_tot[t]["n"], 1))):
        nat, usr = n_tot[tag], u_tot[tag]
        rows.append({
            "tag": tag, "label": fonemas.LABEL.get(tag, tag),
            "native": [nat["off"], nat["n"], *wilson(nat["off"], nat["n"])],
            "user": [usr["off"], usr["n"], *wilson(usr["off"], usr["n"])],
            "by_corpus": {c: [t[tag]["off"], t[tag]["n"]] for c, t in per_corpus.items()},
            "verdict": verdict(usr, nat),
            "native_examples": n_ex[tag].most_common(8),
        })

    print(f"\n{'som':34s} {'nativos':>18s}   {'você':>18s}   veredito")
    for r in rows:
        nk, nn, nlo, nhi = r["native"]
        uk, un, ulo, uhi = r["user"]
        print(f"{r['label']:34s} {nk:>3}/{nn:<4} {100 * nk / max(nn, 1):5.1f}%   "
              f"{uk:>3}/{un:<3} {100 * uk / max(un, 1):5.1f}% [{100 * ulo:4.0f}-{100 * uhi:3.0f}]   {r['verdict']}")
    print("\nOnde o detector acusa nativos (candidatos a ajuste de regra):")
    for r in rows:
        if r["native_examples"]:
            ex = ", ".join(f"{w} ×{c}" for w, c in r["native_examples"][:6])
            print(f"  {r['label']}: {ex}")
    out = config.DATA / "fonemas" / "validacao.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n(salvo em {out})")


if __name__ == "__main__":
    main()
