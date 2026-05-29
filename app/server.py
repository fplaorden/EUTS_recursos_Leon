import os
import sqlite3
import secrets
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from flask import Flask, request, jsonify, session, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash
from geopy.geocoders import Nominatim
import sys

# Import geocoding helper
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.geocode_utils import GeocodingCache, get_coordinates, clean_address

app = Flask(__name__)

# Config
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "leon_assistance_social_default_secret_key_12345")
# Keep session active for 2 hours
app.permanent_session_lifetime = timedelta(hours=2)

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(WORKSPACE_DIR, "data", "app.db")
CACHE_PATH = os.path.join(WORKSPACE_DIR, "data", "geocoding_cache.json")
LOG_PATH = os.path.join(WORKSPACE_DIR, "data", "sent_emails.log")

# Setup Geolocator
geolocator = Nominatim(user_agent="león_social_resources_app")

# Ensure directories exist
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Auto-inicializar base de datos si no existe o está vacía
if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0:
    print("Base de datos no encontrada o vacía. Iniciando ingesta automática desde Excel...")
    try:
        from scripts.ingest_data import ingest_all
        ingest_all()
    except Exception as e:
        print(f"Error al inicializar la base de datos automáticamente: {e}")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def login_required(f):
    """Decorator to require login on API routes"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "No autorizado. Inicie sesión primero."}), 401
        return f(*args, **kwargs)
    return decorated_function


# --- EMAIL RECOVERY UTILITY ---
def send_recovery_email(email, reset_link, username):
    smtp_server = os.environ.get("SMTP_SERVER", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASSWORD", "")
    smtp_from = os.environ.get("SMTP_FROM", "noreply@leon.es")

    subject = "Recuperación de contraseña - Asistencia Social León"
    body = f"""Hola, {username}.

Has solicitado restablecer tu contraseña en el portal de Recursos de Asistencia Social de León.

Para restablecer tu contraseña, haz clic en el siguiente enlace o cópialo en tu navegador:
{reset_link}

Este enlace expirará en 1 hora. Si no has solicitado esto, puedes ignorar este correo.

