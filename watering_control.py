#!/usr/bin/env python3

import logging
import sys
import time
from datetime import datetime, timedelta

import yaml

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None  # Mock or fallback handled later


HIGH_LEVEL_PIN = 23
LOW_LEVEL_PIN = 24


class RPIWatering:
    def __init__(self, output_pins, input_pins, main_power_pin):
        self.output_pins = output_pins
        self.main_power_pin = main_power_pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.output_pins, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(input_pins, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        for ch in self.output_pins:
            self.set_status_rpi(ch, True)  # OFF

    def get_status(self, channel):
        return GPIO.input(channel) == 0

    def set_status_rpi(self, channel, status):
        GPIO.output(channel, not status)
        return True

    def set_status(self, channel, status):
        logger.info(f"Checking status for channel {channel}: expected {status}")
        if self.get_status(channel) != status:
            logger.info(f"Switching channel {channel} to {status}")
            self.set_status_rpi(channel, status)
            self.check_main_power()
        return True

    def check_main_power(self):
        target_status = any(
            self.get_status(ch) for ch in self.output_pins if ch != self.main_power_pin
        )
        if self.get_status(self.main_power_pin) != target_status:
            logger.info(f"Setting main power {self.main_power_pin} to {target_status}")
            self.set_status_rpi(self.main_power_pin, target_status)

    def cleanup(self):
        GPIO.cleanup()


class RPIWateringTest:
    def __init__(self):
        self.states = {}

    def get_status(self, channel):
        return self.states.get(channel, False)

    def set_status_rpi(self, channel, status):
        self.states[channel] = status
        return True

    def set_status(self, channel, status):
        current_state = self.states.get(channel)
        if current_state != status:
            logger.info(f"Setting test channel {channel} to {status}")
            self.states[channel] = status
        return True

    def cleanup(self):
        return True


def is_current_time_in_interval(day: str, time_str: str, duration: int) -> bool:
    now = datetime.now()
    days_map = {
        'Mon': 0, 'Tue': 1, 'Wed': 2,
        'Thu': 3, 'Fri': 4, 'Sat': 5, 'Sun': 6
    }
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
    high_level = rpi.get_status(HIGH_LEVEL_PIN) == 0
    low_level = rpi.get_status(LOW_LEVEL_PIN) == 0
    return low_level, high_level


logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='watering_control.log',
    level=logging.INFO
)

if len(sys.argv) < 2:
    logger.critical("Configuration file path not provided.")
    sys.exit(1)

with open(sys.argv[1]) as stream:
    try:
        config = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        logger.critical(exc)
        sys.exit(1)

chan_list = [config['general']['main_power_channel']]

if config['general'].get('water_input_channel'):
    chan_list.append(config['general']['water_input_channel'])

for zone in config['zones'].values():
    chan_list.append(zone['channel'])

if GPIO:
    rpi = RPIWatering(chan_list, [HIGH_LEVEL_PIN, LOW_LEVEL_PIN], config['general']['main_power_channel'])
else:
    logger.info("RPi.GPIO not available. Using test mode.")
    rpi = RPIWateringTest()

for ch in chan_list:
    logger.info(f"Channel {ch} initial status: {rpi.get_status(ch)}")

try:
    while True:
        water_input_channel = config['general'].get('water_input_channel')
        if water_input_channel:
            low_level = rpi.get_status(LOW_LEVEL_PIN)
            high_level = rpi.get_status(HIGH_LEVEL_PIN)
            logger.info(f"Water level - Low: {low_level}, High: {high_level}")

            if not low_level:
                logger.info("Starting refill")
                rpi.set_status(water_input_channel, True)

            if high_level:
                logger.info("Stopping refill")
                rpi.set_status(water_input_channel, False)

        for zone_name, zone_config in config['zones'].items():
            logger.info(f"Checking schedule for zone: {zone_name}")
            current_needs = any(
                is_current_time_in_interval(period['day'], period['time'], period['duration'])
                for period in zone_config.get('schedule', [])
            )
            if current_needs:
                logger.info(f"{zone_name} needs watering")
            rpi.set_status(zone_config['channel'], current_needs)

        time.sleep(config['general']['sleep_time'])

except KeyboardInterrupt:
    logger.info("Shutting down watering system...")
    rpi.cleanup()
