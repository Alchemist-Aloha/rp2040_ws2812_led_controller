import machine
import neopixel
import math
import mp_time as time
import _thread
import os
import ujson
from ssd1306 import SSD1306_I2C
from ir_buttons import (
    IR_NONE,
    IR_POWER,
    IR_MENU,
    IR_PLUS,
    IR_MINUS,
    IR_LEFT,
    IR_RIGHT,
    IR_PLAY,
    IR_BACK,
    IR_1,
    IR_2,
    IR_3,
    IR_4,
)
import gc

gc.collect()  # Force garbage collection at startup
# from irrecvdata import irGetCMD

machine.freq(200000000)

# Constants
PIN_LED = 15
NUM_LEDS = 60
OLED_SDA = 6
OLED_SCL = 7
OLED_I2C_FREQ = 400000
OLED_CONTRAST = 160
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
i2c_1 = machine.I2C(
    1,
    sda=machine.Pin(OLED_SDA),
    scl=machine.Pin(OLED_SCL),
    freq=OLED_I2C_FREQ,
)
oled = SSD1306_I2C(128, 64, i2c_1)
oled.contrast(OLED_CONTRAST)
oled.fill(0)
oled.show()

humansensor_read = machine.Pin(14, machine.Pin.IN)

# Shared variables
persist_multiplier = 0
brightness = 1
color_mode = 0

CONFIG_FILE = "light_config.json"
CONFIG_TEMP_FILE = "light_config.tmp"

SCREEN_TIMEOUT_MS = 15000
SCREEN_STATUS_REFRESH_MS = 1000
SCREEN_ERROR_RETRY_MS = 1000
UI_HOME = 0
UI_MAIN_MENU = 1
UI_BRIGHTNESS = 2
UI_RUN_MODE = 3
UI_COLOR_MODE = 4

# Keep names short enough for the 128-pixel OLED.  The first entry preserves
# the original warm-white animation as the default.
COLOR_MODES = (
    "Warm white",
    "Soft white",
    "Daylight",
    "Red",
    "Green",
    "Blue",
    "Cyan",
    "Magenta",
    "Yellow",
    "Orange",
    "Purple",
    "Pink",
    "Breathing",
    "Rainbow wave",
    "Rainbow cycle",
    "Color chase",
    "Theater chase",
    "Comet",
    "Twinkle",
    "Fire",
    "Ocean wave",
    "Forest wave",
    "Police",
    "Color wipe",
)


def load_config():
    """Load saved settings, keeping safe defaults if the file is invalid."""
    global brightness, persist_multiplier, color_mode

    for filename in (CONFIG_FILE, CONFIG_TEMP_FILE):
        try:
            with open(filename, "r") as config_file:
                config = ujson.load(config_file)

            saved_brightness = config.get("brightness")
            saved_run_mode = config.get("run_mode")
            saved_color_mode = config.get("color_mode")
            if not isinstance(saved_brightness, (int, float)):
                raise ValueError("invalid brightness")
            if not 0.05 <= saved_brightness <= 1:
                raise ValueError("brightness out of range")
            if saved_run_mode not in (0, 1, 2):
                raise ValueError("invalid run mode")
            if not isinstance(saved_color_mode, int):
                raise ValueError("invalid color mode")
            if not 0 <= saved_color_mode < len(COLOR_MODES):
                raise ValueError("color mode out of range")

            brightness = round(saved_brightness, 2)
            persist_multiplier = saved_run_mode
            color_mode = saved_color_mode
            print("Loaded settings from", filename)
            return
        except OSError:
            pass
        except (ValueError, TypeError) as error:
            print("Ignoring invalid settings in", filename, ":", error)


def save_config():
    """Save committed settings using a temporary file for safer updates."""
    config = {
        "brightness": brightness,
        "run_mode": persist_multiplier,
        "color_mode": color_mode,
    }
    try:
        try:
            os.remove(CONFIG_TEMP_FILE)
        except OSError:
            pass
        with open(CONFIG_TEMP_FILE, "w") as config_file:
            ujson.dump(config, config_file)

        try:
            os.remove(CONFIG_FILE)
        except OSError:
            pass
        os.rename(CONFIG_TEMP_FILE, CONFIG_FILE)
        print("Settings saved")
        return True
    except OSError as error:
        print("Error saving settings:", error)
        return False


load_config()

STATIC_COLORS = (
    (255, 170, 80),   # Soft white
    (210, 230, 255),  # Daylight
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (0, 255, 255),
    (255, 0, 255),
    (255, 220, 0),
    (255, 80, 0),
    (145, 0, 255),
    (255, 20, 100),
)

