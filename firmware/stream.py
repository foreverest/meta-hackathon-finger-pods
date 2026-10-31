"""Finger Pods streaming firmware for an Adafruit QT Py (CircuitPython).

Streams synchronised magnetometer + button readings to the host over USB
serial as CSV, as fast as the I2C bus allows (no fixed sleep). Copy this
file to the board as ``code.py``, together with ``button_latch.py``.

Button latency: buttons are polled after every single magnetometer
read (not once per cycle) and every observed press is latched until it
has been emitted once, so a quick tap cannot fall between samples. A
sample is also emitted immediately when a new press is latched, using
the most recent magnetometer values (some up to one cycle old). The
magnetometers run with a fast conversion setting (see MAG_FILTER /
MAG_OVERSAMPLING below): with the library defaults one read blocks
~220 ms and a whole cycle ~0.7 s, which made short presses invisible.

Wiring (as assembled on Day 3):
  * QT Py STEMMA QT port -> PCA9546A I2C multiplexer (0x70), with one
    MLX90393 magnetometer on each of three multiplexer channels
    (thumb, middle, ring fingers; magnets are on index and pinky).
  * Nine tactile buttons, each wired between a GPIO pin and GND
    (internal pull-up, so "pressed" reads LOW on the pin).

Output protocol (one line per sample, 115200 baud):
  * Lines starting with ``#`` are human-readable diagnostics.
  * Data lines are CSV:
      t_ms,m0x,m0y,m0z,m1x,m1y,m1z,m2x,m2y,m2z,b0,b1,b2,b3,b4,b5,b6,b7,b8
    ``t_ms`` is milliseconds since boot, magnetometer values are in
    microtesla (uT), and button values are 1 = pressed, 0 = released.
    Magnetometers appear in multiplexer-channel order; the ``# sensors``
    diagnostic at startup says which channel each group belongs to.

IMPORTANT -- button order: ``BUTTON_PIN_NAMES`` below defines which GPIO
each of the nine buttons (b0..b8) is read from, in order. Edit that tuple
so the order matches the physical wiring (e.g. thumb..pinky). The host
tools treat the button index as a feature, so any consistent order works,
but it must not change between data collection and live use.

Requires in ``lib`` on the CIRCUITPY drive: ``adafruit_mlx90393`` and
``adafruit_tca9548a`` (plus ``adafruit_bus_device`` / ``adafruit_register``).
"""

import time

import board
import digitalio
import adafruit_mlx90393
import adafruit_tca9548a

import button_latch

# --- Buttons -------------------------------------------------------------
# QT Py GPIO candidates that do not clash with the STEMMA QT I2C pins
# (SCL/SDA). Edit the order to match the physical wiring; missing pin
# names on a given QT Py variant are skipped with a diagnostic.
BUTTON_PIN_NAMES = ("A0", "A1", "A2", "A3", "TX", "RX", "SCK", "MOSI", "MISO")

MLX90393_ADDRESSES = (0x0C, 0x0D, 0x0E, 0x0F, 0x18, 0x19, 0x1A, 0x1B)

# Magnetometer conversion speed. The MLX90393 driver sleeps for the
# conversion time on every read; the datasheet lookup is roughly:
#   FILTER_7/OSR_3 (library default): ~200 ms per read  -> unusable
#   FILTER_2/OSR_1 (below):           ~3 ms per read
#   FILTER_0/OSR_0 (fastest):         ~1.3 ms per read, noisier
# Gain/resolution are untouched, so values stay in the same uT scale;
# lower filter/oversampling only trades a little noise for speed.
MAG_FILTER = 2        # adafruit_mlx90393.FILTER_2
MAG_OVERSAMPLING = 1  # adafruit_mlx90393.OSR_1


def _transceive_with_timeout(self, payload, rxlen=0):
    """Repeated-start version of the MLX90393 library's ``_transceive``.

    The library version writes multi-byte payloads (register writes)
    with a STOP and then does a naked read for the status byte; some
    MLX90393 units NAK that read indefinitely through the mux
    (Errno 19 during initialisation -- confirmed on the Day-3 rig,
    where ``write_then_readinto`` fixed it). The datasheet only
    documents repeated-start sequences, so this version uses
    ``write_then_readinto`` for every payload. A NAK then raises
    ``OSError`` promptly instead of the library's infinite retry, and
    the caller can skip that sensor for this sample.
    """
    data = bytearray(rxlen + 1)
    with self.i2c_device as i2c:
        i2c.write_then_readinto(payload, data)
    self._status_last = data[0]
    return data


adafruit_mlx90393.MLX90393._transceive = _transceive_with_timeout


def setup_buttons():
    buttons = []
    for name in BUTTON_PIN_NAMES:
        pin = getattr(board, name, None)
        if pin is None:
            print("# button pin", name, "not available on this board - skipped")
            continue
        btn = digitalio.DigitalInOut(pin)
        btn.switch_to_input(pull=digitalio.Pull.UP)
        buttons.append(btn)
    print("# buttons:", len(buttons), "on pins", BUTTON_PIN_NAMES[: len(buttons)])
    return buttons


def _force_unlock(i2c):
    try:
        i2c.unlock()
    except Exception:
        pass


