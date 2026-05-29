import os
import pandas as pd
import sqlite3
from werkzeug.security import generate_password_hash
from geopy.geocoders import Nominatim
import sys

# Add scripts directory to path to import geocode_utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from geocode_utils import GeocodingCache, get_coordinates

workspace_dir = r"g:\Mi unidad\Antigravity_fpl\EUTS_Recursos_Leon"
db_path = os.path.join(workspace_dir, "data", "app.db")
cache_path = os.path.join(workspace_dir, "data", "geocoding_cache.json")

# Ensure data directory exists
os.makedirs(os.path.dirname(db_path), exist_ok=True)

def create_schema(conn):
    cursor = conn.cursor()
    
    # 1. Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 2. Password Recovery Tokens Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recovery_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token TEXT NOT NULL UNIQUE,
        expires_at DATETIME NOT NULL,
        used BOOLEAN DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)
    
    # 3. Entidades Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS entidades (
        id INTEGER PRIMARY KEY,
        nombre TEXT NOT NULL,
        tipo_entidad TEXT,
        direccion TEXT,
        cp TEXT,
        localidad TEXT,
        titularidad TEXT,
        telefono TEXT,
        telefono2 TEXT,
        fax TEXT,
        email TEXT,
        web TEXT,
        ceas TEXT,
        area TEXT,
        colectivo TEXT,
        latitude REAL,
        longitude REAL
    )
    """)
    
    # 4. Servicios Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS servicios (
        id INTEGER PRIMARY KEY,
        entidad_id INTEGER NOT NULL,
        nombre TEXT NOT NULL,
        tipo_servicio TEXT,
        tipo_registro TEXT,
        descripcion_corta TEXT,
        descripcion_larga TEXT,
        plazas TEXT,
        cita_previa TEXT,
        horario TEXT,
        condiciones_admision TEXT,
        aportacion_beneficiario TEXT,
        direccion TEXT,
        finalidad TEXT,
        FOREIGN KEY (entidad_id) REFERENCES entidades (id) ON DELETE CASCADE
    )
    """)
    
    # 5. Documentacion Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documentacion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        servicio_id INTEGER NOT NULL,
        nombre_documento TEXT NOT NULL,
        FOREIGN KEY (servicio_id) REFERENCES servicios (id) ON DELETE CASCADE
    )
    """)
    
    # 6. Servicios Basicos Table (CEAS / Centros de Salud)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS servicios_basicos (
        id INTEGER PRIMARY KEY,
        tipo TEXT,
        nombre TEXT NOT NULL,
        direccion TEXT,
        cp TEXT,
        ciudad TEXT,
        telefono TEXT,
        email TEXT,
        telefono2 TEXT,
        telefono3 TEXT,
        telefono4 TEXT,
        latitude REAL,
        longitude REAL
    )
    """)
    
    conn.commit()
    print("SQLite schema created successfully.")


def clean_str(val):
    if pd.isna(val):
        return None
    val_str = str(val).strip()
    # Normalize some known broken spellings or replace them
    # Accents are preserved in openpyxl, but let's make sure we clean whitespace.
    return val_str if val_str else None


def clean_cp(val):
    if pd.isna(val):
        return None
    try:
        # Convert e.g. 24005.0 -> 24005
        return f"{int(float(val)):05d}"
    except (ValueError, TypeError):
        return str(val).strip()


def normalize_area(area):
    area = clean_str(area)
    if not area:
        return "Sin Especificar"
    area_map = {
        'Servicios_Sociales': 'Servicios Sociales',
        'Tercer_Sector': 'Tercer Sector',
        'Educacion': 'Educación',
        'Empleo': 'Empleo',
        'Sin_Especificar': 'Sin Especificar',
        'Ocio_Cultura': 'Ocio y Cultura',
        'Sanidad': 'Sanidad',
        'Vivienda': 'Vivienda'
    }
    return area_map.get(area, area)


def normalize_colectivo(colec):
    colec = clean_str(colec)
    if not colec:
        return "Sin Especificar"
    colec_map = {
        'Tercera_Edad': 'Tercera Edad',
        'Inmigrantes': 'Inmigrantes',
        'Toxicomanías - Ludopatias': 'Toxicomanías y Ludopatías',
        'Toxicomanías - Ludopatías': 'Toxicomanías y Ludopatías',
        'Toxicomanas - Ludopatias': 'Toxicomanías y Ludopatías',
        'Sin_Especificar': 'Sin Especificar',
        'Infancia_Familia': 'Infancia y Familia',
        'Mujer': 'Mujer',
        'Personas_con_Discapacidad': 'Personas con Discapacidad',
        'Minorias_etnicas': 'Minorías Étnicas',
        'Juventud': 'Juventud',
        'Población_General': 'Población General',
        'Poblacion_General': 'Población General',
        'Reclusos': 'Reclusos',
        'Pobreza_Marginacion': 'Pobreza y Marginación',
        'Voluntariado': 'Voluntariado'
    }
    return colec_map.get(colec, colec)