IR_COMMANDS = (
    IR_POWER,
    IR_MENU,
    IR_PLUS,
    IR_MINUS,
    IR_LEFT,
    IR_RIGHT,
    IR_PLAY,
    IR_BACK,
    IR_1,
    IR_2,
    IR_3,
    IR_4,
)

# UI state is written by the button core and read by the display core. Each
# assignment is atomic on MicroPython, and ui_revision requests a redraw.
screen_on = True
last_ui_action_time = time.ticks_ms()
ui_view = UI_HOME
main_menu_index = 0
brightness_draft = brightness
run_mode_draft = persist_multiplier
color_mode_draft = color_mode
ui_revision = 0


def handle_ui_button(button_number):
    """Handle one UI button press. Returns True when the press only wakes OLED."""
    global screen_on, last_ui_action_time, ui_view, main_menu_index
    global brightness_draft, run_mode_draft, brightness, persist_multiplier
    global color_mode, color_mode_draft, ui_revision

    last_ui_action_time = time.ticks_ms()
    if not screen_on:
        screen_on = True
        ui_revision += 1
        return True

    if ui_view == UI_HOME:
        if button_number in (1, 2, 3):
            ui_view = UI_MAIN_MENU
            if button_number == 2:
                main_menu_index = 1

    elif ui_view == UI_MAIN_MENU:
        if button_number == 1:
            main_menu_index = (main_menu_index - 1) % 3
        elif button_number == 2:
            main_menu_index = (main_menu_index + 1) % 3
        elif button_number == 3:
            if main_menu_index == 0:
                brightness_draft = brightness
                ui_view = UI_BRIGHTNESS
            elif main_menu_index == 1:
                run_mode_draft = persist_multiplier
                ui_view = UI_RUN_MODE
            else:
                color_mode_draft = color_mode
                ui_view = UI_COLOR_MODE
        elif button_number == 4:
            ui_view = UI_HOME

    elif ui_view == UI_BRIGHTNESS:
        if button_number == 1:
            brightness_draft = round(min(1, brightness_draft + 0.05), 2)
        elif button_number == 2:
            brightness_draft = round(max(0.05, brightness_draft - 0.05), 2)
        elif button_number == 3:
            brightness = brightness_draft
            save_config()
            ui_view = UI_MAIN_MENU
            print("Brightness:", int(brightness * 100), "%")
        elif button_number == 4:
            brightness_draft = brightness
            ui_view = UI_MAIN_MENU

    elif ui_view == UI_RUN_MODE:
        if button_number == 1:
            run_mode_draft = (run_mode_draft - 1) % 3
        elif button_number == 2:
            run_mode_draft = (run_mode_draft + 1) % 3
        elif button_number == 3:
            persist_multiplier = run_mode_draft
            save_config()
            ui_view = UI_MAIN_MENU
            print("Run mode:", mode_name(persist_multiplier))
        elif button_number == 4:
            run_mode_draft = persist_multiplier
            ui_view = UI_MAIN_MENU

    elif ui_view == UI_COLOR_MODE:
        if button_number == 1:
            color_mode_draft = (color_mode_draft - 1) % len(COLOR_MODES)
        elif button_number == 2:
            color_mode_draft = (color_mode_draft + 1) % len(COLOR_MODES)
        elif button_number == 3:
            color_mode = color_mode_draft
            save_config()
            ui_view = UI_MAIN_MENU
            print("Color mode:", COLOR_MODES[color_mode])
        elif button_number == 4:
            color_mode_draft = color_mode
            ui_view = UI_MAIN_MENU

    ui_revision += 1
    return True


def mode_name(mode):
    if mode == 1:
        return "Always on"
    if mode == 2:
        return "Always off"
    return "Human detect"


