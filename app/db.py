"""SQLite: sessões, falas e o caderno de erros com revisão espaçada."""
import json
import re
import sqlite3
import threading
from datetime import date, datetime, timedelta

from . import config

_conn = sqlite3.connect(config.DATA / "companheiro.db", check_same_thread=False)
_conn.row_factory = sqlite3.Row
_lock = threading.Lock()

BACKUPS_KEPT = 14


def _auto_backup():
    """Uma cópia do banco por dia, ao ligar, antes das migrações. Ficam as 14 mais novas."""
    folder = config.DATA / "backups" / "auto"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"companheiro-{date.today().isoformat()}.db"
        if not target.exists():
            dst = sqlite3.connect(target)
            with dst:
                _conn.backup(dst)
            dst.close()
        for old in sorted(folder.glob("companheiro-*.db"))[:-BACKUPS_KEPT]:
            old.unlink()
    except (OSError, sqlite3.Error) as e:  # sem backup não é motivo para o app não ligar
        print(f"[db] backup automático falhou: {e}")


_auto_backup()

_conn.executescript("""
CREATE TABLE IF NOT EXISTS sessions(
    id INTEGER PRIMARY KEY, scenario TEXT, level REAL, recurring TEXT,
    started_at TEXT, ended_at TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS turns(
    id INTEGER PRIMARY KEY, session_id INTEGER, role TEXT, text TEXT,
    data TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS mistakes(
    id INTEGER PRIMARY KEY, session_id INTEGER, pattern TEXT, original TEXT,
    better TEXT, explanation_pt TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS patterns(
    pattern TEXT PRIMARY KEY, count INTEGER DEFAULT 0, good_uses INTEGER DEFAULT 0,
    box INTEGER DEFAULT 1, last_seen TEXT, next_review TEXT);
CREATE TABLE IF NOT EXISTS words(
    id INTEGER PRIMARY KEY, session_id INTEGER, word TEXT, meaning_pt TEXT,
    example TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS recordings(
    id INTEGER PRIMARY KEY, session_id INTEGER, path TEXT, transcript TEXT,
    words TEXT, audio_seconds REAL, sent_text TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS reading_runs(
    id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT);
""")

# Colunas novas (leitura em voz alta e pronúncia), para bancos criados antes delas.
_have = {r[1] for r in _conn.execute("PRAGMA table_info(recordings)")}
for _col, _type in [("kind", "TEXT"), ("reference", "TEXT"), ("sentence_id", "TEXT"),
                    ("run_id", "INTEGER"), ("compare", "TEXT"), ("pron_status", "TEXT"),
                    ("phones", "TEXT")]:
    if _col not in _have:
        _conn.execute(f"ALTER TABLE recordings ADD COLUMN {_col} {_type}")

# Versão 2: pronúncia som a som, prática, atividade e ajustes.
_conn.executescript("""
CREATE TABLE IF NOT EXISTS pron_checks(
    id INTEGER PRIMARY KEY, recording_id INTEGER, source TEXT, tag TEXT, word TEXT,
    what TEXT, ok INTEGER, start REAL, end REAL, created_at TEXT);
CREATE INDEX IF NOT EXISTS pron_checks_tag ON pron_checks(tag, created_at);
CREATE TABLE IF NOT EXISTS practice(
    id INTEGER PRIMARY KEY, kind TEXT, pattern TEXT, mistake_id INTEGER, target TEXT,
    transcript TEXT, ok INTEGER, recording_id INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS activity(
    id INTEGER PRIMARY KEY, kind TEXT, ref TEXT, seconds INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS drill_items(
    id INTEGER PRIMARY KEY, tag TEXT, text TEXT, targets TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS word_practice(
    word TEXT, tag TEXT, step INTEGER DEFAULT 0, streak INTEGER DEFAULT 0, fails INTEGER DEFAULT 0,
    mastered_at TEXT, updated_at TEXT, PRIMARY KEY(word, tag));
CREATE TABLE IF NOT EXISTS cards(
    id INTEGER PRIMARY KEY, kind TEXT, front TEXT, hint TEXT, back TEXT, note TEXT, speak TEXT,
    source TEXT, source_id INTEGER, created_at TEXT,
    state TEXT DEFAULT 'new', due TEXT, stability REAL, difficulty REAL,
    reps INTEGER DEFAULT 0, lapses INTEGER DEFAULT 0, last_review TEXT,
    suspended INTEGER DEFAULT 0, deleted INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS cards_due ON cards(state, due);
CREATE TABLE IF NOT EXISTS card_reviews(
    id INTEGER PRIMARY KEY, card_id INTEGER, rating INTEGER, state TEXT, days REAL,
    prev TEXT, reviewed_at TEXT);
CREATE TABLE IF NOT EXISTS ask_messages(
    id INTEGER PRIMARY KEY, thread INTEGER, role TEXT, text TEXT, actions TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS listen_trials(
    id INTEGER PRIMARY KEY, tag TEXT, word TEXT, other TEXT, chosen TEXT, ok INTEGER, voice TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS passages(
    id INTEGER PRIMARY KEY, title TEXT, sentences TEXT, focus TEXT, source TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS free_prompts(
    id INTEGER PRIMARY KEY, kind TEXT, ref TEXT, question_en TEXT, question_pt TEXT, target TEXT,
    created_at TEXT, answered_at TEXT);
CREATE TABLE IF NOT EXISTS lessons(
    key TEXT PRIMARY KEY, content TEXT, score INTEGER, total INTEGER, done_at TEXT, created_at TEXT);
""")
# O "soou como" da escada fica guardado: a lista de degraus de uma palavra não pode mudar no meio.
if "heard_as" not in {r[1] for r in _conn.execute("PRAGMA table_info(word_practice)")}:
    _conn.execute("ALTER TABLE word_practice ADD COLUMN heard_as TEXT")
