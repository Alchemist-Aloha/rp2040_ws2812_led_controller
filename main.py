import machine
import neopixel
import math
import time
import _thread
from ssd1306 import SSD1306_I2C
import gc

gc.collect()  # Force garbage collection at startup
# from irrecvdata import irGetCMD

machine.freq(200000000)

# Constants
PIN_LED = 15
NUM_LEDS = 60
OLED_SDA = 6
OLED_SCL = 7
ADC_PIN = 4
BUTTON_1 = 2
BUTTON_2 = 3
BUTTON_3 = 4
BUTTON_4 = 5

# Pins
# recvPin = irGetCMD(26)    # Moved to second pico
button_1 = machine.Pin(BUTTON_1, machine.Pin.IN, machine.Pin.PULL_UP)
button_2 = machine.Pin(BUTTON_2, machine.Pin.IN, machine.Pin.PULL_UP)
button_3 = machine.Pin(BUTTON_3, machine.Pin.IN, machine.Pin.PULL_UP)
button_4 = machine.Pin(BUTTON_4, machine.Pin.IN, machine.Pin.PULL_UP)

# UART0
uart0 = machine.UART(0, baudrate=115200, tx=machine.Pin(0), rx=machine.Pin(1))
# Temperature Sensor
sensor = machine.ADC(ADC_PIN)


def ReadTemperature():
    adc_value = sensor.read_u16()
    volt = (3.3 / 65535) * adc_value
    temperature = 27 - (volt - 0.706) / 0.001721
    return round(temperature, 1)


# Display and LED setup
led = neopixel.NeoPixel(machine.Pin(PIN_LED), NUM_LEDS, bpp=3)
i2c_1 = machine.I2C(id=1, sda=machine.Pin(OLED_SDA), scl=machine.Pin(OLED_SCL))
oled = SSD1306_I2C(128, 64, i2c_1)
oled.fill(1)
oled.show()
oled.fill(0)
oled.show()

humansensor_read = machine.Pin(14, machine.Pin.IN)

# Shared variables
persist_multiplier = 0
brightness = 1
lock = _thread.allocate_lock()


def button_control():
    global persist_multiplier, brightness
    irValue = "0x000000"
    last_button_time = 0
    debounce_time = 200  # ms

    while True:
        current_time = time.ticks_ms()
        button_pressed = False

        # Read UART more efficiently
        if uart0.any():
            try:
                irValue = uart0.read().decode().strip()
            except UnicodeDecodeError:
                irValue = "0x000000"

        # Only process button inputs if debounce time has passed
        if time.ticks_diff(current_time, last_button_time) > debounce_time:
            if button_4.value() == 0 or irValue == "0xffa25d":
                persist_multiplier = 1 if persist_multiplier == 2 else 2
                button_pressed = True
                print("Toggled on/off")
                irValue = "0x000000"

            elif button_1.value() == 0 or irValue == "0xff02fd":
                brightness = min(1, brightness * 1.6)
                button_pressed = True
                print("Increase brightness")
                irValue = "0x000000"

            elif button_2.value() == 0 or irValue == "0xff9867":
                brightness = max(0.05, brightness * 0.625)
                button_pressed = True
                print("Decrease brightness")
                irValue = "0x000000"

            elif button_3.value() == 0 or irValue == "0xffa857":
                persist_multiplier = 0
                button_pressed = True
                print("Human sensor mode")
                irValue = "0x000000"

            if button_pressed:
                last_button_time = current_time

        # Small sleep to prevent CPU hogging
        time.sleep_ms(10)


def led_loop():
    global persist_multiplier, brightness
    t = 0
    previous_state = -1  # Track previous state
    led_buffer = [(0, 0, 0)] * NUM_LEDS  # Pre-allocate buffer

    while True:
        temperature = ReadTemperature() - 5
        current_state = (
            humansensor_read.value() == 1 and persist_multiplier == 0
        ) or persist_multiplier == 1

        try:
            # Only update OLED if state changes or every 50 iterations (reduces I2C traffic)
            if t % 50 == 0 or previous_state != current_state:
                oled.fill(0)
                if humansensor_read.value() == 1 and persist_multiplier == 0:
                    oled.text("Human Detected", 0, 20)
                elif persist_multiplier == 1:
                    oled.text("Always on", 0, 20)
                elif persist_multiplier == 2:
                    oled.text("Always off", 0, 20)
                else:
                    oled.text("No Human Detected", 0, 20)
                oled.text("Temp: " + str(temperature) + "C", 0, 10)
                if current_state:
                    oled.text("Power: " + str(int(brightness * 100)) + "%", 0, 30)
                oled.show()
                previous_state = current_state

            # Calculate values once for LED updates
            if current_state:  # Human detected or always on
                breath = 0.8 + 0.2 * math.sin(t * math.pi / 400)
                r = int(brightness * breath * (235 - 20 * math.sin(t * math.pi / 250)))
                g = int(brightness * breath * (100 - 20 * math.sin(t * math.pi / 200)))
                b = int(brightness * breath * (59 + math.sin(t * math.pi / 300) * 10))

                # Shift pattern (more efficient)
                for i in range(NUM_LEDS - 1):
                    led_buffer[i] = led_buffer[i + 1]
                led_buffer[NUM_LEDS - 1] = (r, g, b)

                # Update all LEDs at once
                for i in range(NUM_LEDS):
                    led[i] = led_buffer[i]
            elif (
                not (t % 5) or previous_state != current_state
            ):  # Only update LEDs when needed
                for i in range(NUM_LEDS):
                    led[i] = (0, 0, 0)
        except Exception as e:
            print("Error updating LEDs:", e)

        # Add periodic garbage collection in your main loop
        if t % 1000 == 0:
            gc.collect()
        t += 1

        led.write()
        time.sleep_ms(2)


# Start the second core for button control
_thread.start_new_thread(led_loop, ())


# Run main loop on core 0
button_control()
