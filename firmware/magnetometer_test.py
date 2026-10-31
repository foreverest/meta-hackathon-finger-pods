"""Magnetometer test for an Adafruit QT Py (CircuitPython).

Wiring (as assembled on Day 3): the QT Py STEMMA QT port connects to a
PCA9546A I2C multiplexer, and one MLX90393 magnetometer is plugged into
each of three multiplexer channels. The multiplexer is needed because
the MLX90393s would otherwise all share the same I2C address.

MLX90393 address: older Adafruit breakouts default to 0x0C, breakouts
shipped since May 2023 default to 0x18, and the A0/A1 jumpers can shift
either base by 0-3. This script therefore scans each multiplexer channel
and tries every MLX90393 address it finds (0x0C-0x0F and 0x18-0x1B), so
it works with either version and any jumper setting.

Requires these libraries in the ``lib`` folder on the CIRCUITPY drive:
``adafruit_mlx90393`` and ``adafruit_tca9548a`` (plus their dependencies,
``adafruit_bus_device`` and ``adafruit_register``).

Copy this file to the board as ``code.py`` and ``sensor_discovery.py``
next to it (board root, not ``lib``), open the board in the Mu
editor, open the Serial/REPL, and click Plotter. The Mu plotter only
plots Python tuples, so one tuple is printed every second with the
X/Y/Z field of every magnetometer found, in microtesla (uT), e.g.
``(12.34, -5.67, 89.01, ...)``. At startup the script prints which
multiplexer channel each group of three values (X, Y, Z) belongs to --
the plotter itself only shows the values in that order.

At startup the script also prints the I2C addresses seen on the QT Py
bus and on each multiplexer channel. If no magnetometer is found,
share those lines -- they show whether the multiplexer (0x70) and the
sensors are visible.
"""

import time

import board
import adafruit_mlx90393
import adafruit_tca9548a

import sensor_discovery

MLX90393_ADDRESSES = (0x0C, 0x0D, 0x0E, 0x0F, 0x18, 0x19, 0x1A, 0x1B)


def _transceive_with_timeout(self, payload, rxlen=0):
    """Bounded, repeated-start version of the library's ``_transceive``.

    Two deviations from the library version, both seen on the mux:

    * Multi-byte payloads (register writes) use ``write_then_readinto``
      (repeated start, no STOP between write and status read). The
      library writes with a STOP and then does a naked read for the
      status byte; some MLX90393 units NAK that read indefinitely
      through the mux (Errno 19 during initialisation), while the
      datasheet only documents repeated-start sequences.
    * The single-byte path is bounded like before: the library retries
      a zero status byte forever, hanging the script; this version is
      a single transaction, so a NAK raises ``OSError`` promptly and
      the caller (sensor discovery) can retry or skip that sensor.
    """
    data = bytearray(rxlen + 1)
    with self.i2c_device as i2c:
        i2c.write_then_readinto(payload, data)
    self._status_last = data[0]
    return data


adafruit_mlx90393.MLX90393._transceive = _transceive_with_timeout

try:
    i2c = board.STEMMA_I2C()  # QT Py built-in STEMMA QT connector
except AttributeError:
    i2c = board.I2C()

# Show what is on the QT Py bus itself. The multiplexer is 0x70.
while not i2c.try_lock():
    pass
try:
    print("QT Py I2C scan", [hex(address) for address in i2c.scan()])
finally:
    i2c.unlock()

mux = adafruit_tca9548a.PCA9546A(i2c)  # default multiplexer address 0x70

# Find the magnetometers by scanning each multiplexer channel.
# Sensor init is retried (per-attempt and in a second pass): with 2+
# sensors on the mux, one can answer the scan but NAK during MLX90393
# initialisation (Errno 19), and a one-shot attempt drops it.
# Diagnostic: if a sensor still fails, the traceback printed on its
# first attempt names the exact adafruit_mlx90393.py line/transaction
# being NAK'd. To test whether the failure follows initialisation
# ORDER or a physical channel/sensor, temporarily reverse this:
# CHANNEL_ORDER = (3, 2, 1, 0) -- if channel 2 then initialises and
# channel 0 fails instead, it is order/state; if channel 2 fails
# even when initialised first, it is that channel/sensor/cable.
CHANNEL_ORDER = (0, 1, 2, 3)
sensors = sensor_discovery.discover_sensors(
    mux, adafruit_mlx90393.MLX90393, MLX90393_ADDRESSES,
    channels=CHANNEL_ORDER, show_traceback=True)

if not sensors:
    raise RuntimeError(
        "No MLX90393 found - check the scan lines above "
        "(multiplexer 0x70 and sensors 0x0C-0x0F / 0x18-0x1B expected)"
    )

print("MLX90393 found on multiplexer channels", [ch for ch, _ in sensors])
print(
    "Tuple order",
    ", ".join(f"mux{channel} X/Y/Z" for channel, _ in sensors),
)

while True:
    values = []
    for channel, sensor in sensors:
        mx, my, mz = sensor.magnetic  # X, Y, Z in microtesla
        values.append(round(mx, 2))
        values.append(round(my, 2))
        values.append(round(mz, 2))
    # The Mu plotter plots lines that are Python tuples of numbers.
    print(tuple(values))
    time.sleep(1.0)