# O que você queria dizer com cada erro: sem isso, "it's lower" sozinho não diz qual é a versão certa.
for _table, _col in [("mistakes", "meaning_pt"), ("cards", "meaning")]:
    if _col not in {r[1] for r in _conn.execute(f"PRAGMA table_info({_table})")}:
        _conn.execute(f"ALTER TABLE {_table} ADD COLUMN {_col} TEXT")
_conn.commit()


def _backfill_activity():
    """Uma vez só: o tempo das conversas e leituras feitas antes de existir a tabela de atividade."""
    if _conn.execute("SELECT COUNT(*) FROM activity").fetchone()[0]:
        return
    rows = []
    for sid, scenario, started in _conn.execute("SELECT id, scenario, started_at FROM sessions"):
        last = _conn.execute("SELECT MAX(created_at) FROM turns WHERE session_id=?", (sid,)).fetchone()[0]
        if last:
            secs = (datetime.fromisoformat(last) - datetime.fromisoformat(started)).total_seconds()
            rows.append(("conversa", scenario, int(min(secs, 7200)), last))  # como as outras linhas: a hora do fim
    for rid, started, finished in _conn.execute("SELECT id, started_at, finished_at FROM reading_runs"):
        if finished:
            secs = (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds()
            rows.append(("leitura", str(rid), int(min(secs, 7200)), finished))
    rows = [r for r in rows if r[2] >= 30]
    if rows:
        _conn.executemany("INSERT INTO activity(kind, ref, seconds, created_at) VALUES (?,?,?,?)", rows)
        _conn.commit()


_backfill_activity()


def _fix_backfilled_ends():
    """Uma vez só: as linhas do primeiro preenchimento guardavam a hora do começo, e as outras, a do
    fim. Para agrupar a prática em sessões, todas precisam guardar o fim."""
    if _conn.execute("SELECT 1 FROM settings WHERE key='activity_ends_fixed'").fetchone():
        return
    _conn.execute(
        "UPDATE activity SET created_at = strftime('%Y-%m-%dT%H:%M:%S', created_at, '+' || seconds || ' seconds')"
        " WHERE (kind='conversa' AND created_at IN (SELECT started_at FROM sessions))"
        " OR (kind='leitura' AND created_at IN (SELECT started_at FROM reading_runs))")
    _conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('activity_ends_fixed', '1')")
    _conn.commit()


_fix_backfilled_ends()

# Caixas de Leitner: errou, volta pra caixa 1 (revisar já); acertou, sobe e espera mais.
REVIEW_DAYS = {1: 0, 2: 2, 3: 5, 4: 12, 5: 30}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _q(sql, args=(), one=False):
    with _lock:
        cur = _conn.execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
        _conn.commit()
    return (rows[0] if rows else None) if one else rows


def _exec(sql, args=()) -> int:
    with _lock:
        cur = _conn.execute(sql, args)
        _conn.commit()
        return cur.lastrowid


def create_session(scenario: str, level: float, recurring: list) -> int:
    return _exec(
        "INSERT INTO sessions(scenario, level, recurring, started_at) VALUES (?,?,?,?)",
        (scenario, level, json.dumps(recurring, ensure_ascii=False), _now()),
    )


def get_session(sid: int):
    s = _q("SELECT * FROM sessions WHERE id=?", (sid,), one=True)
    if s:
        s["recurring"] = json.loads(s["recurring"] or "[]")
        s["summary"] = json.loads(s["summary"]) if s["summary"] else None
    return s


def delete_session(sid: int):
    _exec("DELETE FROM sessions WHERE id=?", (sid,))


def add_turn(sid: int, role: str, text: str, data: dict | None):
    _exec(
        "INSERT INTO turns(session_id, role, text, data, created_at) VALUES (?,?,?,?,?)",
        (sid, role, text, json.dumps(data, ensure_ascii=False) if data else None, _now()),
    )


def get_turns(sid: int) -> list:
    rows = _q("SELECT role, text, data FROM turns WHERE session_id=? ORDER BY id", (sid,))
    for r in rows:
        r["data"] = json.loads(r["data"]) if r["data"] else None
    return rows


def add_recording(sid, path: str, transcript: str, words: list, audio_seconds: float,
                  kind: str = "conversa", reference: str | None = None, sentence_id: str | None = None,
                  run_id: int | None = None, compare: dict | None = None) -> int:
    return _exec(
        "INSERT INTO recordings(session_id, path, transcript, words, audio_seconds, created_at,"
        " kind, reference, sentence_id, run_id, compare) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (sid, path, transcript, json.dumps(words, ensure_ascii=False), audio_seconds, _now(),
         kind, reference, sentence_id, run_id, json.dumps(compare, ensure_ascii=False) if compare else None),
    )


def create_run() -> int:
    return _exec("INSERT INTO reading_runs(started_at) VALUES (?)", (_now(),))


def finish_run(rid: int) -> bool:
    """Fecha a rodada uma vez só (dois cliques em "Ver o retrato" não contam o tempo duas vezes)."""
    with _lock:
        cur = _conn.execute("UPDATE reading_runs SET finished_at=? WHERE id=? AND finished_at IS NULL", (_now(), rid))
        _conn.commit()
        return cur.rowcount > 0