def draw_ui(temperature):
    """Draw the current UI into the framebuffer; caller sends it with show()."""
    oled.fill(0)

    if ui_view == UI_HOME:
        oled.text("Light Control", 0, 0)
        oled.text("Mode:", 0, 16)
        oled.text(mode_name(persist_multiplier), 40, 16)
        oled.text("Brightness: " + str(round(brightness * 100)) + "%", 0, 28)
        oled.text("Color: " + COLOR_MODES[color_mode], 0, 40)
        oled.text("Temp:" + str(temperature) + "C B3 Menu", 0, 54)

    elif ui_view == UI_MAIN_MENU:
        oled.text("Main Menu", 0, 0)
        oled.text(("> " if main_menu_index == 0 else "  ") + "Brightness", 0, 14)
        oled.text(("> " if main_menu_index == 1 else "  ") + "Run mode", 0, 26)
        oled.text(("> " if main_menu_index == 2 else "  ") + "Color mode", 0, 38)
        oled.text("B3 Select B4 Back", 0, 54)

    elif ui_view == UI_BRIGHTNESS:
        oled.text("Brightness", 0, 0)
        oled.text(str(round(brightness_draft * 100)) + "%", 48, 20)
        oled.text("B1 +     B2 -", 0, 38)
        oled.text("B3 Save B4 Back", 0, 54)

    elif ui_view == UI_RUN_MODE:
        oled.text("Run mode", 0, 0)
        modes = ("Human detect", "Always on", "Always off")
        for index in range(3):
            marker = "> " if run_mode_draft == index else "  "
            oled.text(marker + modes[index], 0, 16 + index * 12)
        oled.text("B3 Save B4 Back", 0, 54)

    elif ui_view == UI_COLOR_MODE:
        oled.text("Color mode", 0, 0)
        oled.text(
            str(color_mode_draft + 1) + "/" + str(len(COLOR_MODES)),
            88,
            0,
        )
        oled.text(COLOR_MODES[color_mode_draft], 0, 22)
        oled.text("B1 Prev  B2 Next", 0, 40)
        oled.text("B3 Save B4 Back", 0, 54)


def button_control():
    ir_value = IR_NONE
    uart_buffer = ""
    last_button_time = 0
    debounce_time = 200  # ms
    buttons = (
        (button_1, 1),
        (button_2, 2),
        (button_3, 3),
        (button_4, 4),
    )
    remote_buttons = {
        # Previous / increase
        IR_LEFT: 1,
        IR_PLUS: 1,
        IR_1: 1,
        # Next / decrease
        IR_RIGHT: 2,
        IR_MINUS: 2,
        IR_2: 2,
        # Open / select / save
        IR_PLAY: 3,
        IR_MENU: 3,
        IR_3: 3,
        # Back / cancel
        IR_BACK: 4,
        IR_POWER: 4,
        IR_4: 4,
    }
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
                            print("UART0 IR command:", command)
                            ir_value = command
                            uart_buffer = ""
                            break
            except UnicodeDecodeError:
                uart_buffer = ""

        current_values = [button.value() for button, _ in buttons]
        pressed_button = remote_buttons.get(ir_value)

        # Trigger physical buttons only on the pressed edge. This prevents a
        # held mode button from toggling repeatedly every debounce interval.
        if pressed_button is None:
            for index, (_, button_number) in enumerate(buttons):
                if previous_values[index] == 1 and current_values[index] == 0:
                    pressed_button = button_number
                    break

        if time.ticks_diff(current_time, last_button_time) > debounce_time:
            if pressed_button is not None and handle_ui_button(pressed_button):
                last_button_time = current_time
                ir_value = IR_NONE

        previous_values = current_values
        time.sleep_ms(10)


def color_wheel(position):
    """Return a full-brightness RGB color for a wheel position from 0 to 255."""
    position %= 256
    if position < 85:
        return (255 - position * 3, position * 3, 0)
    if position < 170:
        position -= 85
        return (0, 255 - position * 3, position * 3)
    position -= 170
    return (position * 3, 0, 255 - position * 3)


def scaled_color(color, level=1):
    scale = brightness * level
    return (
        int(color[0] * scale),
        int(color[1] * scale),
        int(color[2] * scale),
    )