Saludos,
Ayuntamiento de León
"""

    if smtp_server:
        # Send actual email
        try:
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = smtp_from
            msg['To'] = email

            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_from, [email], msg.as_string())
            print(f"Sent recovery email to {email}")
            return True
        except Exception as e:
            print(f"Failed to send SMTP email: {e}")
            # Fall back to logging
    
    # Logging fallback
    try:
        log_entry = f"""========================================
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
To: {email}
Subject: {subject}
Reset Link: {reset_link}
Content:
{body}
========================================
"""
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(log_entry)
        print(f"Logged recovery email to {LOG_PATH}")
        return True
    except Exception as e:
        print(f"Failed to write email to log: {e}")
        return False


# --- AUTHENTICATION ROUTES ---

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json or {}
    username_or_email = data.get('username')
    password = data.get('password')
    
    if not username_or_email or not password:
        return jsonify({"error": "Faltan credenciales"}), 400
        
    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? OR email = ?", 
        (username_or_email, username_or_email)
    ).fetchone()
    conn.close()
    
    if user and check_password_hash(user['password_hash'], password):
        session.permanent = True
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['email'] = user['email']
        return jsonify({
            "message": "Login exitoso",
            "user": {
                "id": user['id'],
                "username": user['username'],
                "email": user['email']
            }
        })
        
    return jsonify({"error": "Credenciales inválidas"}), 401


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"message": "Sesión cerrada correctamente"})


@app.route('/api/auth/check', methods=['GET'])
def check_auth():
    if 'user_id' in session:
        return jsonify({
            "authenticated": True,
            "user": {
                "id": session['user_id'],
                "username": session['username'],
                "email": session['email']
            }
        })
    return jsonify({"authenticated": False}), 200


@app.route('/api/auth/forgot-password', methods=['POST'])
def forgot_password():
    data = request.json or {}
    email = data.get('email')
    
    if not email:
        return jsonify({"error": "Se requiere el correo electrónico"}), 400
        
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    
    # Generate token always to prevent timing attacks, but send only if user exists
    token = secrets.token_hex(32)
    expires = datetime.now() + timedelta(hours=1)
    
    if user:
        conn.execute(
            "INSERT INTO recovery_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
            (user['id'], token, expires.strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit()
        
        # Build reset link. Nginx config points to login.html with token.
        # Inside login.html we will read this token parameter to show the Reset Form.
        # Use Host header dynamically or use standard relative path
        host = request.headers.get('Host', 'localhost')
        # If running on 443 under Nginx, or local 8000
        proto = "https" if request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https' else "http"
        reset_link = f"{proto}://{host}/login.html?token={token}"
        
        send_recovery_email(email, reset_link, user['username'])
        
    conn.close()
    
    # Return generic success to avoid email harvesting
    return jsonify({"message": "Si el correo está registrado, se enviará un enlace de recuperación."})


@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    data = request.json or {}
    token = data.get('token')
    new_password = data.get('password')
    
    if not token or not new_password:
        return jsonify({"error": "Token y contraseña requeridos"}), 400
        
    conn = get_db_connection()
    
    # Find token
    token_row = conn.execute(
        "SELECT * FROM recovery_tokens WHERE token = ? AND used = 0 AND expires_at > ?",
        (token, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    ).fetchone()
    
    if not token_row:
        conn.close()
        return jsonify({"error": "Token inválido o expirado"}), 400
        
    # Hash and update
    hashed = generate_password_hash(new_password)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hashed, token_row['user_id']))
    # Mark token as used
    conn.execute("UPDATE recovery_tokens SET used = 1 WHERE id = ?", (token_row['id'],))
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Contraseña restablecida correctamente."})


# --- RESOURCE API ROUTES ---

@app.route('/api/recursos', methods=['GET'])
def get_recursos():
    conn = get_db_connection()
    
    # 1. Fetch Entidades
    entities = conn.execute("SELECT * FROM entidades").fetchall()
    
    # 2. Fetch Servicios
    services = conn.execute("SELECT * FROM servicios").fetchall()
    
    # 3. Fetch Documentacion
    docs = conn.execute("SELECT * FROM documentacion").fetchall()
    
    # 4. Fetch basic services (CEAS)
    basic_services = conn.execute("SELECT * FROM servicios_basicos").fetchall()
    
    conn.close()
    
    # Process and link
    docs_by_service = {}
    for d in docs:
        s_id = d['servicio_id']
        docs_by_service.setdefault(s_id, []).append(d['nombre_documento'])
        
    services_list = []
    for s in services:
        s_dict = dict(s)
        s_dict['documentacion'] = docs_by_service.get(s['id'], [])
        services_list.append(s_dict)
        
    # Group services under their entities
    services_by_entity = {}
    for s in services_list:
        services_by_entity.setdefault(s['entidad_id'], []).append(s)
        
    entities_list = []
    for e in entities:
        e_dict = dict(e)
        e_dict['servicios'] = services_by_entity.get(e['id'], [])
        entities_list.append(e_dict)
        
    basic_list = [dict(b) for b in basic_services]
    
    # Pre-calculated filters from database values
    areas = sorted(list(set(e['area'] for e in entities_list if e['area'])))
    collectives = sorted(list(set(e['colectivo'] for e in entities_list if e['colectivo'])))
    service_types = sorted(list(set(s['tipo_servicio'] for s in services_list if s['tipo_servicio'])))
    titularities = sorted(list(set(e['titularidad'] for e in entities_list if e['titularidad'])))
    
    return jsonify({
        "entidades": entities_list,
        "servicios_basicos": basic_list,
        "filters": {
            "areas": areas,
            "collectives": collectives,
            "service_types": service_types,
            "titularities": titularities
        }
    })


@app.route('/api/entidades', methods=['POST'])
@login_required
def create_entidad():
    data = request.json or {}
    nombre = data.get('nombre')
    if not nombre:
        return jsonify({"error": "El nombre es obligatorio"}), 400
        
    direccion = data.get('direccion')
    cp = data.get('cp')
    localidad = data.get('localidad', 'LEÓN')
    
    # Read custom coordinates if provided, otherwise geocode
    lat = data.get('latitude')
    lon = data.get('longitude')
    
    use_manual_coords = False
    if lat is not None and lon is not None and str(lat).strip() != '' and str(lon).strip() != '':
        try:
            lat = float(lat)
            lon = float(lon)
            use_manual_coords = True
        except ValueError:
            pass
            
    if not use_manual_coords:
        cache = GeocodingCache(CACHE_PATH)
        lat, lon = get_coordinates(geolocator, direccion, cp, localidad, cache)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO entidades 
    (nombre, tipo_entidad, direccion, cp, localidad, titularidad, telefono, telefono2, fax, email, web, ceas, area, colectivo, latitude, longitude)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        nombre,
        data.get('tipo_entidad'),
        direccion,
        cp,
        localidad,
        data.get('titularidad'),
        data.get('telefono'),
        data.get('telefono2'),
        data.get('fax'),
        data.get('email'),
        data.get('web'),
        data.get('ceas'),
        data.get('area', 'Sin Especificar'),
        data.get('colectivo', 'Sin Especificar'),
        lat, lon
    ))
    new_id = cursor.lastrowid
    conn.commit()
    
    # Fetch inserted
    inserted = conn.execute("SELECT * FROM entidades WHERE id = ?", (new_id,)).fetchone()
    conn.close()
    
    return jsonify(dict(inserted)), 201


@app.route('/api/entidades/<int:ent_id>', methods=['PUT'])
@login_required
def update_entidad(ent_id):
    data = request.json or {}
    conn = get_db_connection()
    
    # Check if exists
    entity = conn.execute("SELECT * FROM entidades WHERE id = ?", (ent_id,)).fetchone()
    if not entity:
        conn.close()
        return jsonify({"error": "Entidad no encontrada"}), 404
        
    direccion = data.get('direccion', entity['direccion'])
    cp = data.get('cp', entity['cp'])
    localidad = data.get('localidad', entity['localidad'])
    
    # Re-geocode or use manual coords
    lat = data.get('latitude')
    lon = data.get('longitude')
    
    use_manual_coords = False
    if lat is not None and lon is not None and str(lat).strip() != '' and str(lon).strip() != '':
        try:
            lat = float(lat)
            lon = float(lon)
            use_manual_coords = True
        except ValueError:
            pass
            
    if not use_manual_coords:
        # Re-geocode if address/zip/locality changed
        lat, lon = entity['latitude'], entity['longitude']
        if (direccion != entity['direccion'] or cp != entity['cp'] or localidad != entity['localidad']):
            cache = GeocodingCache(CACHE_PATH)
            lat, lon = get_coordinates(geolocator, direccion, cp, localidad, cache)
        
    conn.execute("""
    UPDATE entidades SET
        nombre = ?, tipo_entidad = ?, direccion = ?, cp = ?, localidad = ?, titularidad = ?, 
        telefono = ?, telefono2 = ?, fax = ?, email = ?, web = ?, ceas = ?, area = ?, colectivo = ?, 
        latitude = ?, longitude = ?
    WHERE id = ?
    """, (
        data.get('nombre', entity['nombre']),
        data.get('tipo_entidad', entity['tipo_entidad']),
        direccion,
        cp,
        localidad,
        data.get('titularidad', entity['titularidad']),
        data.get('telefono', entity['telefono']),
        data.get('telefono2', entity['telefono2']),
        data.get('fax', entity['fax']),
        data.get('email', entity['email']),
        data.get('web', entity['web']),
        data.get('ceas', entity['ceas']),
        data.get('area', entity['area']),
        data.get('colectivo', entity['colectivo']),
        lat, lon, ent_id
    ))
    conn.commit()
    
    updated = conn.execute("SELECT * FROM entidades WHERE id = ?", (ent_id,)).fetchone()
    conn.close()
    
    return jsonify(dict(updated))


@app.route('/api/entidades/<int:ent_id>', methods=['DELETE'])
@login_required
def delete_entidad(ent_id):
    conn = get_db_connection()
    entity = conn.execute("SELECT * FROM entidades WHERE id = ?", (ent_id,)).fetchone()
    if not entity:
        conn.close()
        return jsonify({"error": "Entidad no encontrada"}), 404
        
    conn.execute("DELETE FROM entidades WHERE id = ?", (ent_id,))
    # SQLite schema foreign keys CASCADE deletes services and docs
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Entidad eliminada correctamente."})


@app.route('/api/servicios', methods=['POST'])
@login_required
def create_servicio():
    data = request.json or {}
    entidad_id = data.get('entidad_id')
    nombre = data.get('nombre')
    
    if not entidad_id or not nombre:
        return jsonify({"error": "El nombre y el ID de la entidad son obligatorios"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if entity exists
    entity = conn.execute("SELECT id FROM entidades WHERE id = ?", (entidad_id,)).fetchone()
    if not entity:
        conn.close()
        return jsonify({"error": "Entidad no encontrada"}), 404
        
    cursor.execute("""
    INSERT INTO servicios
    (entidad_id, nombre, tipo_servicio, tipo_registro, descripcion_corta, descripcion_larga, plazas, cita_previa, horario, condiciones_admision, aportacion_beneficiario, direccion, finalidad)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        entidad_id,
        nombre,
        data.get('tipo_servicio', 'Sin Especificar'),
        data.get('tipo_registro', 'servicio'),
        data.get('descripcion_corta'),
        data.get('descripcion_larga'),
        data.get('plazas'),
        data.get('cita_previa'),
        data.get('horario'),
        data.get('condiciones_admision'),
        data.get('aportacion_beneficiario'),
        data.get('direccion'),
        data.get('finalidad')
    ))
    new_id = cursor.lastrowid
    
    # Process required documentation
    docs = data.get('documentacion', [])
    for doc in docs:
        if str(doc).strip():
            cursor.execute("INSERT INTO documentacion (servicio_id, nombre_documento) VALUES (?, ?)", (new_id, str(doc).strip()))
            
    conn.commit()
    
    # Fetch inserted
    inserted = conn.execute("SELECT * FROM servicios WHERE id = ?", (new_id,)).fetchone()
    inserted_dict = dict(inserted)
    inserted_dict['documentacion'] = docs
    
    conn.close()
    return jsonify(inserted_dict), 201


