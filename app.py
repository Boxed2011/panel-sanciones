from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import psycopg2 
import psycopg2.extras 
from psycopg2 import errors as pg_errors 
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv
import requests
from datetime import datetime

load_dotenv()

APP_SECRET = os.getenv("APP_SECRET", "cambia_esto_ya")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
DATABASE_URL = os.getenv("DATABASE_URL")

app = Flask(__name__)
app.secret_key = APP_SECRET

# -------------- DB helpers --------------
def get_db():
    if not DATABASE_URL:
        raise ValueError("No se encontró DATABASE_URL en las variables de entorno")
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db()
    with conn.cursor() as c:
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
    conn.commit() 
    conn.close()

# -------------- Auth helpers --------------
def create_user(username, password):
    pw_hash = generate_password_hash(password)
    conn = get_db()
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO users (username, password_hash, created_at) VALUES (%s, %s, %s)",
                     (username, pw_hash, datetime.utcnow().isoformat()))
        conn.commit()
        return True
    except (psycopg2.IntegrityError, pg_errors.UniqueViolation):
        conn.rollback() 
        return False
    finally:
        conn.close()

def verify_user(username, password):
    conn = get_db()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
        c.execute("SELECT * FROM users WHERE username = %s", (username,))
        row = c.fetchone()
    conn.close()
    if row and check_password_hash(row["password_hash"], password):
        return True
    return False

# ----- INICIALIZACIÓN DE LA APP -----
try:
    init_db()
except Exception as e:
    print(f"Error al inicializar la base de datos (puede que ya exista): {e}")

admin_user = os.getenv("DEFAULT_ADMIN_USER")
admin_pass = os.getenv("DEFAULT_ADMIN_PASS")

if admin_user and admin_pass:
    print(f"Intentando crear usuario por defecto: {admin_user}")
    created = create_user(admin_user, admin_pass)
    if created:
        print("Usuario por defecto CREADO CON ÉXITO.")
    else:
        print("Usuario por defecto ya existía, no se ha creado.")
else:
    print("No se encontraron variables DEFAULT_ADMIN_USER y DEFAULT_ADMIN_PASS, no se crea usuario.")
# ----- FIN DEL BLOQUE DE INICIALIZACIÓN -----


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
    objetivo_name = data.get("objetivo", "—")
    user_id = data.get("user_id", "").strip() # La ID de Discord nueva
    accion = data.get("accion", "sancionar")
    motivo = data.get("motivo", "—")
    gravedad = data.get("gravedad", "Media")
    conteo = int(data.get("conteo") or 0)
    pruebas = data.get("pruebas", "")
    moderador = session.get("user")

    objetivo_final_db = objetivo_name
    if user_id:
        objetivo_final_db = f"{objetivo_name} (ID: {user_id})"

    objetivo_discord_ping = objetivo_name
    if user_id:
        objetivo_discord_ping = f"{objetivo_name} (<@{user_id}>)"

    conn = get_db()
    try:
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO sanciones (fecha, objetivo, accion, motivo, gravedad, conteo, pruebas, moderador, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (fecha, objetivo_final_db, accion, motivo, gravedad, conteo, pruebas, moderador, datetime.utcnow().isoformat()))
        conn.commit()
    finally:
        conn.close()

    if not DISCORD_WEBHOOK:
        return jsonify({"ok": False, "msg": "Webhook no configurado"}), 500

    embed = {
        "title": "Registro de sanción",
        "description": f"**Acción:** {accion}",
        "fields": [
            {"name": "Objetivo", "value": objetivo_discord_ping, "inline": True}, 
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

@app.route("/api/sanciones")
def api_sanciones():
    if not session.get("user"):
        return jsonify({"ok": False, "msg": "No autenticado"}), 401
    conn = get_db()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
        c.execute("SELECT * FROM sanciones ORDER BY id DESC")
        rows = c.fetchall()
    conn.close()
    data = [dict(r) for r in rows]
    return jsonify({"ok": True, "data": data})

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
    
    print("Para producción, usa 'gunicorn app:app'")
    app.run(host="0.0.0.0", port=5000, debug=True)