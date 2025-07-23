#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MeshBot: Un bot de servidor para Meshtastic.

Versión 0.0.1

===============================================================================
Este bot ha sido creado por Gemini (IA de Google), guiado y depurado por LhUpYn.
Repositorio del proyecto: https://github.com/lhupyn/meshbot
===============================================================================
"""

# --- Módulos Estándar de Python ---
import sys
import time
import random
import base64
import threading
from datetime import datetime, timedelta

# --- Dependencias de Terceros ---
try:
    import paho.mqtt.client as mqtt
    import google.generativeai as genai
    import requests
    from meshtastic import mesh_pb2, mqtt_pb2, portnums_pb2, BROADCAST_NUM, config_pb2, telemetry_pb2
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
except ImportError as e:
    print(f"Error: Faltan dependencias críticas ({e.name}). Por favor, instálalas.")
    print("Asegúrate de ejecutar: pip install paho-mqtt google-generativeai requests meshtastic cryptography")
    sys.exit(1)

# --- Módulos del Proyecto ---
try:
    import config
    import bot_commands
    import database
    from bot_commands import get_weather_data, get_current_time, get_node_info_for_ai
except ImportError as e:
    print(f"CRITICO: No se encuentra un archivo del proyecto: {e.name}.")
    sys.exit(1)


# --- Constantes y Variables Globales ---
OUR_NODE_ID_HEX = f"!{config.OUR_NODE_NUMBER:08x}"
MAX_PAYLOAD_LEN = mesh_pb2.Constants.DATA_PAYLOAD_LEN - 10 
CONVERSATION_HISTORY = {}
LAST_INVITATION_SENT = {}
PRIVATE_REQUEST_KEYWORDS = ["dm", "privado", "abreme un privado"]

# --- FUNCIONES AUXILIARES Y DE LOG ---
def log(level, message):
    """Función de logging estándar."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [{level.upper():^9}] {message}")

# --- LÓGICA DE PROTOCOLO Y CIFRADO ---

def xor_hash(data: bytes) -> int:
    result = 0
    for char in data: result ^= char
    return result

def generate_channel_hash(name: str, key_b64: str) -> int:
    try:
        if key_b64 == "AQ==": key_b64 = "1PG7OiApB1nwvP+rz05pAQ=="
        key_bytes = base64.b64decode(key_b64.encode('ascii'))
        return xor_hash(bytes(name, 'utf-8')) ^ xor_hash(key_bytes)
    except Exception as e:
        log('error', f"Error generando hash de canal para '{name}': {e}")
        return 0

