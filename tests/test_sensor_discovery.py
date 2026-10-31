"""Tests for firmware/sensor_discovery.py (stdlib only, fake hardware).

Run:  python3 -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "firmware"))
import sensor_discovery

ADDRESSES = (0x0C, 0x18)


class FakeBus:
    def __init__(self, channel, addresses):
        self.channel = channel
        self._addresses = addresses
        self.unlocked = False

    def try_lock(self):
        return True

    def unlock(self):
        self.unlocked = True

    def scan(self):
        return list(self._addresses)


class FakeMux:
    def __init__(self, addresses_by_channel):
        self._buses = {
            ch: FakeBus(ch, addrs) for ch, addrs in addresses_by_channel.items()
        }

    def __getitem__(self, channel):
        return self._buses[channel]


def silent(*_args):
    pass


class DiscoveryTest(unittest.TestCase):
    def test_second_sensor_recovers_from_transient_init_failure(self):
        # Channel 2's sensor NAKs (Errno 19) the first two init attempts,
        # then answers -- the intermittent failure seen on real hardware.
        # Discovery must retry instead of dropping that sensor.
        calls = {0: 0, 2: 0}

        def factory(bus, address):
            calls[bus.channel] += 1
            if bus.channel == 2 and calls[2] < 3:
                raise OSError(19, "No such device")
            return ("sensor", bus.channel, address)

        mux = FakeMux({0: [0x70, 0x18], 1: [], 2: [0x70, 0x18], 3: []})
        sensors = sensor_discovery.discover_sensors(
            mux, factory, ADDRESSES, attempts=3,
            sleep=lambda _s: None, log=silent)

        self.assertEqual([ch for ch, _s in sensors], [0, 2])
        self.assertEqual(calls[2], 3)

    def test_sensor_recovered_in_second_discovery_pass(self):
        # Channel 2 fails every attempt of pass 1 (e.g. it dislikes
        # being initialised immediately after channel 0), then
        # succeeds on the first attempt of pass 2.
        calls = {0: 0, 2: 0}

        def factory(bus, address):
            calls[bus.channel] += 1
            if bus.channel == 2 and calls[2] <= 2:
                raise OSError(19, "No such device")
            return ("sensor", bus.channel, address)

        mux = FakeMux({0: [0x70, 0x18], 1: [], 2: [0x70, 0x18], 3: []})
        sensors = sensor_discovery.discover_sensors(
            mux, factory, ADDRESSES, attempts=2, passes=2,
            pass_delay_s=0, sleep=lambda _s: None, log=silent)

        self.assertEqual([ch for ch, _s in sensors], [0, 2])
        self.assertEqual(calls[2], 3)

    def test_permanently_failing_sensor_is_skipped(self):
        calls = []

        def factory(bus, address):
            calls.append(bus.channel)
            if bus.channel == 2:
                raise OSError(19, "No such device")
            return ("sensor", bus.channel, address)

        mux = FakeMux({0: [0x70, 0x18], 1: [], 2: [0x70, 0x18], 3: []})
        sensors = sensor_discovery.discover_sensors(
            mux, factory, ADDRESSES, attempts=2, passes=2,
            pass_delay_s=0, sleep=lambda _s: None, log=silent)

        self.assertEqual([ch for ch, _s in sensors], [0])
        # 2 attempts x 2 passes, then it is given up on.
        self.assertEqual(calls.count(2), 4)

    def test_non_mlx_address_is_ignored(self):
        def factory(bus, address):  # must never be called
            raise AssertionError("factory called for a non-MLX address")

        mux = FakeMux({0: [0x70, 0x50], 1: [], 2: [], 3: []})
        sensors = sensor_discovery.discover_sensors(
            mux, factory, ADDRESSES, attempts=1,
            sleep=lambda _s: None, log=silent)
        self.assertEqual(sensors, [])


if __name__ == "__main__":
    unittest.main()
