"""
Bit-accurate telemetry packet decoder

This decoder matches the bit-packing used by the test packet generator: fields are
packed LSB-first (bit 0 = LSB of byte 0). Total packet size is 42 bytes (334 bits).

Field layout (same as generator):
 - time_ms: 24 bits (unsigned)
 - temp_cC: 14 bits (signed, two's complement)
 - pressPa: 20 bits (unsigned)
 - magX, magY, magZ: 3 x 16 bits (signed)
 - accelX, accelY, accelZ: 3 x 16 bits (signed)
 - gyroX, gyroY, gyroZ: 3 x 16 bits (signed)
 - lat_1e7: 30 bits (signed)
 - lon_1e7: 30 bits (signed)
 - flags: 8 bits
 - radData0..3: 4 x 16 bits (unsigned)

This file replaces any previous byte-aligned struct.unpack approach and uses a
BitReader that reads arbitrary numbers of bits LSB-first.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Any, Dict, Optional

PACKET_SIZE = 42  # bytes


@dataclass
class SystemFlags:
    err: bool
    wait: bool
    ok: bool
    ping: bool
    command: bool
    land: bool
    eject: bool
    start: bool

    @classmethod
    def from_byte(cls, b: int) -> 'SystemFlags':
        return cls(
            err=bool(b & 0x01),
            wait=bool(b & 0x02),
            ok=bool(b & 0x04),
            ping=bool(b & 0x08),
            command=bool(b & 0x10),
            land=bool(b & 0x20),
            eject=bool(b & 0x40),
            start=bool(b & 0x80),
        )

    def to_string(self) -> str:
        return ''.join(['1' if f else '0' for f in [
            self.err, self.wait, self.ok, self.ping,
            self.command, self.land, self.eject, self.start
        ]])

    def to_flags_display(self) -> str:
        """Convert flags to display format like |START||DROP||PING||OK|"""
        active_flags = []

        # Map flags to display names (in typical order)
        flag_mapping = [
            (self.start, 'START'),
            (self.eject, 'DROP'),  # assuming eject means drop
            (self.ping, 'PING'),
            (self.ok, 'OK'),
            (self.err, 'ERR'),
            (self.wait, 'WAIT'),
            (self.command, 'CMD'),
            (self.land, 'LAND'),
        ]

        for flag_active, flag_name in flag_mapping:
            if flag_active:
                active_flags.append(f'|{flag_name}|')

        return ''.join(active_flags) if active_flags else '|NONE|'


@dataclass
class TelemetryPacket:
    time_ms: int
    temp_cC: int
    pressPa: int
    magX: int
    magY: int
    magZ: int
    accelX: int
    accelY: int
    accelZ: int
    gyroX: int
    gyroY: int
    gyroZ: int
    lat_1e7: int
    lon_1e7: int
    flags: SystemFlags
    radData0: int
    radData1: int
    radData2: int
    radData3: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            'time_ms': self.time_ms,
            'temp_cC': self.temp_cC,
            'pressPa': self.pressPa,
            'magX': self.magX,
            'magY': self.magY,
            'magZ': self.magZ,
            'accelX': self.accelX,
            'accelY': self.accelY,
            'accelZ': self.accelZ,
            'gyroX': self.gyroX,
            'gyroY': self.gyroY,
            'gyroZ': self.gyroZ,
            'lat_1e7': self.lat_1e7,
            'lon_1e7': self.lon_1e7,
            'flags': self.flags.to_string(),
            'radData0': self.radData0,
            'radData1': self.radData1,
            'radData2': self.radData2,
            'radData3': self.radData3,
        }

    def to_log_format(self, rssi: Optional[float] = None, snr: Optional[float] = None) -> str:
        """Format packet for logging in specified format"""
        lines = []

        # Header with radio info if available
        if rssi is not None and snr is not None:
            lines.append(f"-- Dataframe BGN -- (RSSI: {rssi:.0f} dBm, SNR: {snr:.0f} dB)")
        else:
            lines.append("-- Dataframe BGN --")

        # Time
        lines.append(f"Time: {self.time_ms} ms")

        # Temperature (convert from centi-degrees to degrees)
        temp_c = self.temp_cC * 0.1
        lines.append(f"Temp: {temp_c:.2f} C")

        # Pressure
        lines.append(f"Press: {self.pressPa} Pa")

        # Magnetometer (assuming mG units, convert to G)
        mag_x_g = self.magX * 0.001
        mag_y_g = self.magY * 0.001
        mag_z_g = self.magZ * 0.001
        lines.append(f"Mag:  X:{mag_x_g:.3f}  Y:{mag_y_g:.3f}  Z:{mag_z_g:.3f} G")

        # Accelerometer (assuming mG units, convert to G)
        accel_x_g = self.accelX * 0.001
        accel_y_g = self.accelY * 0.001
        accel_z_g = self.accelZ * 0.001
        lines.append(f"Accel:  X:{accel_x_g:.3f}  Y:{accel_y_g:.3f}  Z:{accel_z_g:.3f} G")

        # Gyroscope (convert from units to dps, assuming 0.1 scale factor)
        gyro_x_dps = self.gyroX * 0.1
        gyro_y_dps = self.gyroY * 0.1
        gyro_z_dps = self.gyroZ * 0.1
        lines.append(f"Gyro:  X:{gyro_x_dps:.1f}  Y:{gyro_y_dps:.1f}  Z:{gyro_z_dps:.1f} dps")

        # GPS coordinates (convert from 1e-7 scale)
        lat_deg = self.lat_1e7 * 1e-7
        lon_deg = self.lon_1e7 * 1e-7
        lines.append(f"lat: {lat_deg:.7f}  lon: {lon_deg:.7f}")

        # Radiation data
        lines.append(f"rad: {self.radData0}  {self.radData1}  {self.radData2}  {self.radData3}")

        # Flags
        lines.append(self.flags.to_flags_display())

        # Footer
        lines.append("-- Dataframe END --")

        return '\n'.join(lines)


class BitReader:
    """Read arbitrary bit-length fields LSB-first from a bytes-like object.

    The generator writes bits LSB-first into bytes using this rule:
    - bit 0 is LSB of byte 0, bit 7 is MSB of byte 0
    - then next bits continue into byte 1 LSB-first, etc.
    """

    def __init__(self, data: bytes):
        self._data = data
        self._bit_pos = 0
        self._max_bits = len(data) * 8

    def read_bits(self, n: int) -> int:
        if n == 0:
            return 0
        if n < 0:
            raise ValueError('n must be >= 0')
        if self._bit_pos + n > self._max_bits:
            raise ValueError(f'Not enough bits: requested {n} at pos {self._bit_pos}, max {self._max_bits}')

        result = 0
        shift = 0
        remain = n
        while remain:
            byte_idx = self._bit_pos // 8
            bit_in_byte = self._bit_pos % 8
            available = 8 - bit_in_byte
            take = min(available, remain)

            # extract take bits starting at bit_in_byte within this byte
            byte_val = self._data[byte_idx]
            mask = (1 << take) - 1
            chunk = (byte_val >> bit_in_byte) & mask

            result |= (chunk << shift)

            self._bit_pos += take
            shift += take
            remain -= take

        return result

    def bits_left(self) -> int:
        return self._max_bits - self._bit_pos


def _sign_extend(value: int, bits: int) -> int:
    sign_bit = 1 << (bits - 1)
    mask = (1 << bits) - 1
    v = value & mask
    if v & sign_bit:
        return v - (1 << bits)
    return v


class TelemetryDecoder:
    def __init__(self, log_packets: bool = False, log_level: int = logging.INFO):
        self.logger = logging.getLogger(__name__)
        self.log_packets = log_packets
        self.log_level = log_level

    def decode_file(self, path: Path, rssi: Optional[float] = None, snr: Optional[float] = None) -> List[
        TelemetryPacket]:
        data = path.read_bytes()
        packets: List[TelemetryPacket] = []

        if len(data) < PACKET_SIZE:
            self.logger.warning('File too small: %d bytes', len(data))
            return packets

        count = len(data) // PACKET_SIZE
        self.logger.info(f'Decoding {count} packets from {path}')

        for i in range(count):
            start = i * PACKET_SIZE
            block = data[start:start + PACKET_SIZE]
            try:
                pkt = self._decode_packet(block)
                if self._is_valid_packet(pkt):
                    packets.append(pkt)

                    # Log packet if requested
                    if self.log_packets:
                        packet_log = pkt.to_log_format(rssi, snr)
                        self.logger.log(self.log_level, f'\nPacket {i + 1}:\n{packet_log}')

                else:
                    self.logger.warning('Invalid packet %d (sanity checks failed)', i)
            except Exception as e:
                self.logger.warning('Failed to decode packet %d: %s', i, e)

        self.logger.info(f'Successfully decoded {len(packets)} valid packets')
        return packets

    def decode_packet_with_log(self, data: bytes, packet_index: int = 0,
                               rssi: Optional[float] = None, snr: Optional[float] = None) -> Optional[TelemetryPacket]:
        """Decode single packet and optionally log it"""
        try:
            pkt = self._decode_packet(data)
            if self._is_valid_packet(pkt):
                if self.log_packets:
                    packet_log = pkt.to_log_format(rssi, snr)
                    self.logger.log(self.log_level, f'\nPacket {packet_index + 1}:\n{packet_log}')
                return pkt
            else:
                self.logger.warning('Invalid packet %d (sanity checks failed)', packet_index)
                return None
        except Exception as e:
            self.logger.warning('Failed to decode packet %d: %s', packet_index, e)
            return None

    def _decode_packet(self, data: bytes) -> TelemetryPacket:
        if len(data) != PACKET_SIZE:
            raise ValueError(f'Expected {PACKET_SIZE} bytes, got {len(data)}')

        r = BitReader(data)

        time_ms = r.read_bits(24)
        temp_raw = r.read_bits(14)
        temp_cC = _sign_extend(temp_raw, 14)
        pressPa = r.read_bits(20)

        lat_raw = r.read_bits(30)
        lat_1e7 = _sign_extend(lat_raw, 30)

        lon_raw = r.read_bits(30)
        lon_1e7 = _sign_extend(lon_raw, 30)

        dummy = r.read_bits(2)

        magX = _sign_extend(r.read_bits(16), 16)
        magY = _sign_extend(r.read_bits(16), 16)
        magZ = _sign_extend(r.read_bits(16), 16)

        accelX = _sign_extend(r.read_bits(16), 16)
        accelY = _sign_extend(r.read_bits(16), 16)
        accelZ = _sign_extend(r.read_bits(16), 16)

        gyroX = _sign_extend(r.read_bits(16), 16)
        gyroY = _sign_extend(r.read_bits(16), 16)
        gyroZ = _sign_extend(r.read_bits(16), 16)

        flags_byte = r.read_bits(8)
        flags = SystemFlags.from_byte(flags_byte)

        rad0 = r.read_bits(16)
        rad1 = r.read_bits(16)
        rad2 = r.read_bits(16)
        rad3 = r.read_bits(16)

        # ensure we've consumed the whole packet (2 bits is 'dummy' field, unused)
        if r.bits_left():
            # usually zero; warn if not
            self.logger.debug('Bits left after parsing: %d', r.bits_left())

        return TelemetryPacket(
            time_ms=time_ms,
            temp_cC=temp_cC,
            pressPa=pressPa,
            magX=magX, magY=magY, magZ=magZ,
            accelX=accelX, accelY=accelY, accelZ=accelZ,
            gyroX=gyroX, gyroY=gyroY, gyroZ=gyroZ,
            lat_1e7=lat_1e7, lon_1e7=lon_1e7,
            flags=flags,
            radData0=rad0, radData1=rad1, radData2=rad2, radData3=rad3
        )

    def _is_valid_packet(self, pkt: TelemetryPacket) -> bool:
        # Basic sanity checks for numeric ranges
        if not isinstance(pkt.time_ms, int):
            return False
        if not isinstance(pkt.temp_cC, int):
            return False
        if pkt.pressPa < 0 or pkt.pressPa >= (1 << 20):
            return False
        # lat/lon ranges (approx): lat in +/-90 deg, lon in +/-180 deg scaled by 1e7
        if abs(pkt.lat_1e7) > 90 * 10_000_000:
            return False
        if abs(pkt.lon_1e7) > 180 * 10_000_000:
            return False
        # temperature sanity (centi-degrees)
        if abs(pkt.temp_cC) > 100_000:  # > 1000°C
            return False
        return True