def run_recordings(rid: int) -> list:
    rows = _q(
        "SELECT id, sentence_id, transcript, compare FROM recordings WHERE run_id=? ORDER BY id", (rid,)
    )
    for r in rows:
        r["compare"] = json.loads(r["compare"]) if r["compare"] else {"tokens": [], "diffs": 0, "unsure": 0}
    return rows


def run_checks(rid: int) -> dict:
    """Checagens de pronúncia de uma rodada, por gravação."""
    rows = _q("SELECT c.recording_id, c.tag, c.word, c.what, c.ok, c.start, c.end FROM pron_checks c"
              " JOIN recordings r ON r.id=c.recording_id WHERE r.run_id=? ORDER BY c.id", (rid,))
    out = {}
    for r in rows:
        out.setdefault(r["recording_id"], []).append(r)
    return out


def run_seconds(rid: int) -> int:
    r = _q("SELECT started_at, finished_at FROM reading_runs WHERE id=?", (rid,), one=True)
    if not r or not r["finished_at"]:
        return 0
    return int((datetime.fromisoformat(r["finished_at"]) - datetime.fromisoformat(r["started_at"])).total_seconds())


def reading_runs(limit: int = 20) -> list:
    return _q(
        "SELECT r.id, r.started_at, r.finished_at,"
        " (SELECT COUNT(DISTINCT sentence_id) FROM recordings g WHERE g.run_id=r.id) AS recorded"
        " FROM reading_runs r ORDER BY r.id DESC LIMIT ?",
        (limit,),
    )


def link_recording(rid: int, sid: int, sent_text: str):
    """Guarda o texto que foi enviado de fato (você pode ter editado a transcrição)."""
    _exec("UPDATE recordings SET session_id=?, sent_text=? WHERE id=?", (sid, sent_text, rid))


def _add_mistake(sid, pattern, original, better, explanation_pt, meaning_pt=""):
    _exec(
        "INSERT INTO mistakes(session_id, pattern, original, better, explanation_pt, meaning_pt, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (sid, pattern, original, better, explanation_pt, meaning_pt or "", _now()),
    )


def record_feedback(sid: int, corrections: list, pattern_counts: list, good_uses: list, new_words: list):
    """Cartões viram exemplos no caderno. A contagem por padrão inclui os erros que não
    viraram cartão, para o caderno saber o que mais se repete de verdade."""
    carded = {c["pattern"] for c in corrections}
    for c in corrections:
        _add_mistake(sid, c["pattern"], c["original"], c["better"], c["explanation_pt"], c.get("meaning_pt", ""))
    for pc in pattern_counts:
        if pc["pattern"] not in carded and pc.get("original") and pc.get("better"):
            _add_mistake(sid, pc["pattern"], pc["original"], pc["better"], "", pc.get("meaning_pt", ""))
        _exec(
            "INSERT INTO patterns(pattern, count, box, last_seen, next_review) VALUES (?,?,1,?,?)"
            " ON CONFLICT(pattern) DO UPDATE SET count=count+excluded.count, box=1,"
            " last_seen=excluded.last_seen, next_review=excluded.next_review",
            (pc["pattern"], pc["count"], _now(), _now()),
        )
    corrected = {pc["pattern"] for pc in pattern_counts}
    for pattern in good_uses:
        if pattern not in corrected:
            _promote(pattern)
    for w in new_words:
        _exec(
            "INSERT INTO words(session_id, word, meaning_pt, example, created_at) VALUES (?,?,?,?,?)",
            (sid, w["word"], w["meaning_pt"], w["example"], _now()),
        )


def session_mistakes(sid: int) -> list:
    return _q(
        "SELECT pattern, original, better, explanation_pt FROM mistakes WHERE session_id=? ORDER BY id",
        (sid,),
    )


def end_session(sid: int, summary: dict):
    _exec(
        "UPDATE sessions SET ended_at=?, summary=? WHERE id=?",
        (_now(), json.dumps(summary, ensure_ascii=False), sid),
    )


def due_patterns(limit: int = 3) -> list:
    """Padrões que estão na hora de revisar, com o exemplo mais recente de cada."""
    rows = _q(
        "SELECT pattern, count FROM patterns WHERE next_review <= ?"
        " ORDER BY count DESC, last_seen DESC LIMIT ?",
        (_now(), limit),
    )
    for r in rows:
        ex = _q(
            "SELECT original, better FROM mistakes WHERE pattern=? ORDER BY id DESC LIMIT 1",
            (r["pattern"],), one=True,
        ) or {}
        r.update(ex)
    return rows


def notebook() -> dict:
    patterns = _q("SELECT * FROM patterns ORDER BY next_review ASC, count DESC")
    now = _now()
    for p in patterns:
        p["due"] = p["next_review"] <= now
        p["examples"] = _q(
            "SELECT original, better, explanation_pt FROM mistakes WHERE pattern=?"
            " ORDER BY id DESC LIMIT 3",
            (p["pattern"],),
        )
    words = _q("SELECT word, meaning_pt, example, created_at FROM words ORDER BY id DESC LIMIT 100")
    return {"patterns": patterns, "words": words}


def history(limit: int = 30) -> list:
    rows = _q(
        "SELECT s.id, s.scenario, s.level, s.started_at, s.ended_at, s.summary,"
        " (SELECT COUNT(*) FROM turns t WHERE t.session_id=s.id AND t.role='student') AS student_turns"
        " FROM sessions s ORDER BY s.id DESC LIMIT ?",
        (limit,),
    )
    for r in rows:
        r["summary"] = json.loads(r["summary"]) if r["summary"] else None
    return rows


