"""Quick tactile-button test for an Adafruit QT Py (CircuitPython).

Wire each button between a GPIO pin and GND (uses the internal pull-up,
so no external resistor is needed), copy this file to the board as
``code.py``, and open the serial console. Pressing a button pulls the
pin LOW, so "pressed" reads as False.
"""

import board
import digitalio
import time

btn = digitalio.DigitalInOut(board.A0)  # change to the GPIO pin under test
btn.switch_to_input(pull=digitalio.Pull.UP)

while True:
    print("PRESSED" if not btn.value else "released")
    time.sleep(0.1)
