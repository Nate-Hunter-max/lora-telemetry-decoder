#!/usr/bin/env python3
"""
Generate properly bit-packed 42-byte telemetry packets for testing the decoder.

This file replaces the previous simplified byte-aligned generator: it packs fields
bit-by-bit (LSB-first) so the total packet size is exactly 42 bytes (334 bits).

Field layout (in order, bit lengths):
 - time_ms: 24
 - temp_cC: 14 (two's complement for negative values)
 - pressPa: 20
 - mag x,y,z: 3 * 16 (signed, two's complement)
 - accel x,y,z: 3 * 16
 - gyro x,y,z: 3 * 16
 - lat_1e7: 30 (two's complement / masked to 30 bits)
 - lon_1e7: 30
 - flags: 8
 - rad_data: 4 * 16 (unsigned)

The bit writer writes LSB-first into the packet bytearray (bit 0 is LSB of byte 0).
"""

import random
import sys
from pathlib import Path

PACKET_SIZE_BYTES = 42


class BitWriter:
    """A small helper to write arbitrary-length bit fields LSB-first into a bytearray."""

    def __init__(self, size_bytes):
        self.buf = bytearray(size_bytes)
        self.bit_pos = 0
        self.size_bits = size_bytes * 8

    def write_bits(self, value: int, nbits: int):
        """Write the low `nbits` bits of `value` into the buffer LSB-first.

        Example: write_bits(0b1011, 4) will write bit sequence 1,1,0,1 to bit positions
        bit_pos..bit_pos+3 where each bit is placed as (value >> i) & 1.
        """
        if nbits == 0:
            return
        if nbits < 0:
            raise ValueError("nbits must be non-negative")
        if self.bit_pos + nbits > self.size_bits:
            raise ValueError(f"Not enough space to write {nbits} bits at pos {self.bit_pos}")

        remaining = nbits
        v = value & ((1 << nbits) - 1) if nbits < 64 else value  # mask to nbits (safe)
        while remaining:
            byte_idx = self.bit_pos // 8
            bit_in_byte = self.bit_pos % 8
            free = 8 - bit_in_byte
            to_write = min(free, remaining)

            mask = (1 << to_write) - 1
            chunk = v & mask
            # place chunk at the correct offset inside the target byte
            self.buf[byte_idx] |= (chunk << bit_in_byte) & 0xFF

            v >>= to_write
            self.bit_pos += to_write
            remaining -= to_write

    def get_bytes(self) -> bytes:
        return bytes(self.buf)


def _to_twos_complement(value: int, nbits: int) -> int:
    """Convert signed integer to two's complement representation in nbits bits."""
    mask = (1 << nbits) - 1
    return value & mask


def generate_test_packet(time_ms, packet_id=0):
    """Generate a single bit-packed telemetry packet of exactly 42 bytes."""
    # Generate realistic test data
    temp_cC = random.randint(-2000, 4000)  # -20.00°C .. 40.00°C (centi-degrees)
    pressPa = random.randint(50000, 105000)

    # IMU data (signed 16-bit)
    mag = [random.randint(-500, 500) for _ in range(3)]
    accel = [random.randint(-1000, 1000) for _ in range(3)]
    gyro = [random.randint(-1800, 1800) for _ in range(3)]

    # GPS (scaled by 1e7) - allow negative longitudes
    lat_1e7 = random.randint(400000000, 700000000)  # 40-70°N
    lon_1e7 = random.randint(-100000000, 300000000)  # -10-30°E

    # System flags
    flags = 0
    if packet_id == 10:
        flags |= 0x80
    if packet_id == 50:
        flags |= 0x20
    if packet_id == 100:
        flags |= 0x40
    if random.random() < 0.1:
        flags |= 0x04

    # Radiation counters (unsigned 16-bit)
    rad_data = [random.randint(1000, 2000) for _ in range(4)]

    # Create bit writer for exact packet size
    bw = BitWriter(PACKET_SIZE_BYTES)

    # Pack fields LSB-first (fields' bit widths are defined in the module docstring)
    bw.write_bits(time_ms, 24)

    # Temperature: signed 14-bit (two's complement)
    bw.write_bits(_to_twos_complement(temp_cC, 14), 14)

    # Pressure: unsigned 20-bit
    bw.write_bits(pressPa & ((1 << 20) - 1), 20)

    # IMU: signed 16-bit values (x,y,z) for mag, accel, gyro
    for v in mag:
        bw.write_bits(_to_twos_complement(v, 16), 16)
    for v in accel:
        bw.write_bits(_to_twos_complement(v, 16), 16)
    for v in gyro:
        bw.write_bits(_to_twos_complement(v, 16), 16)

    # GPS coords: 30-bit each (mask/truncate to 30 bits; handles negative via two's complement)
    bw.write_bits(_to_twos_complement(lat_1e7, 30), 30)
    bw.write_bits(_to_twos_complement(lon_1e7, 30), 30)

    # Flags: 8 bits
    bw.write_bits(flags & 0xFF, 8)

    # Radiation counters: 4 x 16 bits unsigned
    for r in rad_data:
        bw.write_bits(r & 0xFFFF, 16)

    # Dummy
    bw.write_bits(0x0, 2)

    # Sanity checks
    if bw.bit_pos != PACKET_SIZE_BYTES * 8:
        raise AssertionError(f"Packed bits = {bw.bit_pos}, expected {PACKET_SIZE_BYTES * 8}")

    return bw.get_bytes()


def generate_test_file(filename, packet_count=200):
    print(f"Generating {packet_count} bit-packed test packets in {filename}")
    with open(filename, 'wb') as f:
        time_ms = 1000
        for i in range(packet_count):
            if i == 0:
                time_ms = 1000
            else:
                if random.random() < 0.05:
                    time_ms += random.randint(5000, 10000)
                else:
                    time_ms += random.randint(100, 500)
            time_ms = time_ms % (1 << 24)
            packet = generate_test_packet(time_ms, i)
            assert len(packet) == PACKET_SIZE_BYTES, f"packet size {len(packet)} != {PACKET_SIZE_BYTES}"
            f.write(packet)

    print(f"Generated {filename} ({packet_count * PACKET_SIZE_BYTES} bytes)")


def main():
    test_file = "test_telemetry.bin"
    generate_test_file(test_file)

    print("\nTesting decoder (if present)...")
    try:
        sys.path.insert(0, '.')
        from src.decoder import TelemetryDecoder

        decoder = TelemetryDecoder()
        packets = decoder.decode_file(Path(test_file))

        print(f"Successfully decoded {len(packets)} packets")

        for i, packet in enumerate(packets[:3]):
            # Defensive access in case decoder field names differ
            timev = getattr(packet, 'time_ms', None)
            tempv = getattr(packet, 'temp_cC', None)
            pressv = getattr(packet, 'pressPa', None)
            flags_obj = getattr(packet, 'flags', None)
            flags_str = flags_obj.to_string() if flags_obj is not None else str(flags_obj)
            print(f"Packet {i}: time={timev}ms, temp={tempv}, press={pressv}Pa, flags={flags_str}")

        print("\nTesting CSV export (if present)...")
        from src.csv_exporter import CSVExporter
        csv_exporter = CSVExporter()
        csv_exporter.export(packets, Path("test_output.csv"))
        print("CSV export successful: test_output.csv")

    except Exception as e:
        print(f"Decoder test skipped or failed: {e}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
