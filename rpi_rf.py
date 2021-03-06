u"""
Sending and receiving 433/315Mhz signals with low-cost GPIO RF Modules on a Raspberry Pi.
"""

from __future__ import division
from __future__ import absolute_import
import logging
import time
from collections import namedtuple

from RPi import GPIO

MAX_CHANGES = 67
print u'ola'
_LOGGER = logging.getLogger(__name__)

Protocol = namedtuple(u'Protocol',
                      [u'pulselength',
                       u'sync_high', u'sync_low',
                       u'zero_high', u'zero_low',
                       u'one_high', u'one_low'])
PROTOCOLS = (None,
             Protocol(350, 1, 31, 1, 3, 3, 1),
             Protocol(650, 1, 10, 1, 2, 2, 1),
             Protocol(100, 30, 71, 4, 11, 9, 6),
             Protocol(380, 1, 6, 1, 3, 3, 1),
             Protocol(500, 6, 14, 1, 2, 2, 1))


class RFDevice(object):
    u"""Representation of a GPIO RF device."""

    # pylint: disable=too-many-instance-attributes,too-many-arguments
    def __init__(self, gpio,
                 tx_proto=1, tx_pulselength=None, tx_repeat=10, tx_length=24, rx_tolerance=80):
        u"""Initialize the RF device."""
        self.gpio = gpio
        self.tx_enabled = False
        self.tx_proto = tx_proto
        if tx_pulselength:
            self.tx_pulselength = tx_pulselength
        else:
            self.tx_pulselength = PROTOCOLS[tx_proto].pulselength
        self.tx_repeat = tx_repeat
        self.tx_length = tx_length
        self.rx_enabled = False
        self.rx_tolerance = rx_tolerance
        # internal values
        self._rx_timings = [0] * (MAX_CHANGES + 1)
        self._rx_last_timestamp = 0
        self._rx_change_count = 0
        self._rx_repeat_count = 0
        # successful RX values
        self.rx_code = None
        self.rx_code_timestamp = None
        self.rx_proto = None
        self.rx_bitlength = None
        self.rx_pulselength = None

        GPIO.setmode(GPIO.BCM)
        _LOGGER.debug(u"Using GPIO " + unicode(gpio))

    def cleanup(self):
        u"""Disable TX and RX and clean up GPIO."""
        if self.tx_enabled:
            self.disable_tx()
        if self.rx_enabled:
            self.disable_rx()
        _LOGGER.debug(u"Cleanup")
        GPIO.cleanup()

    def enable_tx(self):
        u"""Enable TX, set up GPIO."""
        if self.rx_enabled:
            _LOGGER.error(u"RX is enabled, not enabling TX")
            return False
        if not self.tx_enabled:
            self.tx_enabled = True
            GPIO.setup(self.gpio, GPIO.OUT)
            _LOGGER.debug(u"TX enabled")
        return True

    def disable_tx(self):
        u"""Disable TX, reset GPIO."""
        if self.tx_enabled:
            # set up GPIO pin as input for safety
            GPIO.setup(self.gpio, GPIO.IN)
            self.tx_enabled = False
            _LOGGER.debug(u"TX disabled")
        return True

    def tx_code(self, code, tx_proto=None, tx_pulselength=None):
        u"""
        Send a decimal code.
        Optionally set protocol and pulselength.
        When none given reset to default protocol and pulselength.
        """
        if tx_proto:
            self.tx_proto = tx_proto
        else:
            self.tx_proto = 1
        if tx_pulselength:
            self.tx_pulselength = tx_pulselength
        else:
            self.tx_pulselength = PROTOCOLS[self.tx_proto].pulselength
        rawcode = format(code, u'#0{}b'.format(self.tx_length + 2))[2:]
        _LOGGER.debug(u"TX code: " + unicode(code))
        return self.tx_bin(rawcode)

    def tx_bin(self, rawcode):
        u"""Send a binary code."""
        _LOGGER.debug(u"TX bin: " + unicode(rawcode))
        for _ in xrange(0, self.tx_repeat):
            for byte in xrange(0, self.tx_length):
                if rawcode[byte] == u'0':
                    if not self.tx_l0():
                        return False
                else:
                    if not self.tx_l1():
                        return False
            if not self.tx_sync():
                return False

        return True

    def tx_l0(self):
        u"""Send a '0' bit."""
        if not 0 < self.tx_proto < len(PROTOCOLS):
            _LOGGER.error(u"Unknown TX protocol")
            return False
        return self.tx_waveform(PROTOCOLS[self.tx_proto].zero_high,
                                PROTOCOLS[self.tx_proto].zero_low)

    def tx_l1(self):
        u"""Send a '1' bit."""
        if not 0 < self.tx_proto < len(PROTOCOLS):
            _LOGGER.error(u"Unknown TX protocol")
            return False
        return self.tx_waveform(PROTOCOLS[self.tx_proto].one_high,
                                PROTOCOLS[self.tx_proto].one_low)

    def tx_sync(self):
        u"""Send a sync."""
        if not 0 < self.tx_proto < len(PROTOCOLS):
            _LOGGER.error(u"Unknown TX protocol")
            return False
        return self.tx_waveform(PROTOCOLS[self.tx_proto].sync_high,
                                PROTOCOLS[self.tx_proto].sync_low)

    def tx_waveform(self, highpulses, lowpulses):
        u"""Send basic waveform."""
        if not self.tx_enabled:
            _LOGGER.error(u"TX is not enabled, not sending data")
            return False
        GPIO.output(self.gpio, GPIO.HIGH)
        time.sleep((highpulses * self.tx_pulselength) / 1000000)
        GPIO.output(self.gpio, GPIO.LOW)
        time.sleep((lowpulses * self.tx_pulselength) / 1000000)
        return True

    def enable_rx(self):
        u"""Enable RX, set up GPIO and add event detection."""
        if self.tx_enabled:
            _LOGGER.error(u"TX is enabled, not enabling RX")
            return False
        if not self.rx_enabled:
            self.rx_enabled = True
            GPIO.setup(self.gpio, GPIO.IN)
            GPIO.add_event_detect(self.gpio, GPIO.BOTH)
            GPIO.add_event_callback(self.gpio, self.rx_callback)
            _LOGGER.debug(u"RX enabled")
        return True

    def disable_rx(self):
        u"""Disable RX, remove GPIO event detection."""
        if self.rx_enabled:
            GPIO.remove_event_detect(self.gpio)
            self.rx_enabled = False
            _LOGGER.debug(u"RX disabled")
        return True

    # pylint: disable=unused-argument
    def rx_callback(self, gpio):
        u"""RX callback for GPIO event detection. Handle basic signal detection."""
        timestamp = int(time.perf_counter() * 1000000)
        duration = timestamp - self._rx_last_timestamp

        if duration > 5000:
            if duration - self._rx_timings[0] < 200:
                self._rx_repeat_count += 1
                self._rx_change_count -= 1
                if self._rx_repeat_count == 2:
                    for pnum in xrange(1, len(PROTOCOLS)):
                        if self._rx_waveform(pnum, self._rx_change_count, timestamp):
                            _LOGGER.debug(u"RX code " + unicode(self.rx_code))
                            break
                    self._rx_repeat_count = 0
            self._rx_change_count = 0

        if self._rx_change_count >= MAX_CHANGES:
            self._rx_change_count = 0
            self._rx_repeat_count = 0
        self._rx_timings[self._rx_change_count] = duration
        self._rx_change_count += 1
        self._rx_last_timestamp = timestamp

    def _rx_waveform(self, pnum, change_count, timestamp):
        u"""Detect waveform and format code."""
        code = 0
        delay = int(self._rx_timings[0] / PROTOCOLS[pnum].sync_low)
        delay_tolerance = delay * self.rx_tolerance / 100

        for i in xrange(1, change_count, 2):
            if (self._rx_timings[i] - delay * PROTOCOLS[pnum].zero_high < delay_tolerance and
                    self._rx_timings[i+1] - delay * PROTOCOLS[pnum].zero_low < delay_tolerance):
                code <<= 1
            elif (self._rx_timings[i] - delay * PROTOCOLS[pnum].one_high < delay_tolerance and
                  self._rx_timings[i+1] - delay * PROTOCOLS[pnum].one_low < delay_tolerance):
                code <<= 1
                code |= 1
            else:
                return False

        if self._rx_change_count > 6 and code != 0:
            self.rx_code = code
            self.rx_code_timestamp = timestamp
            self.rx_bitlength = int(change_count / 2)
            self.rx_pulselength = delay
            self.rx_proto = pnum
            return True

        return False