@app.route('/api/servicios/<int:serv_id>', methods=['PUT'])
@login_required
def update_servicio(serv_id):
    data = request.json or {}
    conn = get_db_connection()
    
    service = conn.execute("SELECT * FROM servicios WHERE id = ?", (serv_id,)).fetchone()
    if not service:
        conn.close()
        return jsonify({"error": "Servicio no encontrado"}), 404
        
    conn.execute("""
    UPDATE servicios SET
        nombre = ?, tipo_servicio = ?, tipo_registro = ?, descripcion_corta = ?, 
        descripcion_larga = ?, plazas = ?, cita_previa = ?, horario = ?, 
        condiciones_admision = ?, aportacion_beneficiario = ?, direccion = ?, finalidad = ?
    WHERE id = ?
    """, (
        data.get('nombre', service['nombre']),
        data.get('tipo_servicio', service['tipo_servicio']),
        data.get('tipo_registro', service['tipo_registro']),
        data.get('descripcion_corta', service['descripcion_corta']),
        data.get('descripcion_larga', service['descripcion_larga']),
        data.get('plazas', service['plazas']),
        data.get('cita_previa', service['cita_previa']),
        data.get('horario', service['horario']),
        data.get('condiciones_admision', service['condiciones_admision']),
        data.get('aportacion_beneficiario', service['aportacion_beneficiario']),
        data.get('direccion', service['direccion']),
        data.get('finalidad', service['finalidad']),
        serv_id
    ))
    
    # Update documents if provided
    if 'documentacion' in data:
        conn.execute("DELETE FROM documentacion WHERE servicio_id = ?", (serv_id,))
        for doc in data['documentacion']:
            if str(doc).strip():
                conn.execute("INSERT INTO documentacion (servicio_id, nombre_documento) VALUES (?, ?)", (serv_id, str(doc).strip()))
                
    conn.commit()
    
    # Fetch updated
    updated = conn.execute("SELECT * FROM servicios WHERE id = ?", (serv_id,)).fetchone()
    updated_dict = dict(updated)
    
    updated_docs = conn.execute("SELECT nombre_documento FROM documentacion WHERE servicio_id = ?", (serv_id,)).fetchall()
    updated_dict['documentacion'] = [d['nombre_documento'] for d in updated_docs]
    
    conn.close()
    return jsonify(updated_dict)


