# Pico Light Bulbs Project

This project is designed to control light bulbs using a Raspberry Pi Pico. It includes features such as temperature sensing, human detection, and brightness control using buttons and an infrared remote. To enhance quality of the IR reception, a second Pico is used to receive the IR signals and send them to the main Pico via UART. The project also includes an OLED display to show the current mode of operation.

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

## License

This project is licensed under the MIT License.
