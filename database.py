# -*- coding: utf-8 -*-
"""
Módulo de Base de Datos para MeshBot.

Gestiona la base de datos SQLite para la persistencia de datos,
como los IDs de los mensajes ya procesados y la información de los nodos de la red.
"""

import sqlite3
import config
from datetime import datetime, timedelta

def get_db_connection():
    """Crea y devuelve una conexión a la base de datos."""
    conn = sqlite3.connect(config.DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Inicializa la base de datos. Crea las tablas si no existen.
    """
    conn = get_db_connection()
    try:
        # MODIFICADO: Añadimos campo para la presión barométrica
        conn.execute('''
            CREATE TABLE IF NOT EXISTS nodes (
                node_id INTEGER PRIMARY KEY,
                long_name TEXT,
                short_name TEXT,
                latitude REAL,
                longitude REAL,
                altitude INTEGER,
                battery_level REAL,
                voltage REAL,
                air_temp REAL,
                humidity REAL,
                barometric_pressure REAL,
                last_seen DATETIME NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS processed_messages (
                id INTEGER PRIMARY KEY,
                message_uid INTEGER NOT NULL UNIQUE,
                timestamp DATETIME NOT NULL
            )
        ''')
        conn.commit()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [  INFO   ] Base de datos '{config.DATABASE_FILE}' inicializada correctamente.")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [  ERROR  ] Error inicializando la base de datos: {e}")
    finally:
        conn.close()

def update_node(node_id, long_name=None, short_name=None, lat=None, lon=None, alt=None):
    """
    Añade o actualiza la información de un nodo en la base de datos.
    """
    conn = get_db_connection()
    try:
        now = datetime.now()
        conn.execute(
            "INSERT OR IGNORE INTO nodes (node_id, last_seen) VALUES (?, ?)",
            (node_id, now)
        )
        conn.execute("UPDATE nodes SET last_seen = ? WHERE node_id = ?", (now, node_id))

        if long_name is not None and short_name is not None:
            conn.execute(
                "UPDATE nodes SET long_name = ?, short_name = ? WHERE node_id = ?",
                (long_name, short_name, node_id)
            )
        
        if lat is not None and lon is not None:
            conn.execute(
                "UPDATE nodes SET latitude = ?, longitude = ?, altitude = ? WHERE node_id = ?",
                (lat, lon, alt, node_id)
            )
        
        conn.commit()
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [  ERROR  ] Error actualizando nodo en la BD: {e}")
    finally:
        conn.close()

# MODIFICADO: Se añade el parámetro para la presión barométrica
def update_node_telemetry(node_id, battery_level=None, voltage=None, air_temp=None, humidity=None, barometric_pressure=None):
    """
    Actualiza los datos de telemetría de un nodo existente.
    """
    conn = get_db_connection()
    try:
        now = datetime.now()
        conn.execute(
            "INSERT OR IGNORE INTO nodes (node_id, last_seen) VALUES (?, ?)",
            (node_id, now)
        )
        
        fields_to_update = []
        params = []
        
        if battery_level is not None:
            fields_to_update.append("battery_level = ?")
            params.append(battery_level)
        if voltage is not None:
            fields_to_update.append("voltage = ?")
            params.append(voltage)
        if air_temp is not None:
            fields_to_update.append("air_temp = ?")
            params.append(air_temp)
        if humidity is not None:
            fields_to_update.append("humidity = ?")
            params.append(humidity)
        if barometric_pressure is not None:
            fields_to_update.append("barometric_pressure = ?")
            params.append(barometric_pressure)

        if fields_to_update:
            fields_to_update.append("last_seen = ?")
            params.append(now)
            
            query = f"UPDATE nodes SET {', '.join(fields_to_update)} WHERE node_id = ?"
            params.append(node_id)
            
            conn.execute(query, tuple(params))
            conn.commit()

    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [  ERROR  ] Error actualizando telemetría del nodo: {e}")
    finally:
        conn.close()


def get_node_by_name(name):
    """
    Busca un nodo en la base de datos por su nombre largo o corto.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM nodes WHERE long_name = ? COLLATE NOCASE OR short_name = ? COLLATE NOCASE",
            (name, name)
        )
        return cursor.fetchone()
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [  ERROR  ] Error buscando nodo por nombre: {e}")
        return None
    finally:
        conn.close()

def get_node_by_id(node_id):
    """
    Busca un nodo en la base de datos por su ID numérico.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
        return cursor.fetchone()
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [  ERROR  ] Error buscando nodo por ID: {e}")
        return None
    finally:
        conn.close()

def get_recent_nodes(hours_limit):
    """
    Devuelve una lista de nodos vistos en las últimas X horas.
    """
    conn = get_db_connection()
    try:
        time_limit = datetime.now() - timedelta(hours=hours_limit)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM nodes WHERE last_seen < ? ORDER BY last_seen DESC",
            (time_limit,)
        )
        return cursor.fetchall()
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [  ERROR  ] Error obteniendo nodos recientes: {e}")
        return []
    finally:
        conn.close()


def add_message_id(msg_uid):
    """Añade el ID de un mensaje a la base de datos."""
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO processed_messages (message_uid, timestamp) VALUES (?, ?)",
            (msg_uid, datetime.now())
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [  ERROR  ] Error añadiendo ID a la BD: {e}")
    finally:
        conn.close()

def message_id_exists(msg_uid):
    """Comprueba si un ID de mensaje ya existe en la base de datos."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM processed_messages WHERE message_uid = ?", (msg_uid,))
        return cursor.fetchone() is not None
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [  ERROR  ] Error consultando ID en la BD: {e}")
        return False
    finally:
        conn.close()

def cleanup_old_messages():
    """Elimina registros de mensajes de más de 7 días para mantener la BD limpia."""
    conn = get_db_connection()
    try:
        seven_days_ago = datetime.now() - timedelta(days=7)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM processed_messages WHERE timestamp < ?", (seven_days_ago,))
        conn.commit()
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [  ERROR  ] Error limpiando la BD de mensajes: {e}")
    finally:
        conn.close()

def cleanup_old_nodes(days_limit):
    """
    NUEVA FUNCIÓN: Elimina nodos inactivos de la base de datos.
    """
    conn = get_db_connection()
    try:
        time_limit = datetime.now() - timedelta(days=days_limit)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM nodes WHERE last_seen < ?", (time_limit,))
        conn.commit()
        if cursor.rowcount > 0:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [  INFO   ] Limpiados {cursor.rowcount} nodos inactivos de la base de datos.")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [  ERROR  ] Error limpiando la BD de nodos: {e}")
    finally:
        conn.close()