def encrypt_payload(key_b64: str, packet_id: int, from_node_id: int, payload_bytes: bytes) -> bytes:
    if key_b64 == "AQ==": key_b64 = "1PG7OiApB1nwvP+rz05pAQ=="
    key_bytes = base64.b64decode(key_b64.encode('ascii'))
    nonce_packet_id = packet_id.to_bytes(8, "little")
    nonce_from_node = from_node_id.to_bytes(8, "little")
    nonce = nonce_packet_id + nonce_from_node
    cipher = Cipher(algorithms.AES(key_bytes), modes.CTR(nonce), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(payload_bytes) + encryptor.finalize()

def decrypt_payload(key_b64: str, packet_id: int, from_node_id: int, encrypted_payload: bytes) -> bytes:
    if key_b64 == "AQ==": key_b64 = "1PG7OiApB1nwvP+rz05pAQ=="
    key_bytes = base64.b64decode(key_b64.encode('ascii'))
    nonce_packet_id = packet_id.to_bytes(8, "little")
    nonce_from_node = from_node_id.to_bytes(8, "little")
    nonce = nonce_packet_id + nonce_from_node
    cipher = Cipher(algorithms.AES(key_bytes), modes.CTR(nonce), backend=default_backend())
    decryptor = cipher.decryptor()
    return decryptor.update(encrypted_payload) + decryptor.finalize()

def generate_mesh_packet(destination_id, payload_data, port_num, want_ack, channel_name, channel_key):
    mp = mesh_pb2.MeshPacket()
    setattr(mp, 'from', config.OUR_NODE_NUMBER)
    mp.to = destination_id
    mp.id = random.randint(0, 0xFFFFFFFF)
    mp.hop_limit = 3
    mp.hop_start = 3
    mp.want_ack = want_ack
    mp.channel = generate_channel_hash(channel_name, channel_key)
    data = mesh_pb2.Data()
    data.portnum = port_num
    data.payload = payload_data
    encrypted_bytes = encrypt_payload(
        channel_key,
        mp.id,
        config.OUR_NODE_NUMBER,
        data.SerializeToString()
    )
    mp.encrypted = encrypted_bytes
    return mqtt_pb2.ServiceEnvelope(packet=mp, channel_id=channel_name, gateway_id=OUR_NODE_ID_HEX)

def send_long_message(client, destination_id, text, channel_name):
    parts = []
    words = text.split()
    current_part = ""

    for word in words:
        if not current_part:
            if len(word.encode('utf-8')) > MAX_PAYLOAD_LEN:
                 parts.append(word)
                 continue
            current_part = word
        elif len((current_part + " " + word).encode('utf-8')) > MAX_PAYLOAD_LEN:
            parts.append(current_part)
            current_part = word
        else:
            current_part += " " + word
    
    if current_part:
        parts.append(current_part)

    total_parts = len(parts)
    for i, part in enumerate(parts):
        prefix = f"{i+1}/{total_parts}: " if total_parts > 1 else ""
        publish_meshtastic_message(client, destination_id, prefix + part, channel_name, is_part_of_long_message=True)
        if total_parts > 1:
            time.sleep(1.5)

def publish_meshtastic_message(client, destination_id, text_message, channel_name, is_part_of_long_message=False):
    encoded_message = text_message.encode('utf-8')
    if not is_part_of_long_message and len(encoded_message) > mesh_pb2.Constants.DATA_PAYLOAD_LEN:
         log('advertencia', "Mensaje largo detectado. Usando send_long_message para dividirlo.")
         send_long_message(client, destination_id, text_message, channel_name); return
    
    channel_key = config.PRIMARY_CHANNEL_KEY_B64
    if channel_name == config.SECONDARY_CHANNEL_NAME:
        channel_key = config.SECONDARY_CHANNEL_KEY_B64
        
    service_envelope = generate_mesh_packet(destination_id, encoded_message, portnums_pb2.TEXT_MESSAGE_APP, want_ack=True, channel_name=channel_name, channel_key=channel_key)
    if service_envelope:
        topic = f"{config.ROOT_TOPIC}/2/e/{channel_name}/{OUR_NODE_ID_HEX}"
        client.publish(topic, service_envelope.SerializeToString())
        log_dest = "BROADCAST" if destination_id == BROADCAST_NUM else f"!{destination_id:08x}"
        log('info', f"Mensaje enviado a {log_dest} en '{channel_name}': '{text_message}'")

def publish_nodeinfo(client):
    """Publishes node info to all configured channels."""
    try:
        user_payload = mesh_pb2.User(id=OUR_NODE_ID_HEX, long_name=config.OUR_LONG_NAME, short_name=config.OUR_SHORT_NAME, hw_model=255, role=config_pb2.Config.DeviceConfig.CLIENT_MUTE).SerializeToString()
        
        service_envelope_primary = generate_mesh_packet(destination_id=BROADCAST_NUM, payload_data=user_payload, port_num=portnums_pb2.NODEINFO_APP, want_ack=False, channel_name=config.PRIMARY_CHANNEL_NAME, channel_key=config.PRIMARY_CHANNEL_KEY_B64)
        if service_envelope_primary:
            topic_primary = f"{config.ROOT_TOPIC}/2/e/{config.PRIMARY_CHANNEL_NAME}/{OUR_NODE_ID_HEX}"
            client.publish(topic_primary, service_envelope_primary.SerializeToString())
            log('info', f"Anuncio de presencia (NodeInfo) enviado a BROADCAST en canal '{config.PRIMARY_CHANNEL_NAME}'")

        if config.SECONDARY_CHANNEL_ENABLED:
            service_envelope_secondary = generate_mesh_packet(destination_id=BROADCAST_NUM, payload_data=user_payload, port_num=portnums_pb2.NODEINFO_APP, want_ack=False, channel_name=config.SECONDARY_CHANNEL_NAME, channel_key=config.SECONDARY_CHANNEL_KEY_B64)
            if service_envelope_secondary:
                topic_secondary = f"{config.ROOT_TOPIC}/2/e/{config.SECONDARY_CHANNEL_NAME}/{OUR_NODE_ID_HEX}"
                client.publish(topic_secondary, service_envelope_secondary.SerializeToString())
                log('info', f"Anuncio de presencia (NodeInfo) enviado a BROADCAST en canal '{config.SECONDARY_CHANNEL_NAME}'")

    except Exception as e:
        log('error', f"No se pudo enviar el NodeInfo: {e}")

def publish_position(client):
    """Publishes position to all configured channels."""
    if not config.POSITION_ENABLED or (config.BOT_LATITUDE == 0.0 and config.BOT_LONGITUDE == 0.0): return
    try:
        position_payload = mesh_pb2.Position(latitude_i=int(config.BOT_LATITUDE * 1e7), longitude_i=int(config.BOT_LONGITUDE * 1e7), altitude=config.BOT_ALTITUDE, time=int(time.time())).SerializeToString()
        
        service_envelope_primary = generate_mesh_packet(destination_id=BROADCAST_NUM, payload_data=position_payload, port_num=portnums_pb2.POSITION_APP, want_ack=False, channel_name=config.PRIMARY_CHANNEL_NAME, channel_key=config.PRIMARY_CHANNEL_KEY_B64)
        if service_envelope_primary:
            topic_primary = f"{config.ROOT_TOPIC}/2/e/{config.PRIMARY_CHANNEL_NAME}/{OUR_NODE_ID_HEX}"
            client.publish(topic_primary, service_envelope_primary.SerializeToString())
            log('info', f"Anuncio de posición enviado a BROADCAST en canal '{config.PRIMARY_CHANNEL_NAME}'")

        if config.SECONDARY_CHANNEL_ENABLED:
            service_envelope_secondary = generate_mesh_packet(destination_id=BROADCAST_NUM, payload_data=position_payload, port_num=portnums_pb2.POSITION_APP, want_ack=False, channel_name=config.SECONDARY_CHANNEL_NAME, channel_key=config.SECONDARY_CHANNEL_KEY_B64)
            if service_envelope_secondary:
                topic_secondary = f"{config.ROOT_TOPIC}/2/e/{config.SECONDARY_CHANNEL_NAME}/{OUR_NODE_ID_HEX}"
                client.publish(topic_secondary, service_envelope_secondary.SerializeToString())
                log('info', f"Anuncio de posición enviado a BROADCAST en canal '{config.SECONDARY_CHANNEL_NAME}'")

    except Exception as e:
        log('error', f"No se pudo enviar la Posición: {e}")

# --- INTEGRACIÓN CON GEMINI ---
get_weather_tool = genai.protos.Tool(
    function_declarations=[
        genai.protos.FunctionDeclaration(
            name='get_weather_data',
            description="Obtiene el pronóstico del tiempo actual para una ciudad. Úsalo para cualquier pregunta sobre el tiempo, clima o temperatura.",
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={'city': genai.protos.Schema(
                    type=genai.protos.Type.STRING, 
                    description="El nombre de la ciudad, por ejemplo: 'Barcelona', 'Londres', 'BCN'. Debes extraerlo de la pregunta del usuario."
                )},
                required=['city']
            )
        )
    ]
)
get_time_tool = genai.protos.Tool(
    function_declarations=[
        genai.protos.FunctionDeclaration(
            name='get_current_time',
            description="Obtiene la hora y fecha actual del servidor. Úsalo para cualquier pregunta sobre la hora, el día o la fecha.",
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={}
            )
        )
    ]
)
get_node_data_tool = genai.protos.Tool(
    function_declarations=[
        genai.protos.FunctionDeclaration(
            name='get_node_info_for_ai',
            description="Obtiene información guardada sobre un nodo específico de la red, incluyendo su nombre, ID, última vez visto, posición (latitud, longitud, altitud) y datos de telemetría (batería, voltaje, temperatura, presión barométrica). Úsalo cuando el usuario pregunte por datos de un nodo concreto.",
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={'node_identifier': genai.protos.Schema(
                    type=genai.protos.Type.STRING, 
                    description="El identificador del nodo, que puede ser su nombre largo, corto (prefijado con '@') o su ID hexadecimal (prefijado con '!'). Ejemplos: '@MiNodo', '!e2e5a934', 'Estacion Meteo'."
                )},
                required=['node_identifier']
            )
        )
    ]
)