@app.route('/api/servicios/<int:serv_id>', methods=['DELETE'])
@login_required
def delete_servicio(serv_id):
    conn = get_db_connection()
    service = conn.execute("SELECT * FROM servicios WHERE id = ?", (serv_id,)).fetchone()
    if not service:
        conn.close()
        return jsonify({"error": "Servicio no encontrado"}), 404
        
    conn.execute("DELETE FROM servicios WHERE id = ?", (serv_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Servicio eliminado correctamente."})


# --- ADMIN USER ROUTING ---

@app.route('/api/users', methods=['GET'])
@login_required
def list_users():
    conn = get_db_connection()
    users = conn.execute("SELECT id, username, email, created_at FROM users").fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])


@app.route('/api/users', methods=['POST'])
@login_required
def create_user():
    data = request.json or {}
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    
    if not username or not email or not password:
        return jsonify({"error": "Faltan campos obligatorios"}), 400
        
    hashed = generate_password_hash(password)
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, hashed)
        )
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return jsonify({
            "id": new_id,
            "username": username,
            "email": email
        }), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "El nombre de usuario o correo electrónico ya existe."}), 400


@app.route('/api/users/<int:u_id>', methods=['DELETE'])
@login_required
def delete_user(u_id):
    if u_id == session['user_id']:
        return jsonify({"error": "No puede eliminarse a sí mismo."}), 400
        
    conn = get_db_connection()
    user = conn.execute("SELECT id FROM users WHERE id = ?", (u_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "Usuario no encontrado"}), 404
        
    conn.execute("DELETE FROM users WHERE id = ?", (u_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Usuario administrador eliminado."})


@app.route('/api/users/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.json or {}
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    
    if not old_password or not new_password:
        return jsonify({"error": "Faltan campos"}), 400
        
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    
    if not check_password_hash(user['password_hash'], old_password):
        conn.close()
        return jsonify({"error": "Contraseña actual incorrecta."}), 400
        
    hashed = generate_password_hash(new_password)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hashed, session['user_id']))
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Contraseña actualizada con éxito."})


# --- DEVELOPMENT ONLY STATIC FILE ROUTING ---
# In production, Nginx serves static files directly!
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_static(path):
    if not path:
        path = 'index.html'
    
    static_dir = os.path.join(WORKSPACE_DIR, 'app', 'static')
    if os.path.exists(os.path.join(static_dir, path)):
        return send_from_directory(static_dir, path)
    
    # Fallback to index if path has no dot (SPA style redirect)
    if '.' not in path:
        return send_from_directory(static_dir, 'index.html')
        
    return "File not found", 404


if __name__ == '__main__':
    # Local dev server runs on port 8000
    app.run(host='0.0.0.0', port=8000, debug=True)