def _unlock_channel(bus, i2c):
    # Channel unlock writes to the mux first; if the mux is not talking
    # that raises and the main bus would stay locked, so fall back to
    # unlocking the main bus directly.
    try:
        bus.unlock()
    except OSError:
        _force_unlock(i2c)


def setup_magnetometers(i2c):
    # Scan the main bus first, exactly like magnetometer_test.py did.
    # The mux should appear as 0x70. Retried: a wedged bus (e.g. SDA
    # held low) reports OSError ETIMEDOUT here instead of scanning.
    for attempt in range(3):
        try:
            while not i2c.try_lock():
                pass
            try:
                print("# QT Py I2C scan",
                      [hex(a) for a in i2c.scan()])
            finally:
                i2c.unlock()
            break
        except OSError as error:
            print("# main I2C scan failed -", error,
                  "- retry", attempt + 1, "of 3")
            _force_unlock(i2c)
            time.sleep(0.5)

    mux = adafruit_tca9548a.PCA9546A(i2c)  # default multiplexer address 0x70
    sensors = []
    for channel in range(4):
        bus = mux[channel]
        # try_lock() also selects the channel on the mux; if the mux
        # does not ACK, the library raises OSError ETIMEDOUT instead of
        # returning False. Skip that channel instead of crashing.
        try:
            bus.try_lock()
        except OSError as error:
            print("# channel", channel, "select failed -", error,
                  "(mux not responding on this channel, skipping)")
            _force_unlock(i2c)
            time.sleep(0.1)
            continue
        try:
            found = [a for a in bus.scan() if a != 0x70]
            print("# channel", channel, "I2C scan",
                  [hex(a) for a in found])
        except OSError as error:
            print("# channel", channel, "scan failed -", error)
            found = []
        finally:
            _unlock_channel(bus, i2c)
        for address in found:
            if address not in MLX90393_ADDRESSES:
                continue
            try:
                sensor = adafruit_mlx90393.MLX90393(bus, address=address)
                # Fast conversion (see MAG_FILTER above). Best-effort:
                # a sensor that rejects the setting still works, just
                # at the slow default rate.
                try:
                    sensor.filter = MAG_FILTER
                    sensor.oversampling = MAG_OVERSAMPLING
                except (ValueError, OSError) as error:
                    print("# channel", channel,
                          "fast conversion setting failed -", error)
            except (ValueError, OSError) as error:
                print("# channel", channel, "magnetometer failed -", error)
                continue
            sensors.append((channel, sensor))
            break
    print("# sensors on multiplexer channels", [ch for ch, _ in sensors])
    return sensors


try:
    i2c = board.STEMMA_I2C()
except AttributeError:
    i2c = board.I2C()

# Magnetometers first, buttons second: this matches the known-working
# magnetometer_test.py (which never touches GPIO). If configuring the
# button pins breaks I2C -- e.g. a button wired to a pin that shares
# the STEMMA I2C lines, held to GND -- the sanity read after button
# setup will fail below and say so, instead of a bare traceback.
sensors = setup_magnetometers(i2c)
buttons = setup_buttons()

if not sensors:
    raise RuntimeError(
        "No MLX90393 found - see the scan lines above: the mux (0x70) "
        "must appear in the QT Py I2C scan, and each sensor in its "
        "channel scan. Check the STEMMA cable to the mux and mux power.")
if not buttons:
    raise RuntimeError("No button pins available - check BUTTON_PIN_NAMES")

for channel, sensor in sensors:
    try:
        sensor.magnetic
        print("# post-button-setup mag read OK on channel", channel)
    except OSError as error:
        print("# WARNING: mag read on channel", channel,
              "failed AFTER button setup -", error,
              "- a button pin likely conflicts with the I2C lines "
              "(check BUTTON_PIN_NAMES / wiring for SCL/SDA shorts)")

header = ["t_ms"]
for i in range(len(sensors)):
    header += ["m%dx" % i, "m%dy" % i, "m%dz" % i]
header += ["b%d" % i for i in range(len(buttons))]
print("# " + ",".join(header))
print("# streaming - one CSV line per sample")

print("# mag conversion: filter", MAG_FILTER,
      "oversampling", MAG_OVERSAMPLING, "(~3 ms per sensor read)")

start = time.monotonic()
latch = button_latch.PressLatch(len(buttons))
mag_cache = [0.0] * (3 * len(sensors))


def read_buttons():
    return [0 if btn.value else 1 for btn in buttons]  # pressed = LOW


def emit_sample():
    states = read_buttons()
    latch.poll(states)
    out = latch.take_output(states)
    values = [str(int((time.monotonic() - start) * 1000))]
    values += ["%.2f" % v for v in mag_cache]
    values += [str(b) for b in out]
    print(",".join(values))


while True:
    for idx, (_channel, sensor) in enumerate(sensors):
        try:
            mx, my, mz = sensor.magnetic
            mag_cache[3 * idx:3 * idx + 3] = [mx, my, mz]
        except OSError:
            # A failed transfer can leave the main bus locked inside
            # the mux-channel lock; release it so the next read is not
            # stuck spinning forever. Keep the last good values.
            _force_unlock(i2c)
        # Poll buttons between sensor reads: this bounds press
        # detection latency to one sensor read (~ms), and the latch
        # guarantees a tap seen here survives until it is emitted.
        latch.poll(read_buttons())
        if latch.pending:
            emit_sample()  # new press: emit now, don't wait for cycle end
    emit_sample()
