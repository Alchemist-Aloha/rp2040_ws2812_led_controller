# Pico Light Bulbs Project

This MicroPython project is designed to control light bulbs using a Raspberry Pi Pico. It includes features such as human detection and brightness control using buttons or an infrared remote. To enhance quality of the IR reception, a [second Pico](https://github.com/Alchemist-Aloha/pico_ir_receiver) is used to receive the IR signals and send them to the main Pico via UART. The project also includes an OLED display to show the current mode of operation.

## Hardware
- **Raspberry Pi Pico**: Main microcontroller.
- **LD2410 Human Sensor**: Human detection sensor.
- **SSD1306 OLED Display**: For displaying information.
- **WS2812 LED Strip**: RGB LED strip.

## Project Structure

- **ld2410.py**: Manages communication with the LD2410 sensor.
- **main.py**: Main script to control the light bulbs, handle button inputs, and display information on the OLED screen.
- **ssd1306.py**: Driver for the SSD1306 OLED display.

## Usage

- **Buttons**:
  - Button 1: Increase brightness.
  - Button 2: Decrease brightness.
  - Button 3: Switch to human sensor mode.
- Button 4: Toggle between always on and always off modes.

## OLED settings

Press Button 3 from the home screen to open the settings menu. Button 1 and
Button 2 move through items or values, Button 3 selects/saves, and Button 4
goes back.

The **Color mode** subpage includes 24 choices: warm white, soft white,
daylight, red, green, blue, cyan, magenta, yellow, orange, purple, pink,
breathing, rainbow wave, rainbow cycle, color chase, theater chase, comet,
twinkle, fire, ocean wave, forest wave, police, and color wipe.

Selecting **Save** stores the brightness, run mode, and color mode in
`light_config.json` on the Pico. These settings are loaded automatically on
the next startup. If the saved file is missing or invalid, the built-in
defaults are used.

## License

This project is licensed under the MIT License.
