import machine
import neopixel
import math
import time
import _thread
from ssd1306 import SSD1306_I2C

# Constants
PIN_LED = 14
NUM_LEDS = 60
OLED_SDA = 2
OLED_SCL = 3
ADC_PIN = 4
BUTTON_1 = 4
BUTTON_2 = 5
BUTTON_3 = 6
BUTTON_4 = 7

# Pins
button_1 = machine.Pin(BUTTON_1, machine.Pin.IN, machine.Pin.PULL_UP)
button_2 = machine.Pin(BUTTON_2, machine.Pin.IN, machine.Pin.PULL_UP)
button_3 = machine.Pin(BUTTON_3, machine.Pin.IN, machine.Pin.PULL_UP)
button_4 = machine.Pin(BUTTON_4, machine.Pin.IN, machine.Pin.PULL_UP)

# Temperature Sensor
sensor = machine.ADC(ADC_PIN)

def ReadTemperature():
    adc_value = sensor.read_u16()
    volt = (3.3/65535) * adc_value
    temperature = 27 - (volt - 0.706)/0.001721
    return round(temperature, 1)

# Display and LED setup
led = neopixel.NeoPixel(machine.Pin(PIN_LED), NUM_LEDS, bpp=3)
i2c_1 = machine.I2C(id=1, sda=machine.Pin(OLED_SDA), scl=machine.Pin(OLED_SCL))
oled = SSD1306_I2C(128, 64, i2c_1)
oled.fill(1)
oled.show()
oled.fill(0)
oled.show()

humansensor_read = machine.Pin(8, machine.Pin.IN)

# Shared variables
persist_multiplier = 0
brightness = 1
lock = _thread.allocate_lock()

def button_control():
    global persist_multiplier, brightness
    while True:
        with lock:
            if button_4.value() == 0:
                if persist_multiplier == 0:
                    print("always on mode")
                    persist_multiplier = 1
                elif persist_multiplier == 1:
                    print("always off mode")
                    persist_multiplier = 2
                elif persist_multiplier == 2:
                    print("normal mode")
                    persist_multiplier = 0
                time.sleep(0.2)  # Debounce delay
            if button_1.value() == 0:
                print("Button 1 pressed")
                time.sleep(0.2)
                brightness += 0.1
                brightness = min(1, brightness)
            if button_2.value() == 0:
                print("Button 2 pressed")
                time.sleep(0.2)
                brightness -= 0.1
                brightness = max(0, brightness)

def main_loop():
    global persist_multiplier, brightness
    t = 0
    while True:
        temperature = ReadTemperature() - 5
        with lock:
            if humansensor_read.value() == 1 and persist_multiplier == 0:
                print("Human detected")
                oled.fill(0)
                oled.text("Human Detected", 0, 0)
                oled.text("Temp: " + str(temperature) + "C", 0, 10)
                oled.text("Power: " + str(brightness*100) + "%", 0, 30)
                oled.show()
                bright = 0.5 + 0.4 * math.sin(t / 255)
                for i in range(NUM_LEDS):
                    led[i] = (int(brightness * bright * (235 - 0.1 * (t % 255))),
                              int(brightness * bright * (100 - i * 0.1)), int(brightness * bright * (59 + i * 0.2)))
                t += 3
                led.write()
            elif persist_multiplier == 1:
                print("Always on mode")
                oled.fill(0)
                oled.text("Always on", 0, 20)
                oled.text("Temp: " + str(temperature) + "C", 0, 10)
                oled.text("Power: " + str(brightness*100) + "%", 0, 30)
                oled.show()
                bright = 0.5 + 0.4 * math.sin(t / 255)
                for i in range(NUM_LEDS):
                    led[i] = (int(brightness * bright * (235 - 0.1 * (t % 255))),
                              int(brightness * bright * (100 - i * 0.1)), int(brightness * bright * (59 + i * 0.2)))
                t += 3
                led.write()
            elif persist_multiplier == 2:
                print("Always off mode")
                oled.fill(0)
                oled.text("Always off", 0, 20)
                oled.text("Temp: " + str(temperature) + "C", 0, 10)
                oled.show()
                for i in range(NUM_LEDS):
                    led[i] = (0, 0, 0)
                t += 3
                led.write()
            else:
                print("No human detected")
                oled.fill(0)
                oled.text("No Human Detected", 0, 0)
                oled.text("Temp: " + str(temperature) + "C", 0, 10)
                oled.show()
                for i in range(NUM_LEDS):
                    led[i] = (0, 0, 0)
                led.write()
            time.sleep(0.1)

# Start the second core for button control
_thread.start_new_thread(button_control, ())

# Run main loop on core 0
main_loop()