# --- Gravações e pronúncia ---------------------------------------------------------

def get_recording(rid: int):
    r = _q("SELECT * FROM recordings WHERE id=?", (rid,), one=True)
    if r:
        r["words"] = json.loads(r["words"]) if r["words"] else []
        r["compare"] = json.loads(r["compare"]) if r["compare"] else None
    return r


def recordings_pending_pron() -> list[int]:
    rows = _q("SELECT id FROM recordings WHERE path IS NOT NULL AND (pron_status IS NULL OR pron_status='pending')"
              " ORDER BY id")
    return [r["id"] for r in rows]


def set_pron_status(rid: int, status: str):
    _exec("UPDATE recordings SET pron_status=? WHERE id=?", (status, rid))


def save_pron(rid: int, phones: str, checks: list, source: str):
    with _lock:
        _conn.execute("DELETE FROM pron_checks WHERE recording_id=?", (rid,))
        created = _conn.execute("SELECT created_at FROM recordings WHERE id=?", (rid,)).fetchone()[0]
        _conn.executemany(
            "INSERT INTO pron_checks(recording_id, source, tag, word, what, ok, start, end, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            [(rid, source, c["tag"], c["word"], c["what"], int(c["ok"]), c["start"], c["end"], created)
             for c in checks],
        )
        _conn.execute("UPDATE recordings SET pron_status='done', phones=? WHERE id=?", (phones, rid))
        _conn.commit()


def recording_checks(rid: int) -> list:
    return _q("SELECT tag, word, what, ok, start, end FROM pron_checks WHERE recording_id=? ORDER BY id", (rid,))


def pron_checks(since: str | None = None, tag: str | None = None, limit: int | None = None,
                only_off: bool = False) -> list:
    sql = ("SELECT c.*, r.kind, r.session_id, r.reference FROM pron_checks c"
           " JOIN recordings r ON r.id=c.recording_id WHERE 1=1")
    args = []
    if since:
        sql += " AND c.created_at >= ?"; args.append(since)
    if tag:
        sql += " AND c.tag=?"; args.append(tag)
    if only_off:
        sql += " AND c.ok=0"
    sql += " ORDER BY c.created_at DESC, c.id DESC"
    if limit:
        sql += " LIMIT ?"; args.append(limit)
    return _q(sql, tuple(args))


def session_recordings(sid: int) -> list:
    return _q("SELECT id, pron_status FROM recordings WHERE session_id=? AND kind='conversa'", (sid,))


# --- Prática ("fale certo" e treinos) ------------------------------------------------

def practice_items(limit: int = 4) -> list:
    """Erros de gramática na hora de revisar, com o exemplo mais claro de cada padrão."""
    due = _q("SELECT pattern, count, box FROM patterns WHERE next_review <= ? ORDER BY count DESC, last_seen DESC",
             (_now(),))
    items = []
    for p in due:
        ex = _q(
            "SELECT id, session_id, original, better, explanation_pt, meaning_pt FROM mistakes"
            " WHERE pattern=? AND better != ''"
            " ORDER BY (explanation_pt != '') DESC, length(better) ASC, id DESC LIMIT 1",
            (p["pattern"],), one=True,
        )
        if ex and len(ex["better"].split()) <= 25:
            ctx = mistake_context(ex["session_id"], ex["original"])
            items.append({**p, **ex, "mistake_id": ex["id"], "context": ctx})
        if len(items) >= limit:
            break
    return items


def notebook_examples(pattern: str, limit: int = 4) -> list:
    return _q("SELECT original, better, explanation_pt, meaning_pt FROM mistakes WHERE pattern=? AND better != ''"
              " ORDER BY id DESC LIMIT ?", (pattern, limit))


def get_mistake(mid: int):
    return _q("SELECT * FROM mistakes WHERE id=?", (mid,), one=True)


def add_practice(kind: str, pattern: str | None, mistake_id: int | None, target: str,
                 transcript: str, ok: bool, recording_id: int | None) -> int:
    return _exec(
        "INSERT INTO practice(kind, pattern, mistake_id, target, transcript, ok, recording_id, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (kind, pattern, mistake_id, target, transcript, int(ok), recording_id, _now()),
    )


def _promote(pattern: str):
    """Um acerto conta para subir de caixa só quando o padrão estava na hora de revisar.
    Sem isso, falar a mesma frase certa três vezes seguidas pulava da caixa 2 para a 5."""
    p = _q("SELECT box, next_review FROM patterns WHERE pattern=?", (pattern,), one=True)
    if not p:
        return
    if p["next_review"] and p["next_review"] > _now():
        _exec("UPDATE patterns SET good_uses=good_uses+1 WHERE pattern=?", (pattern,))
        return
    box = min(p["box"] + 1, 5)
    due = (datetime.now() + timedelta(days=REVIEW_DAYS[box])).isoformat(timespec="seconds")
    _exec("UPDATE patterns SET good_uses=good_uses+1, box=?, next_review=? WHERE pattern=?", (box, due, pattern))


def practice_result(pattern: str, ok: bool):
    """Falou certo: o padrão sobe de caixa e demora mais para voltar. Errou: fica na caixa 1."""
    if ok:
        _promote(pattern)
    else:
        _exec("UPDATE patterns SET box=1, next_review=? WHERE pattern=?", (_now(), pattern))


def practice_since(since: str) -> list:
    return _q("SELECT kind, ok, created_at FROM practice WHERE created_at >= ? ORDER BY id", (since,))


