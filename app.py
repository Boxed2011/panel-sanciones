from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv
import requests
from datetime import datetime

load_dotenv()

APP_SECRET = os.getenv("APP_SECRET", "cambia_esto_ya")  # cambiar en producción
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")  # obligatorio en .env o en variables de entorno

DB_PATH = "database.db"

app = Flask(__name__)
app.secret_key = APP_SECRET

# -------------- DB helpers --------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    # Usuarios: id, username, password_hash, created_at
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    # Sanciones: id, fecha, objetivo, accion, motivo, gravedad, conteo, pruebas, moderador, created_at
    c.execute("""
    CREATE TABLE IF NOT EXISTS sanciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        objetivo TEXT,
        accion TEXT,
        motivo TEXT,
        gravedad TEXT,
        conteo INTEGER,
        pruebas TEXT,
        moderador TEXT,
        created_at TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

# Inicializa DB al arrancar si no existe
init_db()

# -------------- Auth helpers --------------
def create_user(username, password):
    pw_hash = generate_password_hash(password)
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                     (username, pw_hash, datetime.utcnow().isoformat()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def verify_user(username, password):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if row and check_password_hash(row["password_hash"], password):
        return True
    return False

# -------------- Routes --------------
@app.route("/")
def index():
    if session.get("user"):
        return redirect(url_for("panel"))
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not username or not password:
        flash("Usuario y contraseña requeridos")
        return redirect(url_for("index"))
    if verify_user(username, password):
        session["user"] = username
        return redirect(url_for("panel"))
    else:
        flash("Credenciales incorrectas")
        return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Sesión cerrada")
    return redirect(url_for("index"))

@app.route("/panel")
def panel():
    if not session.get("user"):
        return redirect(url_for("index"))
    return render_template("panel.html", user=session.get("user"))

@app.route("/send_sancion", methods=["POST"])
def send_sancion():
    if not session.get("user"):
        return jsonify({"ok": False, "msg": "No autenticado"}), 401

    data = request.json
    # campos esperados: fecha, objetivo, accion, motivo, gravedad, conteo, pruebas, moderador
    fecha = data.get("fecha") or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    objetivo = data.get("objetivo", "—")
    accion = data.get("accion", "sancionar")
    motivo = data.get("motivo", "—")
    gravedad = data.get("gravedad", "Media")
    conteo = int(data.get("conteo") or 0)
    pruebas = data.get("pruebas", "")
    moderador = session.get("user")

    # Guardar en DB
    conn = get_db()
    conn.execute("""
        INSERT INTO sanciones (fecha, objetivo, accion, motivo, gravedad, conteo, pruebas, moderador, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (fecha, objetivo, accion, motivo, gravedad, conteo, pruebas, moderador, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    # Enviar al webhook de Discord como embed
    if not DISCORD_WEBHOOK:
        return jsonify({"ok": False, "msg": "Webhook no configurado"}), 500

    embed = {
        "title": "Registro de sanción",
        "description": f"**Acción:** {accion}",
        "fields": [
            {"name": "Objetivo", "value": objetivo, "inline": True},
            {"name": "Moderador", "value": moderador, "inline": True},
            {"name": "Fecha", "value": fecha, "inline": True},
            {"name": "Motivo", "value": motivo, "inline": False},
            {"name": "Gravedad", "value": gravedad, "inline": True},
            {"name": "Conteo", "value": str(conteo), "inline": True},
            {"name": "Pruebas", "value": pruebas or "No hay pruebas", "inline": False},
        ],
        "timestamp": datetime.utcnow().isoformat()
    }
    payload = {"embeds": [embed]}

    try:
        res = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        res.raise_for_status()
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Error al enviar webhook: {e}"}), 500

    return jsonify({"ok": True, "msg": "Sanción enviada y guardada"})

# Endpoint opcional para listar sanciones (solo para ti si estás logueado)
@app.route("/api/sanciones")
def api_sanciones():
    if not session.get("user"):
        return jsonify({"ok": False, "msg": "No autenticado"}), 401
    conn = get_db()
    rows = conn.execute("SELECT * FROM sanciones ORDER BY id DESC").fetchall()
    conn.close()
    data = [dict(r) for r in rows]
    return jsonify({"ok": True, "data": data})

# CLI helper para crear user desde terminal (si corres python app.py create_user)
if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "create_user":
        if len(sys.argv) != 4:
            print("Uso: python app.py create_user <username> <password>")
            sys.exit(1)
        u = sys.argv[2]
        p = sys.argv[3]
        ok = create_user(u, p)
        if ok:
            print(f"Usuario '{u}' creado.")
        else:
            print("Error: usuario ya existe.")
        sys.exit(0)

    app.run(host="0.0.0.0", port=5000, debug=True)