def normalize_tipo_servicio(tipo):
    tipo = clean_str(tipo)
    if not tipo:
        return "Sin Especificar"
    tipo_map = {
        'Centros_de_día/Hogares': 'Centros de Día / Hogares',
        'Centros_de_da/Hogares': 'Centros de Día / Hogares',
        'Alojamiento_Residencial': 'Alojamiento Residencial',
        'Sin_Especificar': 'Sin Especificar',
        'Información_Asesoramiento': 'Información y Asesoramiento',
        'Informacin_Asesoramiento': 'Información y Asesoramiento',
        'Casas_de_acogida': 'Casas de Acogida',
        'Formación_No_Reglada': 'Formación No Reglada',
        'Formacin_No_Reglada': 'Formación No Reglada',
        'Centros_Especiales_de_Empleo/Ocupacionales': 'Centros Especiales de Empleo / Ocupacionales',
        'Viviendas/hogares_tutelados': 'Viviendas / Hogares Tutelados',
        'Ayuda_a_domicilio': 'Ayuda a Domicilio',
        'Servicios_de_Emergencia_Social': 'Servicios de Emergencia Social',
        'Ocio/Tiempo_Libre': 'Ocio y Tiempo Libre',
        'Formación Reglada': 'Formación Reglada',
        'Formacin Reglada': 'Formación Reglada',
        'Prestaciones_Económicas': 'Prestaciones Económicas',
        'Prestaciones_Econmicas': 'Prestaciones Económicas'
    }
    return tipo_map.get(tipo, tipo)