def drill_items(tag: str) -> list:
    rows = _q("SELECT id, text, targets FROM drill_items WHERE tag=? ORDER BY id DESC LIMIT 12", (tag,))
    for r in rows:
        r["targets"] = json.loads(r["targets"])
    return rows


def add_drill_items(tag: str, items: list):
    for it in items:
        _exec("INSERT INTO drill_items(tag, text, targets, created_at) VALUES (?,?,?,?)",
              (tag, it["text"], json.dumps(it["targets"], ensure_ascii=False), _now()))


# --- Frases para falar e escada de correção ---------------------------------------------

def corrected_sentences(limit: int = 80) -> list[str]:
    """As suas frases das conversas, na versão certa (cartões e contagens)."""
    rows = _q("SELECT better FROM mistakes WHERE better != '' ORDER BY id DESC LIMIT ?", (limit,))
    return [r["better"] for r in rows]


def recent_references(kind: str, since: str) -> set:
    rows = _q("SELECT DISTINCT reference FROM recordings WHERE kind=? AND created_at >= ?", (kind, since))
    return {r["reference"] for r in rows if r["reference"]}


def word_practice(word: str, tag: str) -> dict:
    r = _q("SELECT step, streak, fails, mastered_at, heard_as FROM word_practice WHERE word=? AND tag=?",
           (word, tag), one=True)
    return r or {"step": 0, "streak": 0, "fails": 0, "mastered_at": None, "heard_as": None}


def set_word_heard(word: str, tag: str, heard_as: str):
    _exec("INSERT INTO word_practice(word, tag, heard_as, updated_at) VALUES (?,?,?,?)"
          " ON CONFLICT(word, tag) DO UPDATE SET heard_as=excluded.heard_as", (word, tag, heard_as, _now()))


def save_word_practice(word: str, tag: str, step: int, streak: int, fails: int, mastered: bool):
    _exec(
        "INSERT INTO word_practice(word, tag, step, streak, fails, mastered_at, updated_at) VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(word, tag) DO UPDATE SET step=excluded.step, streak=excluded.streak, fails=excluded.fails,"
        " mastered_at=COALESCE(excluded.mastered_at, word_practice.mastered_at), updated_at=excluded.updated_at",
        (word, tag, step, streak, fails, _now() if mastered else None, _now()),
    )


def restart_word_practice(word: str, tag: str):
    """Errou de novo uma palavra já vencida: a escada recomeça."""
    _exec("UPDATE word_practice SET step=0, streak=0, fails=0, mastered_at=NULL, heard_as=NULL, updated_at=?"
          " WHERE word=? AND tag=?",
          (_now(), word, tag))


def problem_words(since: str, limit: int = 40) -> list:
    """Palavras em que um som saiu trocado, com a última prova (gravação e trecho) de cada uma."""
    # A escada fica de fora: errar "thick" treinando o θ não cria uma palavra-problema nova.
    rows = _q(
        "SELECT word, tag, COUNT(*) AS misses, MAX(created_at) AS last_seen FROM pron_checks"
        " WHERE ok=0 AND created_at >= ? AND source != 'escada'"
        " GROUP BY word, tag ORDER BY misses DESC, last_seen DESC LIMIT ?",
        (since, limit),
    )
    for r in rows:
        last = _q(
            "SELECT c.recording_id, c.start, c.end, c.what, r.reference, r.sent_text, r.transcript FROM pron_checks c"
            " JOIN recordings r ON r.id=c.recording_id WHERE c.word=? AND c.tag=? AND c.ok=0 AND c.source != 'escada'"
            " ORDER BY c.created_at DESC, c.id DESC LIMIT 1",
            (r["word"], r["tag"]), one=True,
        ) or {}
        r.update({"recording_id": last.get("recording_id"), "start": last.get("start"), "end": last.get("end"),
                  "what": last.get("what"),
                  "sentence": last.get("reference") or last.get("sent_text") or last.get("transcript")})
        wp = word_practice(r["word"], r["tag"])
        r["step"] = wp["step"]
        r["mastered"] = bool(wp["mastered_at"]) and wp["mastered_at"] >= r["last_seen"]
    return rows


# --- Baralho -----------------------------------------------------------------------------

def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", (s or "").lower())


def mistake_context(session_id, original: str, width: int = 12) -> dict | None:
    """A frase em volta do erro, na sua resposta, e a pergunta que você estava respondendo."""
    if not session_id or not original:
        return None
    target = _words(original)
    turns = _q("SELECT role, text FROM turns WHERE session_id=? ORDER BY id", (session_id,))
    for i, t in enumerate(turns):
        if t["role"] != "student" or not target:
            continue
        tokens = (t["text"] or "").split()
        keyed = [(k, "".join(_words(w))) for k, w in enumerate(tokens)]
        keyed = [(k, w) for k, w in keyed if w]
        for j in range(len(keyed) - len(target) + 1):
            if [w for _, w in keyed[j:j + len(target)]] == target:
                s, e = keyed[j][0], keyed[j + len(target) - 1][0] + 1
                a, b = max(0, s - width), min(len(tokens), e + width)
                prev = next((p["text"] for p in reversed(turns[:i]) if p["role"] == "tutor"), "") or ""
                questions = re.findall(r"[^.!?]*\?", prev)
                return {"before": " ".join(tokens[a:s]), "match": " ".join(tokens[s:e]), "after": " ".join(tokens[e:b]),
                        "cut_start": a > 0, "cut_end": b < len(tokens),
                        "asked": (questions[-1].strip() if questions else prev[-160:].strip())}
    return None


