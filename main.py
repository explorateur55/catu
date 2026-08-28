"""
Greenstuff API — Backend Catu (v1 autonome)
FastAPI + SQLite + QR codes segno
Sert le site vitrine, l'appli paniers et l'API REST
"""
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import json, io, os, sqlite3

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import segno

# ─── Configuration ───────────────────────────────────
DB_PATH = os.environ.get("DB_PATH", "catu.db")
STATIC = Path(__file__).parent / "static"
FRIDAY_PHASES = ["14h–15h", "15h–16h", "16h–17h", "17h–18h"]

def clean_creneau(creneau: str) -> str:
    """Accepte 'Vendredi 14h–15h' ou '14h–15h'"""
    for suffix in FRIDAY_PHASES:
        if creneau.endswith(suffix):
            return suffix
    return creneau
PRIX_PANIER = 13  # €
SEED_FERME = "catu"

app = FastAPI(title="Greenstuff — Catu API", version="1.0.0")

# ─── Base SQLite ─────────────────────────────────────
def get_db() -> sqlite3.Connection:
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS fermes (
            slug     TEXT PRIMARY KEY,
            nom      TEXT NOT NULL,
            prix     INTEGER NOT NULL DEFAULT 13,
            capacite INTEGER NOT NULL DEFAULT 50
        );
        CREATE TABLE IF NOT EXISTS commandes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ferme      TEXT NOT NULL DEFAULT 'catu',
            code       TEXT NOT NULL,
            prenom     TEXT NOT NULL,
            tel        TEXT NOT NULL,
            qte        INTEGER NOT NULL DEFAULT 1,
            creneau    TEXT NOT NULL,
            payee      INTEGER NOT NULL DEFAULT 0,
            retiree    INTEGER NOT NULL DEFAULT 0,
            cree_le    TEXT NOT NULL,
            retire_le  TEXT,
            UNIQUE(ferme, code)
        );
        CREATE TABLE IF NOT EXISTS stocks (
            ferme     TEXT PRIMARY KEY,
            vendredi  TEXT NOT NULL,
            total     INTEGER NOT NULL DEFAULT 50,
            reserves  INTEGER NOT NULL DEFAULT 0
        );
    """)
    # Seed ferme
    c = conn.execute("SELECT count(*) FROM fermes WHERE slug=?", (SEED_FERME,))
    if c.fetchone()[0] == 0:
        today = date.today()
        # Next Friday
        days_to_friday = (4 - today.weekday()) % 7
        if days_to_friday == 0:
            days_to_friday = 7
        next_friday = (today + timedelta(days=days_to_friday)).isoformat()
        conn.execute("INSERT INTO fermes(slug,nom,prix,capacite) VALUES(?,?,?,?)",
                     (SEED_FERME, "Ferme CATU", PRIX_PANIER, 50))
        conn.execute("INSERT INTO stocks(ferme,vendredi,total,reserves) VALUES(?,?,?,?)",
                     (SEED_FERME, next_friday, 50, 0))
        conn.commit()
    conn.close()

init_db()

# ─── Helpers ───────────────────────────────────────────
def next_code(ferme: str) -> str:
    conn = get_db()
    c = conn.execute("SELECT code FROM commandes WHERE ferme=? ORDER BY id DESC LIMIT 1", (ferme,))
    row = c.fetchone()
    conn.close()
    if row and row["code"].startswith("A"):
        last = int(row["code"][1:])
        return f"A{last+1:03d}"
    return "A001"

def ferme_check(ferme: str) -> bool:
    conn = get_db()
    c = conn.execute("SELECT 1 FROM fermes WHERE slug=?", (ferme,))
    exists = c.fetchone() is not None
    conn.close()
    return exists

def maintenant() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

# ── Routes API ────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0"}

@app.get("/api/ferme/{ferme}")
def get_ferme(ferme: str):
    conn = get_db()
    f = conn.execute("SELECT * FROM fermes WHERE slug=?", (ferme,)).fetchone()
    conn.close()
    if not f:
        raise HTTPException(404, "Ferme inconnue")
    return dict(f)

@app.get("/api/paniers")
def get_paniers(ferme: str = Query(default=SEED_FERME)):
    conn = get_db()
    f = conn.execute("SELECT * FROM fermes WHERE slug=?", (ferme,)).fetchone()
    s = conn.execute("SELECT * FROM stocks WHERE ferme=?", (ferme,)).fetchone()
    conn.close()
    if not f or not s:
        raise HTTPException(404)
    return {
        "ferme": ferme,
        "nom": f["nom"],
        "prix": f["prix"],
        "capacite": f["capacite"],
        "vendredi": s["vendredi"],
        "reserves": s["reserves"],
        "disponibles": s["total"] - s["reserves"],
        "total": s["total"],
    }

@app.post("/api/reservations")
async def reserver(request: Request):
    body = await request.json()
    ferme = body.get("ferme", SEED_FERME)
    prenom = body.get("prenom", "").strip()
    tel = body.get("tel", "").strip()
    qte = int(body.get("qte", 1))
    creneau = clean_creneau(body.get("creneau", FRIDAY_PHASES[0]))

    if not prenom or not tel:
        raise HTTPException(400, "Prénom et téléphone requis")
    if qte < 1 or qte > 10:
        raise HTTPException(400, "1 à 10 paniers maximum")
    if creneau not in FRIDAY_PHASES:
        raise HTTPException(400, "Créneau invalide")

    conn = get_db()
    try:
        s = conn.execute("SELECT * FROM stocks WHERE ferme=?", (ferme,)).fetchone()
        if not s:
            raise HTTPException(404, "Ferme introuvable")
        disponibles = s["total"] - s["reserves"]
        if qte > disponibles:
            raise HTTPException(409, f"Plus que {disponibles} panier(s) disponible(s)")

        code = next_code(ferme)
        total = qte * PRIX_PANIER
        now = maintenant()

        conn.execute(
            "INSERT INTO commandes(ferme,code,prenom,tel,qte,creneau,cree_le) VALUES(?,?,?,?,?,?,?)",
            (ferme, code, prenom, tel, qte, creneau, now))
        conn.execute("UPDATE stocks SET reserves = reserves + ? WHERE ferme=?", (qte, ferme))
        conn.commit()

        return {
            "status": "ok",
            "code": code,
            "total": total,
            "paniers": qte,
            "creneau": creneau,
            "ferme": ferme,
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        conn.close()

@app.get("/api/commandes")
def get_commandes(ferme: str = Query(default=SEED_FERME)):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM commandes WHERE ferme=? ORDER BY id DESC", (ferme,)).fetchall()
    conn.close()
    return [{
        "id": r["id"], "code": r["code"], "prenom": r["prenom"],
        "tel": r["tel"], "qte": r["qte"], "creneau": r["creneau"],
        "payee": bool(r["payee"]), "retiree": bool(r["retiree"]),
        "cree_le": r["cree_le"], "retire_le": r["retire_le"] or ""
    } for r in rows]

@app.post("/api/commandes/{code}/valider")
def valider_retrait(code: str, ferme: str = Query(default=SEED_FERME)):
    conn = get_db()
    c = conn.execute("SELECT * FROM commandes WHERE ferme=? AND code=?", (ferme, code)).fetchone()
    if not c:
        conn.close()
        raise HTTPException(404, "Commande introuvable")
    if c["retiree"]:
        conn.close()
        raise HTTPException(409, "Déjà retirée")
    now = maintenant()
    conn.execute("UPDATE commandes SET retiree=1, retire_le=? WHERE id=?", (now, c["id"]))
    conn.commit()
    conn.close()
    return {
        "status": "ok",
        "code": code,
        "prenom": c["prenom"],
        "qte": c["qte"],
        "creneau": c["creneau"],
        "retire_le": now,
        "message": f"{c['prenom']} — {c['qte']} panier(s) — Retrait validé ✅"
    }

@app.get("/api/kpis")
def get_kpis(ferme: str = Query(default=SEED_FERME)):
    conn = get_db()
    s = conn.execute("SELECT * FROM stocks WHERE ferme=?", (ferme,)).fetchone()
    cmds = conn.execute(
        "SELECT count(*) as total, sum(qte) as paniers, sum(retiree) as retires "
        "FROM commandes WHERE ferme=?", (ferme,)).fetchone()
    conn.close()
    if not s:
        raise HTTPException(404)
    reserves = s["reserves"]
    retires = cmds["retires"] or 0
    ca = reserves * PRIX_PANIER
    return {
        "ferme": ferme,
        "reserves": reserves,
        "retires": retires,
        "ca": ca,
        "total_paniers": s["total"],
        "disponibles": s["total"] - reserves,
        "vendredi": s["vendredi"],
    }

@app.post("/api/stock")
async def update_stock(request: Request):
    body = await request.json()
    ferme = body.get("ferme", SEED_FERME)
    total = int(body.get("total", 50))

    if total < 1 or total > 500:
        raise HTTPException(400, "1 à 500 paniers")
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO stocks(ferme,vendredi,total,reserves) "
        "VALUES(?,COALESCE((SELECT vendredi FROM stocks WHERE ferme=?), date('now'), ?, "
        "(SELECT reserves FROM stocks WHERE ferme=?))",
        (ferme, ferme, total, ferme))
    conn.commit()
    conn.close()
    return {"status": "ok", "ferme": ferme, "total": total}

@app.get("/api/qr/{code}.png")
def get_qr(code: str):
    # QR code URL vers la page de retrait (scan producteur)
    qr = segno.make_qr(f"CATU\nCommande {code}")
    buf = io.BytesIO()
    qr.save(buf, kind='png', scale=8, dark='#20302a', light='white', border=2)
    buf.seek(0)
    return Response(content=buf.read(), media_type="image/png")

# ── Routes HTML ───────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index_site():
    return STATIC.joinpath("index.html").read_text(encoding="utf-8")

@app.get("/paniers", response_class=HTMLResponse)
def index_app():
    return STATIC.joinpath("app.html").read_text(encoding="utf-8")

# Static files fallback (CSS, JS, images dans le HTML sont inline/URLs externes)
# On mount après les routes = pas de conflit
app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)