def get_ai_response(text, sender_id):
    try:
        genai.configure(api_key=config.GEMINI_API_KEY)
        
        user_context = ""
        user_node = database.get_node_by_id(sender_id)
        if user_node:
            user_name = user_node['long_name'] or user_node['short_name'] or f"!{sender_id:08x}"
            user_context = f"Estás hablando con el usuario '{user_name}' (ID !{sender_id:08x}). "
            if user_node['latitude'] is not None:
                user_context += f"Su última ubicación conocida es Lat: {user_node['latitude']:.4f}, Lon: {user_node['longitude']:.4f}. "

        identity_str = (
            f"Eres MeshBot, un asistente de IA factual y directo. Tu propia identidad en la red es: Nombre Largo='{config.OUR_LONG_NAME}', "
            f"Nombre Corto='{config.OUR_SHORT_NAME}', ID='{OUR_NODE_ID_HEX}'. "
        )
        if config.POSITION_ENABLED and config.BOT_LATITUDE != 0.0:
            identity_str += f"Mi ubicación fija es Latitud {config.BOT_LATITUDE:.4f}, Longitud {config.BOT_LONGITUDE:.4f}. "

        # MODIFICADO: Prompt del sistema actualizado para mayor flexibilidad y sin info de config.
        system_instruction = (
            identity_str +
            "**Reglas de Contexto e Identidad (MUY IMPORTANTE):**\n"
            "1. **Tu Identidad:** Si el usuario pregunta por tu identidad (quién eres, tu nombre, tu ID, tu nodo, tu ubicación, dónde estás), DEBES responder usando la información de 'Tu propia identidad en la red' y 'Mi ubicación fija' que se te proporciona al principio de estas instrucciones. NO uses herramientas para esto.\n"
            "2. **Identidad del Usuario:** Si el usuario pregunta por su propia información ('mi nodo', 'mi ubicación', 'dónde estoy'), DEBES usar el ID del usuario que se te proporciona para buscar su información con la herramienta `get_node_info_for_ai`.\n"
            "3. **Contexto de Conversación:** Presta atención al historial. Si una pregunta es ambigua como '¿y su ubicación?', asume que se refiere al último sujeto del que hablaron (ya sea tú, el usuario, u otro nodo).\n\n"
            "Tu objetivo principal es proporcionar respuestas precisas y concisas. **No uses saludos, despedidas ni ningún tipo de relleno conversacional.** Ve directamente al grano.\n\n"
            "**Cómo Responder:**\n"
            "1. **Prioriza las Herramientas:** Si la pregunta del usuario puede ser respondida de forma precisa por una de tus herramientas, úsala. Las herramientas son para:\n"
            "   - `get_weather_data`: Para el tiempo, clima o temperatura.\n"
            "   - `get_current_time`: Para la hora o fecha actual.\n"
            "   - `get_node_info_for_ai`: Para datos específicos sobre nodos de la red (telemetría, ubicación, etc.).\n"
            "2. **Conocimiento General:** Si la pregunta no encaja con ninguna de las herramientas, responde usando tu conocimiento general. Sé útil y proporciona la información que se te solicita.\n"
            "3. **Sé Conciso:** Siempre da respuestas breves y directas, ideales para las pantallas de los dispositivos de radio.\n"
            "4. **Si no sabes, dilo:** Si una pregunta es demasiado compleja o no tienes la información, es mejor decir que no la tienes a inventar una respuesta."
        )
        
        model = genai.GenerativeModel(
            'gemini-1.5-flash-latest', 
            tools=[get_weather_tool, get_time_tool, get_node_data_tool], 
            system_instruction=system_instruction
        )
        chat = model.start_chat(history=CONVERSATION_HISTORY.get(sender_id, []))
        
        final_prompt = f"{user_context}El usuario dice: '{text}'"
        
        log('debug', f"Enviando a Gemini para !{sender_id:08x}: '{final_prompt}'")
        response = chat.send_message(final_prompt)
        
        while True:
            # CORRECCIÓN: Bucle para manejar múltiples llamadas a función
            function_calls = []
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    function_calls.append(part.function_call)
            
            if not function_calls:
                # No hay más llamadas a función, la respuesta final está lista
                response_text = response.candidates[0].content.parts[0].text.strip().replace('\n', ' ')
                CONVERSATION_HISTORY[sender_id] = chat.history
                return response_text

            # Hay llamadas a función, las ejecutamos todas
            log('info', f"Gemini quiere llamar a {len(function_calls)} función(es).")
            
            function_responses = []
            for function_call in function_calls:
                log('info', f"Ejecutando: {function_call.name}")
                api_response = None
                if function_call.name == 'get_weather_data':
                    city_arg = function_call.args.get('city')
                    if city_arg: api_response = get_weather_data(city=city_arg)
                    else: log('warning', "Llamada a get_weather_data sin 'city'."); api_response = "Error: falta la ciudad."
                elif function_call.name == 'get_current_time':
                    api_response = get_current_time()
                elif function_call.name == 'get_node_info_for_ai':
                    node_arg = function_call.args.get('node_identifier')
                    if node_arg: api_response = get_node_info_for_ai(node_identifier=node_arg)
                    else: log('warning', "Llamada a get_node_info_for_ai sin 'node_identifier'."); api_response = "Error: falta el nodo."
                
                function_responses.append(genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=function_call.name,
                        response={'result': api_response or "Error ejecutando función."}
                    )
                ))

            # Enviamos todas las respuestas de las funciones a la vez
            log('info', f"Enviando {len(function_responses)} resultado(s) de vuelta a Gemini.")
            response = chat.send_message(function_responses)

    except Exception as e:
        log('error', f"Error en la interacción con Gemini: {e}")
        return "Tuve un problema al procesar tu solicitud con la IA."