def mistakes_without_meaning(limit: int = 60) -> list:
    return _q("SELECT id, session_id, original, better FROM mistakes WHERE better != ''"
              " AND (meaning_pt IS NULL OR meaning_pt = '') ORDER BY id DESC LIMIT ?", (limit,))


def set_mistake_meaning(mid: int, meaning: str):
    _exec("UPDATE mistakes SET meaning_pt=? WHERE id=?", (meaning, mid))
    _exec("UPDATE cards SET meaning=? WHERE source='caderno' AND source_id=?", (meaning, mid))


def uncarded_mistakes() -> list:
    """Correções do caderno que ainda não viraram cartão (cartão apagado também conta)."""
    return _q("SELECT m.id, m.pattern, m.original, m.better, m.explanation_pt, m.meaning_pt, m.created_at FROM mistakes m"
              " WHERE m.better != '' AND lower(trim(m.original)) != lower(trim(m.better))"
              " AND NOT EXISTS (SELECT 1 FROM cards c WHERE c.source='caderno' AND c.source_id=m.id) ORDER BY m.id")


def uncarded_words() -> list:
    return _q("SELECT w.id, w.word, w.meaning_pt, w.example, w.created_at FROM words w"
              " WHERE NOT EXISTS (SELECT 1 FROM cards c WHERE c.source='palavra' AND c.source_id=w.id) ORDER BY w.id")


def card_backs(kind: str) -> set:
    return {r["b"] for r in _q("SELECT lower(trim(back)) AS b FROM cards WHERE kind=?", (kind,))}


def add_card(kind: str, front: str, back: str, note: str = "", speak: str = "", hint: str = "",
             source: str = "voce", source_id: int | None = None, created_at: str | None = None,
             meaning: str = "") -> int:
    return _exec(
        "INSERT INTO cards(kind, front, hint, back, note, speak, source, source_id, created_at, meaning)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (kind, front, hint, back, note, speak, source, source_id, created_at or _now(), meaning),
    )


def get_card(cid: int):
    return _q("SELECT * FROM cards WHERE id=?", (cid,), one=True)


def update_card(cid: int, **fields):
    if fields:
        cols = ", ".join(f"{k}=?" for k in fields)
        _exec(f"UPDATE cards SET {cols} WHERE id=?", (*fields.values(), cid))


def delete_card(cid: int):
    """Um cartão que nasceu do caderno fica só marcado como apagado: senão ele renasceria."""
    c = get_card(cid)
    if c and c["source_id"] is not None:
        _exec("UPDATE cards SET deleted=1 WHERE id=?", (cid,))
    else:
        _exec("DELETE FROM cards WHERE id=?", (cid,))
        _exec("DELETE FROM card_reviews WHERE card_id=?", (cid,))


def cards_due(until: str, learn_until: str) -> list:
    # "until" é a virada do dia: um cartão marcado para amanhã vence exatamente nela e não entra hoje.
    return _q(
        "SELECT * FROM cards WHERE deleted=0 AND suspended=0 AND ("
        " (state IN ('learning','relearning') AND due <= ?) OR (state='review' AND due < ?))"
        " ORDER BY (state='review'), due",
        (learn_until, until),
    )


def cards_new(limit: int) -> list:
    if limit <= 0:
        return []
    return _q("SELECT * FROM cards WHERE deleted=0 AND suspended=0 AND state='new'"
              " ORDER BY created_at DESC, id DESC LIMIT ?", (limit,))


def new_cards_seen(since: str) -> int:
    return _q("SELECT COUNT(DISTINCT r.card_id) AS n FROM card_reviews r JOIN cards c ON c.id=r.card_id"
              " WHERE c.deleted=0 AND r.state='new' AND r.reviewed_at >= ?", (since,), one=True)["n"]


def add_review(cid: int, rating: int, state_before: str, days: float, prev: dict) -> int:
    return _exec("INSERT INTO card_reviews(card_id, rating, state, days, prev, reviewed_at) VALUES (?,?,?,?,?,?)",
                 (cid, rating, state_before, days, json.dumps(prev), _now()))


def last_review(since: str):
    return _q("SELECT r.* FROM card_reviews r JOIN cards c ON c.id=r.card_id"
              " WHERE c.deleted=0 AND r.reviewed_at >= ? ORDER BY r.id DESC LIMIT 1", (since,), one=True)


def delete_review(rid: int):
    _exec("DELETE FROM card_reviews WHERE id=?", (rid,))


def list_cards(q: str = "", kind: str = "", limit: int = 400) -> list:
    sql = "SELECT * FROM cards WHERE deleted=0"
    args = []
    if q:
        sql += " AND (front LIKE ? OR back LIKE ? OR note LIKE ?)"
        args += [f"%{q}%"] * 3
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    args.append(limit)
    return _q(sql, tuple(args))


def deck_counts() -> dict:
    rows = _q("SELECT kind, state, suspended, COUNT(*) AS n FROM cards WHERE deleted=0 GROUP BY kind, state, suspended")
    out = {"total": 0, "new": 0, "learning": 0, "review": 0, "suspended": 0, "by_kind": {}}
    for r in rows:
        out["total"] += r["n"]
        out["by_kind"][r["kind"]] = out["by_kind"].get(r["kind"], 0) + r["n"]
        key = "suspended" if r["suspended"] else {"new": "new", "review": "review"}.get(r["state"], "learning")
        out[key] += r["n"]
    return out


