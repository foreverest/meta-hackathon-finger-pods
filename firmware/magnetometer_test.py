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

Copy this file to the board as ``code.py``, open the board in the Mu
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

MLX90393_ADDRESSES = (0x0C, 0x0D, 0x0E, 0x0F, 0x18, 0x19, 0x1A, 0x1B)


def _transceive_with_timeout(self, payload, rxlen=0):
    """Bounded version of the MLX90393 library's ``_transceive``.

    The library version retries a register read forever while the sensor
    returns a zero status byte, so one unresponsive magnetometer hangs
    the whole script with no output. This version gives up after one
    second and raises ``OSError`` instead, so the caller can skip that
    sensor and carry on with the others.
    """
    data = bytearray(rxlen + 1)
    if len(payload) == 1:
        with self.i2c_device as i2c:
            i2c.write_then_readinto(payload, data)
    else:
        with self.i2c_device as i2c:
            i2c.write(payload)
            start = time.monotonic()
            while True:
                try:
                    i2c.readinto(data)
                    if data[0]:
                        break
                except OSError:
                    if time.monotonic() - start > 1.0:
                        raise
                if time.monotonic() - start > 1.0:
                    raise OSError("MLX90393 status byte stayed zero for 1 s")
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
sensors = []
for channel in range(4):
    bus = mux[channel]
    while not bus.try_lock():
        pass
    try:
        found = [address for address in bus.scan() if address != 0x70]
    finally:
        bus.unlock()
    print(f"Multiplexer channel {channel} I2C scan", [hex(a) for a in found])
    for address in found:
        if address not in MLX90393_ADDRESSES:
            continue
        print("Trying MLX90393 on channel", channel, "at", hex(address))
        try:
            sensor = adafruit_mlx90393.MLX90393(bus, address=address)
        except (ValueError, OSError) as error:
            print("Channel", channel, "magnetometer failed -", error)
            continue
        print("Channel", channel, "magnetometer OK")
        sensors.append((channel, sensor))
        break

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