# --- PROCESAMIENTO DE MENSAJES ENTRANTES ---
def process_incoming_meshtastic_packet(client, raw_payload, topic):
    try:
        se = mqtt_pb2.ServiceEnvelope(); se.ParseFromString(raw_payload)
        mp = se.packet
        sender_id = getattr(mp, 'from')
        
        if sender_id == config.OUR_NODE_NUMBER:
            return
        
        if database.message_id_exists(mp.id):
            return
        
        database.add_message_id(mp.id)
        source_channel = se.channel_id

        if mp.HasField('encrypted'):
            key_to_use = None
            
            if source_channel == config.PRIMARY_CHANNEL_NAME:
                key_to_use = config.PRIMARY_CHANNEL_KEY_B64
            elif config.SECONDARY_CHANNEL_ENABLED and source_channel == config.SECONDARY_CHANNEL_NAME:
                key_to_use = config.SECONDARY_CHANNEL_KEY_B64
            
            if not key_to_use:
                return

            try:
                decrypted_bytes = decrypt_payload(key_to_use, mp.id, sender_id, mp.encrypted)
                mp.decoded.ParseFromString(decrypted_bytes)
            except Exception as e:
                log('error', f"Fallo al descifrar mensaje de !{sender_id:08x} en '{source_channel}'. Clave incorrecta o paquete corrupto.")
                return

        if not mp.HasField('decoded'):
            return

        port_num = mp.decoded.portnum
        log_channel_msg = f"en canal '{source_channel}'"

        if port_num == portnums_pb2.NODEINFO_APP:
            user_info = mesh_pb2.User(); user_info.ParseFromString(mp.decoded.payload)
            log('info', f"NodeInfo recibido de !{sender_id:08x} ({user_info.long_name}) {log_channel_msg}")
            database.update_node(node_id=sender_id, long_name=user_info.long_name, short_name=user_info.short_name)
        
        elif port_num == portnums_pb2.POSITION_APP:
            pos_info = mesh_pb2.Position(); pos_info.ParseFromString(mp.decoded.payload)
            lat, lon, alt = pos_info.latitude_i * 1e-7, pos_info.longitude_i * 1e-7, pos_info.altitude
            log('info', f"Posición recibida de !{sender_id:08x} ({lat:.4f}, {lon:.4f}, {alt}m) {log_channel_msg}")
            database.update_node(node_id=sender_id, lat=lat, lon=lon, alt=alt)

        elif port_num == portnums_pb2.TELEMETRY_APP:
            telemetry_data = telemetry_pb2.Telemetry(); telemetry_data.ParseFromString(mp.decoded.payload)
            
            battery = telemetry_data.device_metrics.battery_level if telemetry_data.device_metrics.HasField('battery_level') else None
            voltage = telemetry_data.device_metrics.voltage if telemetry_data.device_metrics.HasField('voltage') else None
            air_temp = telemetry_data.environment_metrics.temperature if telemetry_data.environment_metrics.HasField('temperature') else None
            humidity = telemetry_data.environment_metrics.relative_humidity if telemetry_data.environment_metrics.HasField('relative_humidity') else None
            pressure = telemetry_data.environment_metrics.barometric_pressure if telemetry_data.environment_metrics.HasField('barometric_pressure') else None
            
            log_msg_parts = []
            if battery is not None: log_msg_parts.append(f"bat={battery}%")
            if voltage is not None: log_msg_parts.append(f"volt={voltage:.2f}V")
            if air_temp is not None: log_msg_parts.append(f"temp={air_temp:.1f}C")
            if humidity is not None: log_msg_parts.append(f"hum={humidity:.1f}%")
            if pressure is not None: log_msg_parts.append(f"press={pressure:.1f}hPa")

            if log_msg_parts:
                log('info', f"Telemetría de !{sender_id:08x}: {', '.join(log_msg_parts)} {log_channel_msg}")
                database.update_node_telemetry(
                    node_id=sender_id, 
                    battery_level=battery, 
                    voltage=voltage, 
                    air_temp=air_temp, 
                    humidity=humidity,
                    barometric_pressure=pressure
                )

        elif port_num == portnums_pb2.TEXT_MESSAGE_APP and config.SECONDARY_CHANNEL_ENABLED and source_channel == config.SECONDARY_CHANNEL_NAME:
            text = mp.decoded.payload.decode('utf-8', 'ignore')
            
            if mp.to == config.OUR_NODE_NUMBER:
                log('info', f"DM de !{sender_id:08x} en '{source_channel}': '{text}'")
                response_text = ""
                if text.startswith(config.COMMAND_PREFIX):
                    response_text = bot_commands.handle_command(text, CONVERSATION_HISTORY, sender_id)
                else:
                    response_text = get_ai_response(text, sender_id)

                if response_text:
                    send_long_message(client, sender_id, response_text, source_channel)
                return

            elif mp.to == BROADCAST_NUM and text.strip().lower().startswith('@meshbot'):
                original_text_parts = text.strip().split(maxsplit=1)
                
                if len(original_text_parts) > 1 and original_text_parts[1].lower() not in PRIVATE_REQUEST_KEYWORDS:
                    query_text = original_text_parts[1]
                    log('info', f"Consulta pública de !{sender_id:08x} para @meshbot: '{query_text}'")
                    response_text = get_ai_response(query_text, sender_id)
                    if response_text:
                        send_long_message(client, BROADCAST_NUM, response_text, source_channel)
                    
                    now = datetime.now()
                    last_sent = LAST_INVITATION_SENT.get(sender_id)
                    
                    if not last_sent or (now - last_sent) > timedelta(minutes=config.INVITATION_COOLDOWN_MINUTES):
                        log('info', f"Enviando invitación a DM a !{sender_id:08x} (Cooldown finalizado).")
                        invitation_text = "He respondido en el canal. Si prefieres, puedes hablar conmigo en privado."
                        send_long_message(client, sender_id, invitation_text, source_channel)
                        LAST_INVITATION_SENT[sender_id] = now
                    else:
                        log('info', f"No se envía invitación a DM a !{sender_id:08x} (En Cooldown).")

                else:
                    log('info', f"Invocación de @meshbot por !{sender_id:08x}. Enviando ayuda a DM.")
                    response_text = bot_commands.handle_command("!meshbot", CONVERSATION_HISTORY, sender_id)
                    send_long_message(client, sender_id, response_text, source_channel)
                return

    except Exception as e:
        log('error', f"Error procesando paquete entrante: {e}")


