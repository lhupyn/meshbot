# bot_commands.py

# -*- coding: utf-8 -*-
"""
Módulo de Comandos para MeshBot.
"""
import requests
import config
import database
import math
from datetime import datetime

# --- Funciones de Ayuda ---

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_weather_from_api(url):
    """Función interna para procesar la llamada a la API de OpenWeatherMap."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if str(data.get("cod")) != "200":
             return f"Error: {data.get('message', 'ubicación no encontrada')}"
        
        city_name = data.get('name', 'Ubicación desconocida')
        desc = data['weather'][0]['description'].capitalize()
        temp = data['main']['temp']
        sensacion = data['main']['feels_like']
        viento = data['wind']['speed'] * 3.6
        return f"{city_name}: {desc}, {temp:.0f}C (sens. {sensacion:.0f}C). Viento {viento:.0f}km/h."
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401: return "Error: Clave de API del tiempo no válida."
        if e.response.status_code == 404: return "No encontré la ubicación."
        return "Error consultando el tiempo."
    except Exception as e:
        print(f"Error en get_weather_from_api: {e}")
        return "No pude obtener el tiempo en este momento."

def format_time_ago(dt_str):
    if not dt_str: return "Nunca"
    now = datetime.now()
    try:
        try:
            dt_obj = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            dt_obj = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return "Fecha inv."

    diff = now - dt_obj
    
    seconds = diff.total_seconds()
    if seconds < 60: return f"hace {int(seconds)}s"
    minutes = seconds / 60
    if minutes < 60: return f"hace {int(minutes)}m"
    hours = minutes / 60
    if hours < 24: return f"hace {int(hours)}h"
    days = hours / 24
    return f"hace {int(days)}d"

# --- Lógica Central y Definiciones de Comandos ---

def get_weather_data(lat=None, lon=None, city=None):
    if not config.WEATHER_API_KEY or config.WEATHER_API_KEY in ['PON_TU_CLAVE_DE_API_AQUI', '']:
        return "Error: La función de tiempo no está configurada por el administrador."

    base_url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        "appid": config.WEATHER_API_KEY,
        "units": "metric",
        "lang": "es"
    }
    if lat is not None and lon is not None:
        params['lat'] = lat
        params['lon'] = lon
    elif city:
        params['q'] = city
    else:
        return "Se necesita una ubicación (coordenadas o ciudad) para obtener el tiempo."
    
    full_url = f"{base_url}?{requests.compat.urlencode(params)}"
    return get_weather_from_api(full_url)

def get_current_time():
    """Función para que la IA obtenga la hora y fecha actual."""
    now = datetime.now()
    return now.strftime('%H:%M:%S del %d/%m/%Y')

def get_node_info_for_ai(node_identifier):
    """
    Busca un nodo por su nombre (@nombre) o ID (!hexid) y devuelve su información.
    Esta función está diseñada para ser llamada por la IA.
    """
    node = None
    identifier_str = str(node_identifier).strip()

    if identifier_str.startswith('@'):
        node = database.get_node_by_name(identifier_str[1:])
    elif identifier_str.startswith('!'):
        try:
            node_id_int = int(identifier_str[1:], 16)
            node = database.get_node_by_id(node_id_int)
        except (ValueError, TypeError):
            return f"El ID '{identifier_str}' no es válido."
    else:
        node = database.get_node_by_name(identifier_str)

    if not node:
        return f"No encontré información para el nodo '{identifier_str}'."

    node_id_hex = f"!{node['node_id']:08x}"
    response_parts = [f"Datos para {node['long_name']} ({node['short_name']}) [{node_id_hex}]:"]
    response_parts.append(f"Visto por última vez: {format_time_ago(node['last_seen'])}.")
    
    if node['latitude'] is not None:
        location_str = f"Ubicación: {node['latitude']:.4f}, {node['longitude']:.4f}"
        if node['altitude'] is not None and node['altitude'] != 0:
            location_str += f", Altitud: {node['altitude']}m"
        location_str += "."
        response_parts.append(location_str)
    
    telemetry_info = []
    if node['battery_level'] is not None:
        telemetry_info.append(f"{node['battery_level']}% de batería")
    if node['voltage'] is not None:
        telemetry_info.append(f"{node['voltage']:.2f}V")
    if node['air_temp'] is not None:
        telemetry_info.append(f"{node['air_temp']:.1f}°C")
    if node['humidity'] is not None:
        telemetry_info.append(f"{node['humidity']:.1f}% de humedad")
    # MODIFICADO: Se añade la presión barométrica
    if node['barometric_pressure'] is not None:
        telemetry_info.append(f"{node['barometric_pressure']:.1f} hPa")
        
    if telemetry_info:
        response_parts.append(f"Telemetría: {', '.join(telemetry_info)}.")
    else:
        response_parts.append("No hay datos de telemetría disponibles.")
    
    return " ".join(response_parts)

def command_ping(args, history, sender_id):
    return "Pong!"

def command_info(args, history, sender_id):
    return f"Soy {config.OUR_LONG_NAME} {config.OUR_SHORT_NAME}, un asistente virtual para el canal '{config.SECONDARY_CHANNEL_NAME}'."

def command_ayuda(args, history, sender_id):
    available_commands = [cmd for cmd in COMMANDS.keys() if cmd != 'meshbot'] 
    return f"Comandos: {config.COMMAND_PREFIX}" + f", {config.COMMAND_PREFIX}".join(available_commands)

def command_tiempo(args, history, sender_id):
    if not args:
        user_node = database.get_node_by_id(sender_id)
        if user_node and user_node['latitude']:
            return get_weather_data(lat=user_node['latitude'], lon=user_node['longitude'])
        else:
            return "No sé tu ubicación. Compártela o dime una ciudad. Ej: !tiempo Madrid"

    if args[0].startswith('@'):
        node_name = args[0][1:]
        target_node = database.get_node_by_name(node_name)
        if target_node and target_node['latitude']:
            return get_weather_data(lat=target_node['latitude'], lon=target_node['longitude'])
        else:
            return f"No conozco la ubicación de '{node_name}'."
    else:
        ciudad = " ".join(args)
        return get_weather_data(city=ciudad)

def command_hora(args, history, sender_id):
    """Devuelve la hora actual del servidor."""
    now = datetime.now()
    return f"La hora actual es: {now.strftime('%H:%M:%S')}"

def command_reset(args, history, sender_id):
    if sender_id in history:
        del history[sender_id]
        return "Tu historial de conversación con la IA ha sido borrado."
    return "No tenías un historial de conversación para borrar."

def command_meshbot(args, history, sender_id):
    return (
        f"Soy {config.OUR_LONG_NAME} {config.OUR_SHORT_NAME}, el asistente del canal. "
        "¿En qué puedo ayudarte?"
    )

def command_nodo(args, history, sender_id):
    """Muestra información detallada de un nodo, incluyendo telemetría."""
    if not args:
        return "Por favor, especifica un nombre de nodo. Ej: !nodo @MiNodo"
    
    node_name = args[0]
    if node_name.startswith('@'):
        node_name = node_name[1:]
    
    node = database.get_node_by_name(node_name)
    if not node:
        return f"No encontré ningún nodo con el nombre '{node_name}'."

    node_id_hex = f"!{node['node_id']:08x}"
    response = f"Info de {node['long_name']} ({node['short_name']}) [{node_id_hex}]:\n"
    response += f"Visto: {format_time_ago(node['last_seen'])}\n"
    
    if node['latitude'] is not None:
        response += f"Pos: {node['latitude']:.4f}, {node['longitude']:.4f}"
        if node['altitude'] is not None and node['altitude'] != 0:
            response += f", {node['altitude']}m"
        response += "\n"
    
    telemetry_parts = []
    if node['battery_level'] is not None:
        telemetry_parts.append(f"Bat: {node['battery_level']}%")
    if node['voltage'] is not None:
        telemetry_parts.append(f"V: {node['voltage']:.2f}V")
    if node['air_temp'] is not None:
        telemetry_parts.append(f"T: {node['air_temp']:.1f}°C")
    if node['humidity'] is not None:
        telemetry_parts.append(f"H: {node['humidity']:.1f}%")
    # MODIFICADO: Se añade la presión barométrica
    if node['barometric_pressure'] is not None:
        telemetry_parts.append(f"P: {node['barometric_pressure']:.1f}hPa")
        
    if telemetry_parts:
        response += ", ".join(telemetry_parts)
    
    return response.strip()


# --- Diccionario de Comandos ---
COMMANDS = {
    'ping': {'function': command_ping, 'description': 'Comprueba si el bot está online.'},
    'info': {'function': command_info, 'description': 'Muestra información sobre este bot.'},
    'ayuda': {'function': command_ayuda, 'description': 'Muestra esta lista de comandos.'},
    'tiempo': {'function': command_tiempo, 'description': 'Muestra el tiempo para tu ubicación, un nodo o una ciudad.'},
    'hora': {'function': command_hora, 'description': 'Muestra la hora actual del servidor.'},
    'reset': {'function': command_reset, 'description': 'Borra tu historial de conversación con la IA.'},
    'nodo': {'function': command_nodo, 'description': 'Muestra info detallada de un nodo. Ej: !nodo @MiNodo'},
    'meshbot': {'function': command_meshbot, 'description': 'Muestra información sobre cómo usar el bot de IA.'}
}

# --- Manejador Principal de Comandos ---
def handle_command(full_command_text, history, sender_id):
    command_text = full_command_text[len(config.COMMAND_PREFIX):]
    parts = command_text.split()
    command = parts[0].lower()
    args = parts[1:]
    
    if command in COMMANDS:
        return COMMANDS[command]['function'](args, history, sender_id)
    else:
        return f"Comando '{command}' desconocido. Usa {config.COMMAND_PREFIX}ayuda."
