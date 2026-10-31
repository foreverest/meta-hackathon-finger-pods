"""Magnetometer discovery on the PCA9546A multiplexer.

Shared by the firmware scripts. Kept free of board imports so the
discovery logic can be unit-tested on a desktop with fake buses.

Why retries: with two or more MLX90393s on the mux, a sensor can
answer the channel scan but then NAK a transaction during
``MLX90393(...)`` initialisation (``OSError: [Errno 19] No such
device``), so a one-shot attempt drops a healthy sensor. Retrying
the whole constructor (which re-runs the sensor reset), and then
retrying the whole channel in a later discovery pass, recovers
sensors whose failure is timing/state dependent. A sensor that
fails every attempt in every pass is skipped so the remaining
sensors still work.
"""

import time

INIT_ATTEMPTS = 4
INIT_RETRY_DELAY_S = 0.1
DISCOVERY_PASSES = 2
PASS_DELAY_S = 0.5


def _sleep(sleep, seconds):
    (sleep if sleep is not None else time.sleep)(seconds)


def _print_exception(error):
    """Best-effort traceback print on both CPython and CircuitPython."""
    try:
        import traceback

        try:
            traceback.print_exception(type(error), error,
                                      error.__traceback__)
        except TypeError:
            traceback.print_exception(error)
    except Exception:
        try:
            import sys

            sys.print_exception(error)
        except Exception:
            print("exception:", repr(error))


def create_sensor_with_retries(bus, address, create_sensor,
                               attempts=INIT_ATTEMPTS,
                               retry_delay_s=INIT_RETRY_DELAY_S,
                               sleep=None, log=print,
                               show_traceback=False):
    """Create one sensor, retrying transient init failures.

    ``create_sensor`` is called as ``create_sensor(bus, address=...)``
    (the ``adafruit_mlx90393.MLX90393`` constructor on the board).
    Returns the sensor, or None if every attempt failed. With
    ``show_traceback``, the first failure prints a full traceback --
    the line inside ``adafruit_mlx90393.py`` identifies exactly which
    init transaction (reset, register read/write) is being NAK'd.
    """
    for attempt in range(1, attempts + 1):
        try:
            return create_sensor(bus, address=address)
        except (ValueError, OSError) as error:
            log("magnetometer init attempt", attempt, "of", attempts,
                "at", hex(address), "failed -", error)
            if attempt == 1 and show_traceback:
                _print_exception(error)
            if attempt < attempts:
                _sleep(sleep, retry_delay_s)
    return None


def discover_sensors(mux, create_sensor, addresses,
                     channels=(0, 1, 2, 3),
                     attempts=INIT_ATTEMPTS,
                     retry_delay_s=INIT_RETRY_DELAY_S,
                     passes=DISCOVERY_PASSES,
                     pass_delay_s=PASS_DELAY_S,
                     sleep=None, log=print, show_traceback=False):
    """Scan each mux channel and initialise the first MLX90393 found.

    Channels whose sensor was seen in the scan but failed to
    initialise are retried in a later pass (after the other channels
    have been processed and a pause), in case the failure depends on
    back-to-back initialisation of the previous sensor. Returns a
    list of ``(channel, sensor)`` in channel order.
    """
    sensors = []
    pending = list(channels)
    for pass_no in range(1, passes + 1):
        if not pending:
            break
        if pass_no > 1:
            log("Discovery pass", pass_no, "for channels", pending)
            _sleep(sleep, pass_delay_s)
        still_pending = []
        for channel in pending:
            bus = mux[channel]
            while not bus.try_lock():
                pass
            try:
                found = [a for a in bus.scan() if a != 0x70]
            finally:
                bus.unlock()
            log("Multiplexer channel", channel, "I2C scan",
                [hex(a) for a in found])
            sensor = None
            saw_candidate = False
            for address in found:
                if address not in addresses:
                    continue
                saw_candidate = True
                log("Trying MLX90393 on channel", channel,
                    "at", hex(address))
                sensor = create_sensor_with_retries(
                    bus, address, create_sensor, attempts=attempts,
                    retry_delay_s=retry_delay_s, sleep=sleep, log=log,
                    show_traceback=show_traceback)
                if sensor is not None:
                    break
                log("Channel", channel, "magnetometer failed "
                    "after", attempts, "attempts")
            if sensor is not None:
                log("Channel", channel, "magnetometer OK")
                sensors.append((channel, sensor))
            elif saw_candidate:
                still_pending.append(channel)
        pending = still_pending
    for channel in pending:
        log("Channel", channel, "magnetometer giving up after",
            passes, "passes - skipping")
    sensors.sort(key=lambda item: item[0])
    return sensors