# --- CALLBACKS DE MQTT Y TAREAS PROGRAMADAS ---
def on_connect(client, userdata, flags, rc, properties):
    if rc == 0:
        log('info', f"Conectado a {config.MQTT_BROKER}")
        
        primary_channel_topic = f"{config.ROOT_TOPIC}/2/e/{config.PRIMARY_CHANNEL_NAME}/#"
        client.subscribe(primary_channel_topic)
        log('info', f"Suscrito al topic del canal primario: {primary_channel_topic}")

        if config.SECONDARY_CHANNEL_ENABLED:
            secondary_channel_topic = f"{config.ROOT_TOPIC}/2/e/{config.SECONDARY_CHANNEL_NAME}/#"
            client.subscribe(secondary_channel_topic)
            log('info', f"Suscrito al topic del canal secundario: {secondary_channel_topic}")

        dm_topic = f"{config.ROOT_TOPIC}/2/c/{OUR_NODE_ID_HEX}"
        client.subscribe(dm_topic)
        log('info', f"Suscrito al topic de DM: {dm_topic}")

        log('info', f"Bot '{config.OUR_LONG_NAME}' ({OUR_NODE_ID_HEX}) en modo escucha...")
        if config.PRESENCE_ENABLED: 
            threading.Thread(target=presence_scheduler, args=(client,), daemon=True).start()
    else: 
        log('error', f"Fallo al conectar al bróker MQTT, código: {rc}."); client.disconnect()

