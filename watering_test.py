import time
import RPi.GPIO as GPIO

chan_list = [2, 3, 4, 17, 27, 22, 10, 9]
input_ch = 23

#GPIO.setup(channel, GPIO.IN, pull_up_down=GPIO.PUD_UP)
# or
#GPIO.setup(channel, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

GPIO.setmode(GPIO.BCM)
GPIO.setup(chan_list, GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(input_ch, GPIO.IN, pull_up_down=GPIO.PUD_UP)


'''
GPIO.output(2, False) #ON
time.sleep(1)
print(GPIO.input(2))
GPIO.output(2, True) #OFF
time.sleep(1)
print(GPIO.input(2))
time.sleep(3600000)
exit(0)
'''

print('Initial status')
for ch in chan_list:
	ch_status = GPIO.input(ch)
	print(f'{ch} - {ch_status}')
print('Set all to ON state')
for ch in chan_list:
	GPIO.output(ch, False) #ON
	time.sleep(0.5)
for ch in chan_list:
	ch_status = GPIO.input(ch)
	print(f'{ch} - {ch_status}')
print('Set all to OFF state')
for ch in chan_list:
	GPIO.output(ch, True) #OFF
	time.sleep(0.5)
for ch in chan_list:
	ch_status = GPIO.input(ch)
	print(f'{ch} - {ch_status}')


while True:
	level = GPIO.input(input_ch)
	if level==1:
		print('Water NOT detected')
	if level==0:
		print('Water detected')	
	time.sleep(0.5)	


GPIO.cleanup()