def ingest_all():
    print(f"Connecting to database at {db_path}...")
    conn = sqlite3.connect(db_path)
    create_schema(conn)
    cursor = conn.cursor()
    
    geolocator = Nominatim(user_agent="león_social_resources_app")
    cache = GeocodingCache(cache_path)
    
    # 1. Create default admin user
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        admin_username = "admin"
        admin_email = "admin@leon.es"
        admin_pass = "admin_password_change_me"
        hashed = generate_password_hash(admin_pass)
        cursor.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (admin_username, admin_email, hashed)
        )
        print(f"Default admin user created: Username={admin_username}, Password={admin_pass}")
    
    # 2. Ingest Entidades
    print("\nProcessing entidad.xlsx...")
    entidades_file = os.path.join(workspace_dir, "entidad.xlsx")
    ent_df = pd.read_excel(entidades_file)
    
    entities_inserted = 0
    for idx, row in ent_df.iterrows():
        ent_id = int(row['idEnt'])
        nombre = clean_str(row['Nombre'])
        if not nombre:
            continue
            
        tipo_entidad = clean_str(row['TipEnt'])
        direccion = clean_str(row['Direccion'])
        cp = clean_cp(row['cp'])
        localidad = clean_str(row['Localidad'])
        titularidad = clean_str(row['Titularidad'])
        telefono = clean_str(row['tfno'])
        telefono2 = clean_str(row['tfno2'])
        fax = clean_str(row['fax'])
        email = clean_str(row['email'])
        web = clean_str(row['web'])
        ceas = clean_str(row['ceas'])
        area = normalize_area(row['area'])
        colectivo = normalize_colectivo(row['ent_colect'])
        
        # Geocode
        lat, lon = get_coordinates(geolocator, direccion, cp, localidad, cache)
        
        cursor.execute("""
        INSERT OR REPLACE INTO entidades 
        (id, nombre, tipo_entidad, direccion, cp, localidad, titularidad, telefono, telefono2, fax, email, web, ceas, area, colectivo, latitude, longitude)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ent_id, nombre, tipo_entidad, direccion, cp, localidad, titularidad, telefono, telefono2, fax, email, web, ceas, area, colectivo, lat, lon))
        entities_inserted += 1
        
    print(f"Ingested {entities_inserted} entities.")
    conn.commit()
    
    # 3. Ingest Servicios
    print("\nProcessing Servicios.xlsx...")
    servicios_file = os.path.join(workspace_dir, "Servicios.xlsx")
    serv_df = pd.read_excel(servicios_file)
    
    services_inserted = 0
    for idx, row in serv_df.iterrows():
        serv_id = int(row['idSer'])
        
        # Check if entity ID is valid and exists
        ent_id_val = row['idTEnt']
        if pd.isna(ent_id_val):
            continue
        ent_id = int(ent_id_val)
        
        nombre = clean_str(row['Serv_prest'])
        if not nombre:
            continue
            
        tipo_servicio = normalize_tipo_servicio(row['tipo'])
        tipo_registro = clean_str(row['Tip_Serv'])
        # If double-encoded or bad characters:
        if tipo_registro and 'presta' in tipo_registro.lower():
            tipo_registro = "prestación"
        else:
            tipo_registro = "servicio"
            
        desc_corta = clean_str(row['Desc_Servicio'])
        desc_larga = clean_str(row['Descrip'])
        plazas = clean_str(row['n_Plazas'])
        
        cita = clean_str(row['Cita'])
        if cita:
            cita = cita.strip().upper()
            if "SI" in cita:
                cita = "Sí"
            elif "NO" in cita:
                cita = "No"
        
        horario = clean_str(row['Horario'])
        condiciones = clean_str(row['Cond_Admision'])
        aportacion = clean_str(row['Aport_Benefic'])
        dir_serv = clean_str(row['dir_serv'])
        finalidad = clean_str(row['fin_Serv'])
        
        cursor.execute("""
        INSERT OR REPLACE INTO servicios
        (id, entidad_id, nombre, tipo_servicio, tipo_registro, descripcion_corta, descripcion_larga, plazas, cita_previa, horario, condiciones_admision, aportacion_beneficiario, direccion, finalidad)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (serv_id, ent_id, nombre, tipo_servicio, tipo_registro, desc_corta, desc_larga, plazas, cita, horario, condiciones, aportacion, dir_serv, finalidad))
        services_inserted += 1
        
    print(f"Ingested {services_inserted} services.")
    conn.commit()

    # 4. Ingest Documentacion
    print("\nProcessing Documentacion.xlsx...")
    doc_file = os.path.join(workspace_dir, "Documentacion.xlsx")
    doc_df = pd.read_excel(doc_file)
    
    docs_inserted = 0
    # Clear old documents to prevent duplicate primary keys if re-running
    cursor.execute("DELETE FROM documentacion")
    for idx, row in doc_df.iterrows():
        serv_id_val = row['IdTServ']
        if pd.isna(serv_id_val):
            continue
        serv_id = int(serv_id_val)
        
        doc_nom = clean_str(row['Nom_Doc'])
        if not doc_nom:
            continue
            
        cursor.execute("""
        INSERT INTO documentacion (servicio_id, nombre_documento)
        VALUES (?, ?)
        """, (serv_id, doc_nom))
        docs_inserted += 1
        
    print(f"Ingested {docs_inserted} required documents.")
    conn.commit()

    # 5. Ingest Servicios Basicos (CEAS / Centros de Salud)
    print("\nProcessing Serv_Basicos.xlsx...")
    basicos_file = os.path.join(workspace_dir, "Serv_Basicos.xlsx")
    basicos_df = pd.read_excel(basicos_file)
    
    basicos_inserted = 0
    for idx, row in basicos_df.iterrows():
        ceas_id = int(row['IdCEAS'])
        tipo = clean_str(row['Tipo'])
        nombre = clean_str(row['Nomb_CEAS'])
        if not nombre:
            continue
            
        direccion = clean_str(row['Direccion'])
        cp = clean_cp(row['CP'])
        ciudad = clean_str(row['Ciudad'])
        
        # Merge phone numbers
        tel1 = clean_str(row['Tfno'])
        tel2 = clean_str(row['Tfno2'])
        tel3 = clean_str(row['Tfno3'])
        tel4 = clean_str(row['Tfno4'])
        email = clean_str(row['eMail'])
        
        # Geocode basic service
        lat, lon = get_coordinates(geolocator, direccion, cp, ciudad, cache)
        
        cursor.execute("""
        INSERT OR REPLACE INTO servicios_basicos
        (id, tipo, nombre, direccion, cp, ciudad, telefono, email, telefono2, telefono3, telefono4, latitude, longitude)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ceas_id, tipo, nombre, direccion, cp, ciudad, tel1, email, tel2, tel3, tel4, lat, lon))
        basicos_inserted += 1
        
    print(f"Ingested {basicos_inserted} basic services (CEAS).")
    
    # Save cache
    cache.save()
    
    conn.commit()
    conn.close()
    print("\n=== Ingestion Completed Successfully ===")

if __name__ == "__main__":
    ingest_all()