def on_message(client, userdata, msg): process_incoming_meshtastic_packet(client, msg.payload, msg.topic)
def on_disconnect(client, userdata, d, rc, p): log('advertencia', f"Desconectado (código: {rc}).")

def broadcast_scheduler(client):
    if not config.BROADCAST_ENABLED or not config.SECONDARY_CHANNEL_ENABLED: return
    log('info', f"Anuncios automáticos habilitados para '{config.SECONDARY_CHANNEL_NAME}'.")
    while True:
        time.sleep(config.BROADCAST_INTERVAL_MINUTES * 60)
        log('info', f"Enviando anuncio a '{config.SECONDARY_CHANNEL_NAME}'...")
        publish_meshtastic_message(client, BROADCAST_NUM, config.BROADCAST_MESSAGE, config.SECONDARY_CHANNEL_NAME)

def presence_scheduler(client):
    log('info', "Anuncios de presencia habilitados.")
    publish_nodeinfo(client)
    publish_position(client)
    while True:
        time.sleep(config.PRESENCE_INTERVAL_MINUTES * 60)
        publish_nodeinfo(client)
        publish_position(client)

def database_cleanup_scheduler():
    """Tarea programada que se ejecuta una vez al día para limpiar la base de datos."""
    log('info', "Limpieza de base de datos programada habilitada. Se ejecutará cada 24 horas.")
    while True:
        time.sleep(24 * 60 * 60)
        log('info', "Iniciando limpieza periódica de la base de datos...")
        try:
            database.cleanup_old_messages()
            database.cleanup_old_nodes(config.NODE_DB_CLEANUP_DAYS)
            log('info', "Limpieza de la base de datos completada.")
        except Exception as e:
            log('error', f"Error durante la limpieza programada de la base de datos: {e}")

# --- FUNCIÓN PRINCIPAL ---
def main():
    log('info', f"Iniciando 🤖 {config.OUR_LONG_NAME} v0.0.1...")
    database.init_db()
    
    threading.Thread(target=database_cleanup_scheduler, args=(), daemon=True).start()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect, client.on_message, client.on_disconnect = on_connect, on_message, on_disconnect
    if config.MQTT_USERNAME: client.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)
    if config.MQTT_PORT == 8883: client.tls_set()
    try:
        log('info', f"Conectando a {config.MQTT_BROKER}:{config.MQTT_PORT}...")
        client.connect(config.MQTT_BROKER, config.MQTT_PORT, 60)
        if config.BROADCAST_ENABLED: 
            threading.Thread(target=broadcast_scheduler, args=(client,), daemon=True).start()
        client.loop_forever()
    except KeyboardInterrupt: 
        log('info', "Proceso interrumpido.")
    except Exception as e: 
        log('error', f"Error en bucle principal: {e}")
    finally: 
        client.disconnect(); log('info', "Bot detenido.")

if __name__ == "__main__":
    main()