def reviews_since(since: str) -> list:
    return _q("SELECT r.card_id, r.rating, r.state, r.days, r.reviewed_at FROM card_reviews r JOIN cards c"
              " ON c.id=r.card_id WHERE c.deleted=0 AND r.reviewed_at >= ? ORDER BY r.id", (since,))


def add_word(word: str, meaning_pt: str, example: str) -> int:
    return _exec("INSERT INTO words(session_id, word, meaning_pt, example, created_at) VALUES (?,?,?,?,?)",
                 (None, word, meaning_pt, example, _now()))


def delete_word(wid: int):
    _exec("DELETE FROM card_reviews WHERE card_id IN (SELECT id FROM cards WHERE source='palavra' AND source_id=?)",
          (wid,))
    _exec("DELETE FROM cards WHERE source='palavra' AND source_id=?", (wid,))
    _exec("DELETE FROM words WHERE id=?", (wid,))


def add_drill_item(tag: str, text: str, targets: list) -> int:
    return _exec("INSERT INTO drill_items(tag, text, targets, created_at) VALUES (?,?,?,?)",
                 (tag, text, json.dumps(targets, ensure_ascii=False), _now()))


def delete_drill_item(did: int):
    _exec("DELETE FROM drill_items WHERE id=?", (did,))


def set_compare(rid: int, data: dict):
    _exec("UPDATE recordings SET compare=? WHERE id=?", (json.dumps(data, ensure_ascii=False), rid))


def ladder_attempts(tag: str, word: str, limit: int = 10) -> list:
    """As últimas tentativas da escada desta palavra, com o veredito do som e o trecho para ouvir."""
    recs = _q("SELECT id, reference, compare, created_at FROM recordings WHERE kind='escada' AND sentence_id=?"
              " ORDER BY id DESC LIMIT ?", (f"escada:{tag}:{word}", limit))
    out = []
    for r in recs:
        info = json.loads(r["compare"]) if r["compare"] else {}
        wanted = {t.lower() for t in info.get("targets", [])}
        checks = [c for c in _q("SELECT word, what, ok, start, end FROM pron_checks WHERE recording_id=? AND tag=?"
                                " ORDER BY id", (r["id"], tag)) if not wanted or c["word"].lower() in wanted]
        if not checks:
            continue
        bad = next((c for c in checks if not c["ok"]), None)
        c = bad or checks[0]
        out.append({"recording_id": r["id"], "text": r["reference"], "created_at": r["created_at"],
                    "ok": bad is None, "tag": tag, "word": c["word"], "what": c["what"], "start": c["start"], "end": c["end"]})
    return out


def best_take(tag: str, word: str):
    """A sua última vez com o som certo, de preferência nesta palavra: para ouvir a sua voz acertando."""
    return _q("SELECT c.word, c.recording_id, c.start, c.end, c.created_at FROM pron_checks c"
              " JOIN recordings r ON r.id=c.recording_id WHERE c.tag=? AND c.ok=1 AND r.path IS NOT NULL"
              " AND c.start IS NOT NULL AND c.end IS NOT NULL AND c.end > c.start"
              " ORDER BY (lower(c.word)=?) DESC, c.created_at DESC, c.id DESC LIMIT 1", (tag, word), one=True)


def recent_mistakes(limit: int = 12) -> list:
    return _q("SELECT pattern, original, better, explanation_pt, created_at FROM mistakes WHERE better != ''"
              " ORDER BY id DESC LIMIT ?", (limit,))


# --- Ouvir a diferença --------------------------------------------------------------------

def add_listen_trial(tag: str, word: str, other: str, chosen: str, ok: bool, voice: str) -> int:
    return _exec("INSERT INTO listen_trials(tag, word, other, chosen, ok, voice, created_at) VALUES (?,?,?,?,?,?,?)",
                 (tag, word, other, chosen, int(ok), voice[:80], _now()))


def listen_trials(since: str) -> list:
    return _q("SELECT tag, word, other, chosen, ok, voice, created_at FROM listen_trials WHERE created_at >= ?"
              " ORDER BY id", (since,))


# --- Imitar (shadowing) ---------------------------------------------------------------------

def add_passage(title: str, sentences: list[str], focus: list[str], source: str) -> int:
    return _exec("INSERT INTO passages(title, sentences, focus, source, created_at) VALUES (?,?,?,?,?)",
                 (title, json.dumps(sentences, ensure_ascii=False), json.dumps(focus), source, _now()))


def _passage(r: dict) -> dict:
    r["sentences"] = json.loads(r["sentences"] or "[]")
    r["focus"] = json.loads(r["focus"] or "[]")
    return r


def passages(limit: int = 12) -> list:
    return [_passage(r) for r in _q("SELECT * FROM passages ORDER BY id DESC LIMIT ?", (limit,))]


def get_passage(pid: int):
    r = _q("SELECT * FROM passages WHERE id=?", (pid,), one=True)
    return _passage(r) if r else None


def passage_progress(pid: int) -> dict:
    """Por frase do texto (índice; -1 é o texto inteiro): a maior velocidade em que você passou."""
    out = {}
    for r in _q("SELECT sentence_id, compare FROM recordings WHERE kind='imitar' AND sentence_id LIKE ?",
                (f"imitar:{pid}:%",)):
        info = json.loads(r["compare"]) if r["compare"] else {}
        if info.get("ok"):
            idx = int(r["sentence_id"].rsplit(":", 1)[1])
            out[idx] = max(out.get(idx, 0), float(info.get("rate") or 0))
    return out


# --- Usar livre ------------------------------------------------------------------------------

