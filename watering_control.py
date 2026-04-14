#! /usr/bin/python3

import time
import sys
import yaml
import json
import os
import signal
from datetime import datetime, timedelta
import logging
from logging.handlers import TimedRotatingFileHandler
import paho.mqtt.client as mqtt
import threading
import requests
try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None  # Mock or fallback handled later

TRIG = 26  # Associate pin 27 to TRIG
ECHO = 19  # Associate pin 22 to Echo

#import RPi.GPIO as GPIO
# dh - OFF
# dl - ON
#chan_list = [2, 3, 4, 17, 27, 22, 10, 9]
high_level_pin = 23
low_level_pin = 24
rain_pin = 11
'''
zones = {'zone1': 3,
        'zone2': 4,
        'zone3': 17,
        'zone4': 27,
        'zone5': 22,
        'zone6': 10
        }
'''

def get_rain_status():
    try:
        response = requests.get(
            "https://ha.jktu.org.ua/api/states/sensor.northwatering_rain",
            headers={"Authorization": f"Bearer {os.getenv('HA_TOKEN', '')}"},
        )
        json_response = response.json()
        rain_status = json_response["state"]
        if rain_status == 'Yes':
            return True
        else:
            return False
    except Exception as e:
        logging.error(f"Failed to get rain status: {e}")
    return True

