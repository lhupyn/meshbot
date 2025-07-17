# -*- coding: utf-8 -*-
"""
Archivo de Configuración de Ejemplo para MeshBot.

Instrucciones:
1. Renombra este archivo a "config.py".
2. Edita los valores de las variables para que se ajusten a tu configuración.
   (Especialmente las claves de API y los datos de tu red Meshtastic).
"""

import os

# --- CONFIGURACIÓN DE LA BASE DE DATOS ---
# Nombre del archivo de la base de datos SQLite.
DATABASE_FILE = os.getenv('DATABASE_FILE', 'meshbot.db')
# (Avanzado) Horas para considerar un nodo en la lista de nodos.
NODE_LIST_HOURS = int(os.getenv('NODE_LIST_HOURS', 24))
# Días de inactividad tras los cuales un nodo se elimina de la base de datos.
NODE_DB_CLEANUP_DAYS = int(os.getenv('NODE_DB_CLEANUP_DAYS', 30))


# --- CONFIGURACIÓN DE ANUNCIOS (BROADCAST) ---
# Habilita (True) o deshabilita (False) los mensajes periódicos en el canal de interacción.
BROADCAST_ENABLED = os.getenv('BROADCAST_ENABLED', 'False').lower() in ('true', '1', 'yes')
# Intervalo en minutos para los anuncios.
BROADCAST_INTERVAL_MINUTES = int(os.getenv('BROADCAST_INTERVAL_MINUTES', 60))
# Mensaje que se enviará en el anuncio.
BROADCAST_MESSAGE = os.getenv('BROADCAST_MESSAGE', '¿Necesitas ayuda o tienes una consulta? Escribe @meshbot seguido de tu pregunta en este canal. 🤖')


# --- CONFIGURACIÓN DE PRESENCIA (NODEINFO) ---
# Habilita (True) o deshabilita (False) que el bot anuncie su presencia en la red.
PRESENCE_ENABLED = os.getenv('PRESENCE_ENABLED', 'True').lower() in ('true', '1', 'yes')
# Intervalo en minutos para anunciar la presencia.
PRESENCE_INTERVAL_MINUTES = int(os.getenv('PRESENCE_INTERVAL_MINUTES', 720))


# --- CONFIGURACIÓN GEOGRÁFICA ---
# Habilita (True) o deshabilita (False) que el bot anuncie su posición.
POSITION_ENABLED = os.getenv('POSITION_ENABLED', 'True').lower() in ('true', '1', 'yes')
# Coordenadas del bot (si POSITION_ENABLED es True).
BOT_LATITUDE = float(os.getenv('BOT_LATITUDE', 0.0))
BOT_LONGITUDE = float(os.getenv('BOT_LONGITUDE', 0.0))
BOT_ALTITUDE = int(os.getenv('BOT_ALTITUDE', 0))


# --- CONFIGURACIÓN MQTT ---
# Dirección de tu bróker MQTT.
MQTT_BROKER = os.getenv('MQTT_BROKER', 'mqtt.meshtastic.org')
# Puerto del bróker MQTT (1883 para no cifrado, 8883 para TLS).
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
# Credenciales de acceso al bróker MQTT.
MQTT_USERNAME = os.getenv('MQTT_USERNAME', 'meshdev')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', 'large4cats')


# --- CONFIGURACIÓN DEL CANAL MESHTASTIC ---
# El Root Topic de tu región Meshtastic.
ROOT_TOPIC = os.getenv('ROOT_TOPIC', 'msh/EU_868')

# --- CANAL PRIMARIO (Para presencia del bot y telemetría) ---
PRIMARY_CHANNEL_NAME = os.getenv('PRIMARY_CHANNEL_NAME', 'LongFast')
# Clave PSK del canal primario en formato Base64. "AQ==" es la clave por defecto.
PRIMARY_CHANNEL_KEY_B64 = os.getenv('PRIMARY_CHANNEL_KEY', 'AQ==')

# --- CANAL SECUNDARIO (Para interacción con usuarios) ---
SECONDARY_CHANNEL_ENABLED = os.getenv('SECONDARY_CHANNEL_ENABLED', 'True').lower() in ('true', '1', 'yes')
SECONDARY_CHANNEL_NAME = os.getenv('SECONDARY_CHANNEL_NAME', 'Iberia')
# Clave PSK del canal secundario en formato Base64.
SECONDARY_CHANNEL_KEY_B64 = os.getenv('SECONDARY_CHANNEL_KEY', 'AQ==')


# --- IDENTIDAD DEL BOT ---
# ¡IMPORTANTE! Elige un número de nodo único para tu bot.
# Puedes generar uno aleatorio si no tienes uno asignado.
OUR_NODE_NUMBER = int(os.getenv('OUR_NODE_NUMBER', 0xDEADBEEF))
# Nombre largo que mostrará el bot en la red.
OUR_LONG_NAME = os.getenv('OUR_LONG_NAME', 'MeshBot')
# Nombre corto o icono del bot.
OUR_SHORT_NAME = os.getenv('OUR_SHORT_NAME', '🤖')


# --- CONFIGURACIÓN DE COMANDOS ---
# Prefijo para los comandos (ej. !ping).
COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '!')
# Tiempo de espera en minutos antes de volver a invitar a un usuario a un DM.
INVITATION_COOLDOWN_MINUTES = int(os.getenv('INVITATION_COOLDOWN_MINUTES', 30))


# --- CONFIGURACIÓN DE IA Y APIS EXTERNAS ---
# ¡IMPORTANTE! Introduce aquí tus claves de API.
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'PON_TU_CLAVE_DE_GEMINI_AQUI')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY', 'PON_TU_CLAVE_DE_OPENWEATHERMAP_AQUI')
