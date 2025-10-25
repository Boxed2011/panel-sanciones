from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
# import sqlite3  <-- LO BORRAMOS
import psycopg2 # <-- AÑADIDO
import psycopg2.extras # <-- AÑADIDO
from psycopg2 import errors as pg_errors # <-- AÑADIDO
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv
import requests
from datetime import datetime

load_dotenv()

APP_SECRET = os.getenv("APP_SECRET", "cambia_esto_ya")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
# AÑADIMOS LA VARIABLE DE ENTORNO PARA LA BASE DE DATOS
DATABASE_URL = os.getenv("DATABASE_URL")

# DB_PATH = "database.db" <-- LO BORRAMOS

app = Flask(__name__)
app.secret_key = APP_SECRET

# -------------- DB helpers (MODIFICADOS PARA NEON/POSTGRESQL) --------------
def get_db():
    if not DATABASE_URL:
        raise ValueError("No se encontró DATABASE_URL en las variables de entorno")
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db()
    # Usamos un cursor
    with conn.cursor() as c:
        # CAMBIAMOS "INTEGER PRIMARY KEY AUTOINCREMENT" por "SERIAL PRIMARY KEY"
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS sanciones (
            id SERIAL PRIMARY KEY,
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
    conn.commit() # Guardar cambios
    conn.close()

# Inicializa DB al arrancar si no existe
# Esto creará las tablas en NEON la primera vez que arranque la app
try:
    init_db()
except Exception as e:
    print(f"Error al inicializar la base de datos (puede que ya exista): {e}")


# -------------- Auth helpers (MODIFICADOS PARA NEON/POSTGRESQL) --------------
def create_user(username, password):
    pw_hash = generate_password_hash(password)
    conn = get_db()
    try:
        with conn.cursor() as c:
            # CAMBIAMOS "?" por "%s"
            c.execute("INSERT INTO users (username, password_hash, created_at) VALUES (%s, %s, %s)",
                     (username, pw_hash, datetime.utcnow().isoformat()))
        conn.commit()
        return True
    # CAMBIAMOS el tipo de error
    except (psycopg2.IntegrityError, pg_errors.UniqueViolation):
        conn.rollback() # Deshacer
        return False
    finally:
        conn.close()

def verify_user(username, password):
    conn = get_db()
    # USAMOS DictCursor para poder hacer row["password_hash"]
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
        # CAMBIAMOS "?" por "%s"
        c.execute("SELECT * FROM users WHERE username = %s", (username,))
        row = c.fetchone()
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
    fecha = data.get("fecha") or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    objetivo = data.get("objetivo", "—")
    accion = data.get("accion", "sancionar")
    motivo = data.get("motivo", "—")
    gravedad = data.get("gravedad", "Media")
    conteo = int(data.get("conteo") or 0)
    pruebas = data.get("pruebas", "")
    moderador = session.get("user")

    # Guardar en DB (MODIFICADO)
    conn = get_db()
    try:
        with conn.cursor() as c:
            # CAMBIAMOS los "?" por "%s"
            c.execute("""
                INSERT INTO sanciones (fecha, objetivo, accion, motivo, gravedad, conteo, pruebas, moderador, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (fecha, objetivo, accion, motivo, gravedad, conteo, pruebas, moderador, datetime.utcnow().isoformat()))
        conn.commit()
    finally:
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
    # USAMOS DictCursor
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
        c.execute("SELECT * FROM sanciones ORDER BY id DESC")
        rows = c.fetchall()
    conn.close()
    data = [dict(r) for r in rows]
    return jsonify({"ok": True, "data": data})

# CLI helper para crear user desde terminal
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
    
    # Esta parte solo se usa para pruebas locales, Render usará gunicorn
    print("Para producción, usa 'gunicorn app:app'")
    app.run(host="0.0.0.0", port=5000, debug=True)