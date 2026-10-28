"""Relatório do detector de pronúncia na última rodada de leitura (ou na voz sintética).

O detector em si mora em app/pron.py (é o mesmo que o app usa). Este script só roda ele
nas gravações e imprime frase por frase.

Uso (na pasta companheiro-ingles):
  .venv\\Scripts\\python.exe -m lab.fonemas              suas gravações (última rodada)
  .venv\\Scripts\\python.exe -m lab.fonemas --controle   as mesmas frases na voz sintética do Windows
"""
import argparse
import json
import sqlite3
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

from app import config
from app.pron import LABEL, by_word, expected, findings, recognize
from app.reading import SENTENCES
from app.stt import _decode

OUT = config.DATA / "fonemas"


def _latest_run_recordings() -> list[tuple[str, Path]]:
    con = sqlite3.connect(f"file:{config.DATA / 'companheiro.db'}?mode=ro", uri=True)
    run = con.execute("SELECT MAX(run_id) FROM recordings WHERE kind='leitura'").fetchone()[0]
    rows = con.execute(
        "SELECT sentence_id, path FROM recordings WHERE kind='leitura' AND run_id=? ORDER BY id", (run,)
    ).fetchall()
    latest = {sid: config.DATA / path for sid, path in rows}  # vale a última tentativa de cada frase
    return [(sid, latest[sid]) for sid, *_ in SENTENCES if sid in latest]


def _control_recordings() -> list[tuple[str, Path]]:
    """As 24 frases na voz sintética en-US do Windows, como controle do modelo."""
    folder = Path(tempfile.gettempdir()) / "companheiro-controle"
    folder.mkdir(exist_ok=True)
    lines = []
    for sid, text, *_ in SENTENCES:
        wav = folder / f"{sid}.wav"
        if not wav.exists():
            safe = text.replace("'", "''")
            lines.append(f"$s.SetOutputToWaveFile('{wav}'); $s.Speak('{safe}');")
    if lines:
        script = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'en-US' } | Select-Object -First 1; "
                  "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }; $s.Rate = -1; " + " ".join(lines) + " $s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
    return [(sid, folder / f"{sid}.wav") for sid, *_ in SENTENCES]


def run(control: bool) -> dict:
    items = _control_recordings() if control else _latest_run_recordings()
    text_by_id = {sid: text for sid, text, *_ in SENTENCES}
    report, totals, cpu = [], defaultdict(Counter), 0.0
    for sid, path in items:
        samples = _decode(path.read_bytes())
        t0 = time.time()
        rec = recognize(samples)
        cpu += time.time() - t0
        exp = expected(text_by_id[sid])
        found = findings(by_word(exp, rec))
        for _, tag, word, what, ok in found:
            totals[tag]["ok" if ok else "off"] += 1
            if not ok:
                totals[tag][what.split(" (")[0] if tag != "ed" else "vogal a mais"] += 1
        report.append({
            "id": sid, "text": text_by_id[sid],
            "expected": " ".join("".join(w["phones"]) for w in exp),
            "heard": " ".join(rec),
            "off": [(LABEL.get(t, t), w, what) for _, t, w, what, ok in found if not ok],
        })
    return {"control": control, "items": report, "cpu_seconds": round(cpu, 1),
            "totals": {t: dict(c) for t, c in totals.items()}}


def print_report(res: dict):
    who = "VOZ SINTÉTICA (controle)" if res["control"] else "SUAS GRAVAÇÕES"
    print(f"\n===== {who}: {len(res['items'])} frases, {res['cpu_seconds']}s de CPU =====")
    for it in res["items"]:
        print(f"\n[{it['id']}] {it['text']}\n  esperado: {it['expected']}\n  ouvido:   {it['heard']}")
        for label, word, what in it["off"]:
            print(f"    - {label}: {word} {what}")
    print("\n----- por som -----")
    rows = sorted(res["totals"].items(),
                  key=lambda kv: -kv[1].get("off", 0) / max(kv[1].get("ok", 0) + kv[1].get("off", 0), 1))
    for tag, c in rows:
        n = c.get("ok", 0) + c.get("off", 0)
        detail = ", ".join(f"{k} x{v}" for k, v in c.items() if k not in ("ok", "off"))
        print(f"  {LABEL.get(tag, tag):28s} {c.get('off', 0):>2}/{n:<3} diferente  {detail}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--controle", action="store_true", help="usar a voz sintética do Windows")
    args = parser.parse_args()
    res = run(args.controle)
    OUT.mkdir(exist_ok=True)
    out = OUT / ("controle.json" if args.controle else "rodada.json")
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print_report(res)
    print(f"\n(salvo em {out})")


if __name__ == "__main__":
    main()