def render_color_mode(frame, led_buffer):
    """Render the selected color mode into the reusable LED buffer."""
    mode = color_mode
    phase = frame // 4

    if mode == 0:  # Original warm-white moving/breathing effect
        breath = 0.8 + 0.2 * math.sin(frame * math.pi / 400)
        color = scaled_color((
            235 - 20 * math.sin(frame * math.pi / 250),
            100 - 20 * math.sin(frame * math.pi / 200),
            59 + 10 * math.sin(frame * math.pi / 300),
        ), breath)
        for i in range(NUM_LEDS - 1):
            led_buffer[i] = led_buffer[i + 1]
        led_buffer[-1] = color
    elif 1 <= mode <= 11:
        color = scaled_color(STATIC_COLORS[mode - 1])
        for i in range(NUM_LEDS):
            led_buffer[i] = color
    elif mode == 12:  # Breathing
        level = 0.12 + 0.88 * (math.sin(frame * math.pi / 250) + 1) / 2
        color = scaled_color((80, 120, 255), level)
        for i in range(NUM_LEDS):
            led_buffer[i] = color
    elif mode in (13, 14):  # Rainbow wave / rainbow cycle
        spread = 256 // NUM_LEDS if mode == 13 else 0
        for i in range(NUM_LEDS):
            led_buffer[i] = scaled_color(color_wheel(phase + i * spread))
    elif mode == 15:  # Color chase
        for i in range(NUM_LEDS):
            led_buffer[i] = scaled_color(
                color_wheel(phase * 3 + i * 20) if (i + phase) % 5 == 0
                else (0, 0, 0)
            )
    elif mode == 16:  # Theater chase
        color = scaled_color(color_wheel(phase))
        for i in range(NUM_LEDS):
            led_buffer[i] = color if (i + phase) % 3 == 0 else (0, 0, 0)
    elif mode == 17:  # Comet
        head = phase % (NUM_LEDS + 12)
        for i in range(NUM_LEDS):
            distance = head - i
            level = (12 - distance) / 12 if 0 <= distance < 12 else 0
            led_buffer[i] = scaled_color((80, 180, 255), level)
    elif mode == 18:  # Deterministic twinkle, no random-module allocation
        for i in range(NUM_LEDS):
            sparkle = ((i * 37 + phase * 13) % 101) < 4
            led_buffer[i] = scaled_color((220, 235, 255), 1 if sparkle else 0.04)
    elif mode == 19:  # Fire
        for i in range(NUM_LEDS):
            flicker = (i * 29 + phase * 17 + (i * phase) % 31) % 100
            led_buffer[i] = scaled_color((255, 25 + flicker, flicker // 8))
    elif mode in (20, 21):  # Ocean wave / forest wave
        base = (0, 90, 255) if mode == 20 else (0, 210, 55)
        for i in range(NUM_LEDS):
            level = 0.35 + 0.65 * (
                math.sin((i * 12 + phase * 3) * math.pi / 128) + 1
            ) / 2
            led_buffer[i] = scaled_color(base, level)
    elif mode == 22:  # Police
        first_color = (255, 0, 0) if (phase // 8) % 2 == 0 else (0, 0, 255)
        second_color = (0, 0, 255) if first_color[0] else (255, 0, 0)
        for i in range(NUM_LEDS):
            led_buffer[i] = scaled_color(
                first_color if i < NUM_LEDS // 2 else second_color
            )
    else:  # Color wipe
        wipe_position = phase % (NUM_LEDS * 3)
        wipe_color = color_wheel((phase // NUM_LEDS) * 85)
        for i in range(NUM_LEDS):
            led_buffer[i] = scaled_color(wipe_color) if i <= wipe_position % NUM_LEDS else (0, 0, 0)


def led_loop():
    global persist_multiplier, brightness, screen_on
    t = 0
    previous_state = -1  # Track previous state
    rendered_ui_revision = -1
    last_display_refresh = time.ticks_ms()
    last_display_error = None
    display_powered = True
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

        if screen_on and time.ticks_diff(
            time.ticks_ms(), last_ui_action_time
        ) >= SCREEN_TIMEOUT_MS:
            screen_on = False

        # A display failure must not prevent the lights from operating or cause
        # a tight I2C retry loop that can keep a failing bus continuously busy.
        display_retry_ready = (
            last_display_error is None
            or time.ticks_diff(time.ticks_ms(), last_display_error)
            >= SCREEN_ERROR_RETRY_MS
        )
        if display_retry_ready:
            try:
                if not screen_on and display_powered:
                    oled.poweroff()
                    display_powered = False
                elif screen_on:
                    if not display_powered:
                        oled.poweron()
                        display_powered = True
                        rendered_ui_revision = -1

                    refresh_due = time.ticks_diff(
                        time.ticks_ms(), last_display_refresh
                    ) >= SCREEN_STATUS_REFRESH_MS
                    if (
                        state_changed
                        or rendered_ui_revision != ui_revision
                        or (ui_view == UI_HOME and refresh_due)
                    ):
                        draw_ui(temperature)
                        oled.show()
                        rendered_ui_revision = ui_revision
                        last_display_refresh = time.ticks_ms()
                last_display_error = None
            except Exception as e:
                last_display_error = time.ticks_ms()
                print("Error updating display:", e)

        try:
            if current_state:  # Human detected or always on
                render_color_mode(t, led_buffer)
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
