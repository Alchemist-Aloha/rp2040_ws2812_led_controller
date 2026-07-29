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

IR_NONE = "0x000000"
IR_TOGGLE = "0xffa25d"
IR_BRIGHTER = "0xff02fd"
IR_DIMMER = "0xff9867"
IR_SENSOR_MODE = "0xffa857"
IR_COMMANDS = (IR_TOGGLE, IR_BRIGHTER, IR_DIMMER, IR_SENSOR_MODE)


def apply_control(command):
    """Apply one button/remote command and report whether it was recognized."""
    global persist_multiplier, brightness

    if command == IR_TOGGLE:
        # Enter always-on first, then alternate between always-on and always-off.
        persist_multiplier = 2 if persist_multiplier == 1 else 1
        print("Toggled on/off")
    elif command == IR_BRIGHTER:
        brightness = min(1, brightness * 1.6)
        print("Increase brightness")
    elif command == IR_DIMMER:
        brightness = max(0.05, brightness * 0.625)
        print("Decrease brightness")
    elif command == IR_SENSOR_MODE:
        persist_multiplier = 0
        print("Human sensor mode")
    else:
        return False
    return True


def button_control():
    ir_value = IR_NONE
    uart_buffer = ""
    last_button_time = 0
    debounce_time = 200  # ms
    buttons = (
        (button_4, IR_TOGGLE),
        (button_1, IR_BRIGHTER),
        (button_2, IR_DIMMER),
        (button_3, IR_SENSOR_MODE),
    )
    previous_values = [button.value() for button, _ in buttons]

    while True:
        current_time = time.ticks_ms()

        # Preserve partial UART reads; UART data may arrive in several chunks.
        if uart0.any():
            try:
                chunk = uart0.read()
                if chunk:
                    uart_buffer = (uart_buffer + chunk.decode().lower())[-64:]
                    for command in IR_COMMANDS:
                        if command in uart_buffer:
                            ir_value = command
                            uart_buffer = ""
                            break
            except UnicodeDecodeError:
                uart_buffer = ""

        current_values = [button.value() for button, _ in buttons]
        command = ir_value if ir_value in IR_COMMANDS else None

        # Trigger physical buttons only on the pressed edge. This prevents a
        # held mode button from toggling repeatedly every debounce interval.
        if command is None:
            for index, (_, button_command) in enumerate(buttons):
                if previous_values[index] == 1 and current_values[index] == 0:
                    command = button_command
                    break

        if time.ticks_diff(current_time, last_button_time) > debounce_time:
            if command is not None and apply_control(command):
                last_button_time = current_time
                ir_value = IR_NONE

        previous_values = current_values
        time.sleep_ms(10)


def led_loop():
    global persist_multiplier, brightness
    t = 0
    previous_state = -1  # Track previous state
    led_buffer = [(0, 0, 0)] * NUM_LEDS  # Pre-allocate buffer

    while True:
        try:
            temperature = ReadTemperature() - 5
            human_detected = humansensor_read.value() == 1
        except Exception as e:
            print("Error reading sensors:", e)
            time.sleep_ms(100)
            continue

        current_state = (
            human_detected and persist_multiplier == 0
        ) or persist_multiplier == 1
        state_changed = previous_state != current_state

        # A display failure must not prevent the lights from operating.
        try:
            # Only update OLED if state changes or every 50 iterations (reduces I2C traffic)
            if t % 50 == 0 or state_changed:
                oled.fill(0)
                if human_detected and persist_multiplier == 0:
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
        except Exception as e:
            print("Error updating display:", e)

        try:
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
            elif not (t % 5) or state_changed:
                for i in range(NUM_LEDS):
                    led[i] = (0, 0, 0)
            led.write()
        except Exception as e:
            print("Error updating LEDs:", e)

        previous_state = current_state

        # Add periodic garbage collection in your main loop
        if t % 1000 == 0:
            gc.collect()
        t += 1

        time.sleep_ms(2)


# Start the second core for button control
_thread.start_new_thread(led_loop, ())


# Run main loop on core 0
button_control()