class HAMqtt:
    mqtt_host = os.getenv("MQTT_HOST", '')
    mqtt_user = os.getenv("MQTT_USER", '')
    mqtt_password = os.getenv("MQTT_PASSWORD", '')
    mqtt_client = ''
    connected = False
    reconnect_delay = 1
    max_reconnect_delay = 60
    subscriptions = []

    def __init__(self):
        # Check for missing configurations
        REQUIRED_CONFIGS = [self.mqtt_host, self.mqtt_user, self.mqtt_password]
        if not all(REQUIRED_CONFIGS):
            logging.error("One or more required environment variables are missing.")
            exit(1)
        self.mqtt_client = self.setup_mqtt_client()
        self.mqtt_client.loop_start()

    def setup_mqtt_client(self) -> mqtt.Client:
        """Setup and return an MQTT client with reconnection support."""
        mqtt_client = mqtt.Client()
        mqtt_client.username_pw_set(self.mqtt_user, self.mqtt_password)
        
        # Set up callback handlers
        mqtt_client.on_connect = self.on_connect
        mqtt_client.on_disconnect = self.on_disconnect
        mqtt_client.on_publish = self.on_publish
        
        # Note: reconnect_delay_set is not available in paho-mqtt 2.1.0
        # We'll handle reconnection manually in connect_with_retry
        
        mqtt_client.user_data_set(set())
        
        # Initial connection
        self.connect_with_retry(mqtt_client)
        return mqtt_client

    def connect_with_retry(self, mqtt_client):
        """Attempt to connect to MQTT broker with exponential backoff."""
        while not self.connected:
            try:
                mqtt_client.connect(self.mqtt_host)
                logging.info("Connected to MQTT broker.")
                self.connected = True
                self.reconnect_delay = 1  # Reset delay on successful connection
            except Exception as e:
                logging.error(f"Failed to connect to MQTT broker: {e}")
                logging.info(f"Retrying in {self.reconnect_delay} seconds...")
                time.sleep(self.reconnect_delay)
                # Exponential backoff with max delay
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

    def on_connect(self, client, userdata, flags, rc):
        """Callback for MQTT on_connect event."""
        if rc == 0:
            self.connected = True
            logging.info("Successfully connected to MQTT broker")
            # Resubscribe to all topics
            self.resubscribe_all()
        else:
            self.connected = False
            logging.error(f"Failed to connect to MQTT broker. Reason code: {rc}")

    def on_disconnect(self, client, userdata, rc):
        """Callback for MQTT on_disconnect event."""
        self.connected = False
        if rc != 0:
            logging.warning(f"Unexpected disconnection from MQTT broker. Reason code: {rc}")
        else:
            logging.info("Disconnected from MQTT broker")

    def resubscribe_all(self):
        """Resubscribe to all previously subscribed topics."""
        for topic in self.subscriptions:
            try:
                result = self.mqtt_client.subscribe(topic)
                if result[0] == mqtt.MQTT_ERR_SUCCESS:
                    logging.debug(f"Resubscribed to topic: {topic}")
                else:
                    logging.error(f"Failed to resubscribe to topic: {topic}")
            except Exception as e:
                logging.error(f"Error resubscribing to topic {topic}: {e}")

    def on_publish(self, client, userdata, mid):
        """Callback for MQTT on_publish event."""
        userdata.discard(mid)

    def send_data(self, topic: str, message: str):
        """Send data to MQTT broker with connection check."""
        if not self.connected:
            logging.warning("MQTT not connected. Attempting to reconnect...")
            self.connect_with_retry(self.mqtt_client)
        
        try:
            result = self.mqtt_client.publish(topic, message, qos=1)
            # In paho-mqtt 2.1.0, publish returns (result, mid)
            if result[0] == mqtt.MQTT_ERR_SUCCESS:
                logging.debug(f"Published to {topic}: {message} (mid={result[1]})")
            else:
                logging.error(f"Failed to publish to {topic}. Return code: {result[0]}")
        except Exception as e:
            logging.error(f"Failed to publish to MQTT: {e}")
            # Mark as disconnected to trigger reconnection
            self.connected = False

    def subscribe(self, topic: str):
        """Subscribe to a topic and track it for reconnection."""
        try:
            result = self.mqtt_client.subscribe(topic)
            if result[0] == mqtt.MQTT_ERR_SUCCESS:
                self.subscriptions.append(topic)
                logging.debug(f"Subscribed to topic: {topic}")
            else:
                logging.error(f"Failed to subscribe to topic: {topic}")
        except Exception as e:
            logging.error(f"Error subscribing to topic {topic}: {e}")

    def is_connected(self) -> bool:
        """Check if MQTT client is connected."""
        try:
            # Try the newer method first
            if hasattr(self.mqtt_client, 'is_connected'):
                return self.mqtt_client.is_connected()
            else:
                # Fallback for older versions - check if we have a connection
                return self.connected
        except Exception as e:
            logging.error(f"Error checking MQTT connection status: {e}")
            return False

    def check_connection_health(self):
        """Check connection health and reconnect if necessary."""
        if not self.is_connected():
            self.connected = False
            logging.warning("MQTT connection health check failed. Attempting to reconnect...")
            self.connect_with_retry(self.mqtt_client)
            return False
        return True

    #def send_data(self, mqtt_client: mqtt.Client, topic: str, message: str):
    def send_data_old(self, topic: str, message: str):
        """Send data to MQTT broker."""
        try:
            msg_info = self.mqtt_client.publish(topic, message, qos=1)
            msg_info.wait_for_publish()
            logging.info("Data sent to MQTT broker.")
        except Exception as e:
            logging.error(f"Failed to send data to MQTT broker: {e}")
        #mqtt_client = setup_mqtt_client()
        #mqtt_client.loop_start()
        #message = json.dumps(parsed_data)
        #send_data(mqtt_client, 'homeassistant/sensor/heater/state', message)

    def cleanup(self):
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()

    def create_storage_sensor(self, device_name, zone_name):
        payload = {
          "device": {
            "identifiers": [
              device_name
            ],
            "manufacturer": "JktuLTD",
            "model": "WTR-01",
            "name": device_name,
            "serial_number": "01020304"
          },
          "name": zone_name,
          "device_class": "volume_storage",
          "unit_of_measurement": "L",
          "state_class": "measurement",
          "object_id": f'{device_name}-{zone_name}',
          "state_topic": f"watering/{device_name}/state",
          "unique_id": f'{device_name}-{zone_name}',
          "value_template": f"{{{{ value_json.{zone_name}_state }}}}",
          #"device_class": "enum",
          "enabled_by_default": True
        }
        config_topic = f"homeassistant/sensor/{device_name}/{zone_name}/config"
        self.send_data(config_topic, json.dumps(payload))

    def create_flow_sensor(self, device_name, zone_name):
        payload = {
          "device": {
            "identifiers": [
              device_name
            ],
            "manufacturer": "JktuLTD",
            "model": "WTR-01",
            "name": device_name,
            "serial_number": "01020304"
          },
          "name": zone_name,
          "device_class": "volume_flow_rate",
          "unit_of_measurement": "L/m",
          "state_class": "measurement",
          "object_id": f'{device_name}-{zone_name}',
          "state_topic": f"watering/{device_name}/state",
          "unique_id": f'{device_name}-{zone_name}',
          "value_template": f"{{{{ value_json.{zone_name}_state }}}}",
          #"device_class": "enum",
          "enabled_by_default": True
        }
        config_topic = f"homeassistant/sensor/{device_name}/{zone_name}/config"
        self.send_data(config_topic, json.dumps(payload))

    def create_ha_sensor(self, device_name, zone_name):
        payload = {
          "device": {
            "identifiers": [
              device_name
            ],
            "manufacturer": "JktuLTD",
            "model": "WTR-01",
            "name": device_name,
            "serial_number": "01020304"
          },
          "name": zone_name,
          "device_class": "enum",
          "object_id": f'{device_name}-{zone_name}',
          "state_topic": f"watering/{device_name}/state",
          "unique_id": f'{device_name}-{zone_name}',
          "value_template": f"{{{{ value_json.{zone_name}_state }}}}",
          #"device_class": "enum",
          "enabled_by_default": True
        }
        config_topic = f"homeassistant/sensor/{device_name}/{zone_name}/config"
        self.send_data(config_topic, json.dumps(payload))

    def create_ha_device(self, device_name, zone_name):
        payload = {
          "device": {
            "identifiers": [
              device_name
            ],
            "manufacturer": "JktuLTD",
            "model": "WTR-01",
            "name": device_name,
            "serial_number": "01020304"
          },
          "name": zone_name,
          "object_id": f'{device_name}-{zone_name}',
          "state_topic": f"watering/{device_name}/state",
          "command_topic": f"watering/{device_name}/{zone_name}/set",
          "unique_id": f'{device_name}-{zone_name}',
          "value_template": f"{{{{ value_json.{zone_name}_state }}}}",
          #"device_class": "enum",
          "enabled_by_default": True,
          "payload_on": "ON",
          "payload_off": "OFF"
        }
        config_topic = f"homeassistant/switch/{device_name}/{zone_name}/config"
        self.send_data(config_topic, json.dumps(payload))
        self.subscribe(f'watering/{device_name}/{zone_name}/set')

