# !/usr/bin/python
# encoding:utf-8

# Waterproof Ultrasonic Module AJ-SR04M

import RPi.GPIO as GPIO
import time

timeout = 1  # seconds wait for signal
TRIG = 17  # Associate pin 27 to TRIG
ECHO = 27  # Associate pin 22 to Echo

# PIN setup
GPIO.setmode(GPIO.BCM)  # Set GPIO pin numbering
GPIO.setup(TRIG, GPIO.OUT)  # Set pin as GPIO out
GPIO.setup(ECHO, GPIO.IN)  # Set pin as GPIO in
GPIO.output(TRIG, False)  # Set TRIG as LOW

# settle
time.sleep(1)
print("Distance measurement in progress")

try:
    while True:
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
        print(f'pulse_duration: {pulse_duration}')
        distance = pulse_duration * 17150  # Calculate distance
        distance = round(distance, 2)  # Round to two decimal points
        print("Distance:", distance, "cm")

        time.sleep(3)

except KeyboardInterrupt:
    print("Measurement stopped by User")
    GPIO.cleanup()

# chmod +x /home/pi/rainbarrel.py
# sudo chmod 644 /lib/systemd/system/rainbarrel.service