def add_prompt(kind: str, ref: str, question_en: str, question_pt: str, target: str) -> int:
    return _exec("INSERT INTO free_prompts(kind, ref, question_en, question_pt, target, created_at) VALUES (?,?,?,?,?,?)",
                 (kind, ref, question_en, question_pt, target, _now()))


def open_prompts(limit: int = 6, kind: str | None = None, ref: str | None = None) -> list:
    sql, args = "SELECT * FROM free_prompts WHERE answered_at IS NULL", []
    if kind:
        sql += " AND kind=? AND ref=?"
        args += [kind, ref]
    return _q(sql + " ORDER BY id LIMIT ?", (*args, limit))


def get_prompt(pid: int):
    return _q("SELECT * FROM free_prompts WHERE id=?", (pid,), one=True)


def answer_prompt(pid: int):
    _exec("UPDATE free_prompts SET answered_at=? WHERE id=?", (_now(), pid))


# --- Entender ----------------------------------------------------------------------------------

def lesson(key: str):
    r = _q("SELECT * FROM lessons WHERE key=?", (key,), one=True)
    if r:
        r["content"] = json.loads(r["content"])
    return r


def save_lesson(key: str, content: dict):
    _exec("INSERT INTO lessons(key, content, created_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET"
          " content=excluded.content, created_at=excluded.created_at, score=NULL, total=NULL, done_at=NULL",
          (key, json.dumps(content, ensure_ascii=False), _now()))


def score_lesson(key: str, score: int, total: int):
    _exec("UPDATE lessons SET score=?, total=?, done_at=? WHERE key=?", (score, total, _now(), key))


def lessons_done(since: str) -> list:
    """Aulas com o exercício terminado desde `since` (para mostrar na sessão do Progresso)."""
    rows = _q("SELECT key, content, score, total, done_at FROM lessons WHERE done_at >= ?", (since,))
    return [{"key": r["key"], "title": json.loads(r["content"]).get("title") or r["key"], "score": r["score"],
             "total": r["total"], "done_at": r["done_at"]} for r in rows]


def lessons_state() -> dict:
    return {r["key"]: r for r in _q("SELECT key, score, total, done_at FROM lessons")}


# --- Perguntar ------------------------------------------------------------------------------

def ask_thread() -> int:
    """A conversa atual: a última com mensagens, ou a nova que "Nova conversa" abriu."""
    last = _q("SELECT MAX(thread) AS t FROM ask_messages", one=True)["t"] or 1
    opened = int(get_settings().get("ask_thread") or 0)
    return max(last, opened)


def ask_messages(thread: int, limit: int = 60) -> list:
    rows = _q("SELECT * FROM (SELECT * FROM ask_messages WHERE thread=? ORDER BY id DESC LIMIT ?) ORDER BY id",
              (thread, limit))
    for r in rows:
        r["actions"] = json.loads(r["actions"]) if r["actions"] else []
    return rows


def add_ask_message(thread: int, role: str, text: str, actions: list | None = None) -> int:
    return _exec("INSERT INTO ask_messages(thread, role, text, actions, created_at) VALUES (?,?,?,?,?)",
                 (thread, role, text, json.dumps(actions or [], ensure_ascii=False), _now()))


def get_ask_message(mid: int):
    r = _q("SELECT * FROM ask_messages WHERE id=?", (mid,), one=True)
    if r:
        r["actions"] = json.loads(r["actions"]) if r["actions"] else []
    return r


def set_ask_actions(mid: int, actions: list):
    _exec("UPDATE ask_messages SET actions=? WHERE id=?", (json.dumps(actions, ensure_ascii=False), mid))


# --- Atividade e ajustes -------------------------------------------------------------

def add_activity(kind: str, ref: str, seconds: int):
    _exec("INSERT INTO activity(kind, ref, seconds, created_at) VALUES (?,?,?,?)",
          (kind, ref, max(0, min(int(seconds), 3 * 3600)), _now()))


def activity(since: str) -> list:
    return _q("SELECT kind, ref, seconds, created_at FROM activity WHERE created_at >= ? ORDER BY id", (since,))


DEFAULT_SETTINGS = {"weekly_target": "3", "session_minutes": "15", "goal": "", "cards_per_day": "10",
                    "focus_tag": ""}


def get_settings() -> dict:
    out = dict(DEFAULT_SETTINGS)
    out.update({r["key"]: r["value"] for r in _q("SELECT key, value FROM settings")})
    return out


def set_setting(key: str, value: str):
    _exec("INSERT INTO settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
          (key, value))


# --- Números para o progresso ---------------------------------------------------------

def conversation_stats() -> list:
    """Por sessão de conversa: palavras faladas, erros contados e nível estimado."""
    out = []
    for s in _q("SELECT id, scenario, started_at, ended_at, summary FROM sessions ORDER BY id"):
        words = errors = answers = 0
        partial = False
        for t in _q("SELECT text, data FROM turns WHERE session_id=? AND role='student'", (s["id"],)):
            answers += 1
            words += len((t["text"] or "").split())
            data = json.loads(t["data"]) if t["data"] else {}
            counts = data.get("pattern_counts")
            if counts is None:  # conversa de antes da contagem completa: só os cartões
                partial = True
                errors += len(data.get("corrections", []))
            else:
                errors += sum(pc["count"] for pc in counts)
        summary = json.loads(s["summary"]) if s["summary"] else {}
        out.append({"id": s["id"], "scenario": s["scenario"], "date": s["started_at"], "answers": answers,
                    "words": words, "errors": errors, "partial": partial,
                    "scale": summary.get("scale_estimate") or None, "cefr": summary.get("cefr_estimate") or None})
    return out