class RPIWatering:
    output_pins = []
    main_power_pin = 9
    manual_execution = {}
    water_flowtimer = 0
    water_volume = 0

    def __init__(self, output_pins, input_pins, main_power_pin):
        self.output_pins = output_pins
        self.main_power_pin = main_power_pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.output_pins, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(input_pins, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(TRIG, GPIO.OUT)  # Set pin as GPIO out
        GPIO.setup(ECHO, GPIO.IN)  # Set pin as GPIO in
        GPIO.output(TRIG, False)  # Set TRIG as LOW
        #GPIO.setup(high_level_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        #GPIO.setup(low_level_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        for ch in self.output_pins:
            self.set_status_rpi(ch, True) #OFF

    def get_water_amount(self):
        distance_stat = []
        while True:
            distance = self.get_distance()
            #logger.info(f'Distance: {distance}')
            if distance > 20 and distance < 200:
                distance_stat.append(distance)
            if len(distance_stat)>=5:
                break
        distance = sum(distance_stat) / len(distance_stat)
        #logger.info(f'Distance stat: {distance_stat}!!')
        #logger.info(f'Distance: {distance}!!')
        '''
            700 - 38.5
            800 - 29
        '''
        distance = round(distance, 2)
        amount = (-11.11 * distance) + 1122.19
        amount = round(amount, 0)
        old_flowtimer = self.water_flowtimer
        self.water_flowtimer = round(time.time())
        old_volume = self.water_volume
        self.water_volume = amount
        water_flow = 0
        if self.water_flowtimer > 0:
            time_diff = self.water_flowtimer - old_flowtimer
            water_diff = self.water_volume - old_volume
            water_flow = round((water_diff / time_diff)*60)
        logging.info(f'Distance: {distance} cm, Volume: {amount} liters, Water flow: {water_flow} l/min')
        return (amount, water_flow)

    def get_distance(self):
        timeout = 1
        GPIO.output(TRIG, True)  # Set TRIG as HIGH
        time.sleep(0.00001)  # Delay of 0.00001 seconds
        GPIO.output(TRIG, False)  # Set TRIG as LOW

        pulse_start = time.time()
        timeout_start = pulse_start
        while GPIO.input(ECHO) == 0:
            pulse_start = time.time()
            if pulse_start - timeout_start > timeout:
                break

        pulse_end = time.time()
        timeout_end = pulse_end
        if GPIO.input(ECHO) == 1:
            while GPIO.input(ECHO) == 1:
                pulse_end = time.time()
                if pulse_end - timeout_end > timeout:
                    break

        pulse_duration = pulse_end - pulse_start  # Pulse duration to a variable
        #print(f'pulse_duration: {pulse_duration}')
        distance = pulse_duration * 17150  # Calculate distance
        distance = round(distance, 2)  # Round to two decimal points
        #print("Distance:", distance, "cm")
        return distance

    def get_status(self, channel):
        ch_status = GPIO.input(channel)
        if ch_status == 0:
            return True
        if ch_status == 1:
            return False

    def get_all_status(self, zones):
        res={}
        for zone_name, zone_config in zones.items():
            status = self.get_status(zone_config['channel'])
            if status == True:
                res[f'{zone_name}_state'] = 'ON'
            if status == False:
                res[f'{zone_name}_state'] = 'OFF'
        return res

    def get_input_status(self, input_channel):
        res={}
        status = self.get_status(input_channel)
        if status == True:
            return 'ON'
        if status == False:
            return 'OFF'

    def set_status_rpi(self, channel, status):
        #GPIO.output(ch, True) #OFF
        GPIO.output(channel, status)
        return True

    def set_status(self, channel, status):
        '''
        channel - pin number
        status - True = ON, False - OFF 
        '''
        logging.info(f'Check {channel} is in {status}')
        if self.get_status(channel) != status:
            logging.info(f'Switching {channel} to {status}')
            if status == True:
                self.set_status_rpi(channel, False)
            if status == False:
                self.set_status_rpi(channel, True)
            self.check_main_power()
        return True

    def check_main_power(self):
        target_status = False
        for ch in self.output_pins:
            if ch != self.main_power_pin:
                if self.get_status(ch) == True:
                    target_status = True
        if self.get_status(self.main_power_pin) != target_status:
            logging.info(f'Set main power {self.main_power_pin} to {target_status}')
            if target_status == True:
                self.set_status_rpi(self.main_power_pin, False)
            if target_status == False:
                self.set_status_rpi(self.main_power_pin, True)

    def cleanup():
        GPIO.cleanup()

class RPIWateringTest:
    states = {}

    def get_status(self, channel):
        return True

    def set_status_rpi(self, channel, status):
        #GPIO.output(ch, True) #OFF
        GPIO.output(channel, status)
        return True

    def set_status(self, channel, status):
        print('T1')
        if channel in self.states:
            #print(f'{channel} state in the mapping')
            current_state = self.states[channel]
            if current_state != status:
                logging.info(f'Set {channel} channel to {status}')
                self.states[channel] = status
        else:
            logging.info(f'Set {channel} channel to {status}')
            self.states[channel] = status
        return True

    def cleanup():
        return True

def is_current_time_in_interval(day: str, time_str: str, duration: int) -> bool:
    now = datetime.now()    
    days_map = {'Mon': 0, 'Tue': 1, 'Wed': 2, 'Thu': 3, 'Fri': 4, 'Sat': 5, 'Sun': 6}
    target_weekday = days_map.get(day)
    if target_weekday is None:
        raise ValueError(f"Invalid day string: {day}")
    today_weekday = now.weekday()
    days_difference = (target_weekday - today_weekday) % 7
    interval_start_date = now.date() + timedelta(days=days_difference)
    interval_start_time = datetime.strptime(time_str, '%H:%M').time()
    interval_start = datetime.combine(interval_start_date, interval_start_time)
    interval_end = interval_start + timedelta(minutes=duration)
    return interval_start <= now <= interval_end

def get_water_level():
    high_level_bin = rpi.get_status(high_level_pin)
    if high_level_bin == 0:
        high_level = True
    else:
        high_level = False
    low_level_bin = rpi.get_status(low_level_pin)    
    if low_level_bin == 0:
        low_level = True
    else:
        low_level = False
    return(low_level, high_level)

#GPIO.setup(channel, GPIO.IN, pull_up_down=GPIO.PUD_UP)
# or
#GPIO.setup(channel, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

def on_message(mqttc, obj, msg):
    logging.debug("Got new MQTT message "+msg.topic + " " + str(msg.qos) + " " + str(msg.payload))
    zone=msg.topic.split('/')[2]
    command = msg.payload.decode('utf-8')
    ch = config['zones'][zone]['channel']
    logging.info(f'Set {zone} zone ({ch}) to {str(command)}')
    if str(command) == 'ON':
        rpi.set_status(ch, True)
        blocked_zones[zone] = time.time()
    if str(command) == 'OFF':
        rpi.set_status(ch, False)
        blocked_zones.pop(zone)

    status_to_send = {}
    if config['general'].get('water_input_channel', '')!= '':
        low_level = rpi.get_status(low_level_pin)
        high_level = rpi.get_status(high_level_pin)
        rain_detect = rpi.get_status(rain_pin)
        status_to_send['storage_state'] = cached_water_amount
        status_to_send['flow_state'] = cached_water_flow
        if rain_detect == True:
            status_to_send['rain_state'] = 'No'
            logging.info(f'Rain: No')
        else:
            status_to_send['rain_state'] = 'Yes'
            logging.info(f'Rain: Yes')
        if low_level == True:
            status_to_send['low_water_state'] = 'Yes'
        else:
            status_to_send['low_water_state'] = 'No'
        if high_level == True:
            status_to_send['high_water_state'] = 'Yes'
        else:
            status_to_send['high_water_state'] = 'No'
    status_to_send = status_to_send | rpi.get_all_status(config['zones'])
    logging.debug(f'watering/{device_name}/state message: {json.dumps(status_to_send)}')
    threading.Thread(target=lambda: ham.send_data(f'watering/{device_name}/state', json.dumps(status_to_send))).start()
    #ham.send_data(f'watering/{device_name}/state', json.dumps(status_to_send))
    logging.debug('on_message is done')
    #logger.info(json.dumps(status_to_send))
    #ham.send_data(f'watering/{device_name}/state', json.dumps(status_to_send))
    #rpi.set_status(zone_config['channel'], current_needs)

def load_config():
    with open(sys.argv[1]) as stream:
        try:
            config = yaml.safe_load(stream)
            return config
        except yaml.YAMLError as exc:
            logging.critical(exc)

log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
log_handler = TimedRotatingFileHandler(
    'watering_control.log',
    when='midnight',
    interval=1,
    backupCount=7,
)
log_handler.setFormatter(log_formatter)
log_handler.suffix = "%Y-%m-%d"

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(log_handler)
rpi = ''
config = load_config()
ham = HAMqtt()
ham.mqtt_client.on_message = on_message
device_name = config['general']['device_name']
chan_list = []
chan_list.append(config['general']['main_power_channel'])
if config['general'].get('water_input_channel', '')!= '':
    chan_list.append(config['general']['water_input_channel'])
for zone_name, zone_config in config['zones'].items():
    chan_list.append(zone_config['channel'])
    ham.create_ha_device(device_name, zone_name)
ham.create_ha_sensor(device_name, 'high_water')
ham.create_ha_sensor(device_name, 'low_water')
ham.create_ha_sensor(device_name, 'rain')
ham.create_ha_sensor(device_name, 'input_water')
ham.create_storage_sensor(device_name, 'storage')
ham.create_flow_sensor(device_name, 'flow')
if GPIO:
    rpi = RPIWatering(chan_list, [high_level_pin, low_level_pin, rain_pin], config['general']['main_power_channel'])
else:
    logging.info("RPi.GPIO not available. Using test mode.")
    rpi = RPIWateringTest()
blocked_zones = {}
cached_water_amount = 0
cached_water_flow = 0

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logging.info(f"Received signal {signum}. Shutting down gracefully...")
    if 'ham' in globals():
        ham.cleanup()
    if 'rpi' in globals() and hasattr(rpi, 'cleanup'):
        rpi.cleanup()
    sys.exit(0)

def main():
    try:
        for ch in chan_list:
            ch_status = rpi.get_status(ch)
            logging.info(f'{ch} - {ch_status}')

        #GPIO.output(9, False) # Main power ON
        #GPIO.output(2, False) # Water input ON
        refill_timer = 0
        config_reload_timer = time.time()
        mqtt_health_check_timer = time.time()
        config = load_config()
        while True:
            logging.debug('Main loop started')
            if time.time() - config_reload_timer > config['general']['config_reload_timeout']*60:
                config = load_config()
                config_reload_timer = time.time()
            
            # MQTT connection health check every 30 seconds
            if time.time() - mqtt_health_check_timer > 30:
                ham.check_connection_health()
                mqtt_health_check_timer = time.time()
            
            rain_status = get_rain_status()
            if rain_status == True:
                logging.info('Rain detected. No need watering.')
            status_to_send = {}
            # Handle water input needs
            if config['general'].get('water_input_channel', '')!= '':
                global cached_water_amount, cached_water_flow
                water_amount, water_flow = rpi.get_water_amount()
                cached_water_amount = water_amount
                cached_water_flow = water_flow
                low_level = rpi.get_status(low_level_pin)
                high_level = rpi.get_status(high_level_pin)
                rain_detect = rpi.get_status(rain_pin)
                status_to_send['storage_state'] = water_amount
                status_to_send['flow_state'] = water_flow
                if rain_detect == True:
                    status_to_send['rain_state'] = 'No'
                    logging.info(f'Rain: No')
                else:
                    status_to_send['rain_state'] = 'Yes'
                    logging.info(f'Rain: Yes')
                if low_level == True:
                    status_to_send['low_water_state'] = 'Yes'
                else:
                    status_to_send['low_water_state'] = 'No'
                if high_level == True:
                    status_to_send['high_water_state'] = 'Yes'
                    status_to_send['storage_state'] = 1000
                else:
                    status_to_send['high_water_state'] = 'No'
                logging.info(f'Low: {low_level}, High: {high_level}')
                #if low_level == False and high_level == False:
                if water_amount < config['general']['refill_amount'] and high_level == False:
                    logging.info('Start refill')
                    refill_timer = time.time()
                    #rpi.set_status(9, True) # Main power ON
                    rpi.set_status(config['general']['water_input_channel'], True) # Water input ON
                    #status_to_send['input_water_state'] = 'Yes'
                if refill_timer > 0 and time.time() - refill_timer > config['general']['refill_timeout']*60:
                    logging.info('Force stop refill')
                    refill_timer = 0
                    rpi.set_status(config['general']['water_input_channel'], False) # Water input OFF
                    #status_to_send['input_water_state'] = 'No'
                if high_level == True:
                    logging.info('Stop refill')
                    refill_timer = 0
                    rpi.set_status(config['general']['water_input_channel'], False) # Water input OFF
                    #rpi.set_status(9, False) # Main power OFF
                    #status_to_send['input_water_state'] = 'No'
                status_to_send['input_water_state'] = rpi.get_input_status(config['general']['water_input_channel'])

            for zone_name, zone_config in config['zones'].items():
                logging.info(zone_name)
                if zone_name in blocked_zones:
                    if time.time() - blocked_zones[zone_name] > config['general']['blocking_timeout']*60:
                        logging.info(f'Force unblock zone {zone_name}')
                        blocked_zones.pop(zone_name)
                    else:
                        logging.info(f'{zone_name} zone is blocked')
                        continue
                current_needs = False
                for period in zone_config.get('schedule', []):
                    #print(period)
                    need_watering = is_current_time_in_interval(period['day'], 
                                                                period['time'], 
                                                                period['duration'])
                    if need_watering == True and rain_status == False:
                        logging.info(f'{zone_name} zone needs watering')
                        current_needs = True
                rpi.set_status(zone_config['channel'], current_needs)

            status_to_send = status_to_send | rpi.get_all_status(config['zones'])
            #logger.info(f'watering/{device_name}/state message: {json.dumps(status_to_send)}')
            ham.send_data(f'watering/{device_name}/state', json.dumps(status_to_send))
            logging.debug('Main loop done')
            time.sleep(config['general']['sleep_time'])

    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt. Shutting down...")
    except Exception as e:
        logging.error(f"Unexpected error in main loop: {e}")
    finally:
        logging.info("Cleaning up...")
        if 'ham' in globals():
            ham.cleanup()
        if 'rpi' in globals() and hasattr(rpi, 'cleanup'):
            rpi.cleanup()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    main()

