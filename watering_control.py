#! /usr/bin/python3

import time
import sys
import yaml
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

#import RPi.GPIO as GPIO

# dh - OFF
# dl - ON
#chan_list = [2, 3, 4, 17, 27, 22, 10, 9]
high_level_pin = 23
low_level_pin = 24
'''
zones = {'zone1': 3,
        'zone2': 4,
        'zone3': 17,
        'zone4': 27,
        'zone5': 22,
        'zone6': 10
        }
'''

class RPIWatering:

    output_pins = []
    main_power_pin = 9

    def __init__(self, output_pins, input_pins, main_power_pin):
        self.output_pins = output_pins
        self.main_power_pin = main_power_pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.output_pins, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(input_pins, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        #GPIO.setup(high_level_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        #GPIO.setup(low_level_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        for ch in self.output_pins:
            self.set_status_rpi(ch, True) #OFF

    def get_status(self, channel):
        ch_status = GPIO.input(channel)
        if ch_status == 0:
            return True
        if ch_status == 1:
            return False

    def set_status_rpi(self, channel, status):
        #GPIO.output(ch, True) #OFF
        GPIO.output(channel, status)
        return True

    def set_status(self, channel, status):
        '''
        channel - pin number
        status - True = ON, False - OFF 
        '''
        logger.info(f'Check {channel} is in {status}')
        if self.get_status(channel) != status:
            logger.info(f'Switching {channel} to {status}')
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
            logger.info(f'Set main power {self.main_power_pin} to {target_status}')
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
        if channel in self.states:
            #print(f'{channel} state in the mapping')
            current_state = self.states[channel]
            if current_state != status:
                logger.info(f'Set {channel} channel to {status}')
                self.states[channel] = status
        else:
            logger.info(f'Set {channel} channel to {status}')
            self.states[channel] = status
        return True

    def cleanup():
        return True


def is_current_time_in_interval(day: str, time_str: str, duration: int) -> bool:
    # Получаем текущее время
    now = datetime.now()
    
    # Преобразуем день недели из строки в индекс (Mon=0, Sun=6)
    days_map = {'Mon': 0, 'Tue': 1, 'Wed': 2, 'Thu': 3, 'Fri': 4, 'Sat': 5, 'Sun': 6}
    target_weekday = days_map.get(day)

    if target_weekday is None:
        raise ValueError(f"Invalid day string: {day}")

    # Создаем datetime объекта начала интервала для этой недели
    today_weekday = now.weekday()
    days_difference = (target_weekday - today_weekday) % 7
    interval_start_date = now.date() + timedelta(days=days_difference)

    # Время начала интервала
    interval_start_time = datetime.strptime(time_str, '%H:%M').time()
    interval_start = datetime.combine(interval_start_date, interval_start_time)

    # Время окончания интервала
    interval_end = interval_start + timedelta(minutes=duration)

    # Проверка попадания текущего времени в интервал
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


logging.basicConfig(format='%(asctime)s:%(levelname)s: %(message)s', filename='watering_control.log', level=logging.INFO)

with open(sys.argv[1]) as stream:
    try:
        config = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        logger.critical(exc)
chan_list = []
chan_list.append(config['general']['main_power_channel'])
if config['general'].get('water_input_channel', '')!= '':
    chan_list.append(config['general']['water_input_channel'])

for zone_name, zone_config in config['zones'].items():
    chan_list.append(zone_config['channel'])

try:
    import RPi.GPIO as GPIO
    rpi = RPIWatering(chan_list, [high_level_pin, low_level_pin], config['general']['main_power_channel'])
except ImportError:
    logger.info('There is no RPI module. Switching to test class')
    rpi = RPIWateringTest()


for ch in chan_list:
    ch_status = rpi.get_status(ch)
    logger.info(f'{ch} - {ch_status}')

#GPIO.output(9, False) # Main power ON
#GPIO.output(2, False) # Water input ON

while True:
    # Handle water input needs
    if config['general'].get('water_input_channel', '')!= '':
        low_level = rpi.get_status(low_level_pin)
        high_level = rpi.get_status(high_level_pin)
        logger.info(f'Low: {low_level}, High: {high_level}')
        if low_level == False:
            logger.info('Start refill')
            #rpi.set_status(9, True) # Main power ON
            rpi.set_status(config['general']['water_input_channel'], True) # Water input ON
        if high_level == True:
            logger.info('Stop refill')
            rpi.set_status(config['general']['water_input_channel'], False) # Water input OFF
            #rpi.set_status(9, False) # Main power OFF

    for zone_name, zone_config in config['zones'].items():
        logger.info(zone_name)
        current_needs = False
        for period in zone_config.get('schedule', []):
            #print(period)
            need_watering = is_current_time_in_interval(period['day'], 
                                                        period['time'], 
                                                        period['duration'])
            if need_watering == True:
                logger.info(f'{zone_name} zone needs watering')
                current_needs = True
        rpi.set_status(zone_config['channel'], current_needs)

    time.sleep(config['general']['sleep_time'])

rpi.cleanup()


