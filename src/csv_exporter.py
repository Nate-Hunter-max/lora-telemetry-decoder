"""
CSV export module
Handles telemetry data export to CSV format
"""

import csv
import logging
from pathlib import Path
from typing import List

from .decoder import TelemetryPacket


class CSVExporter:
    """Exports telemetry packets to CSV format"""

    # CSV header according to specification
    HEADER = [
        'time_ms', 'temp_cC', 'pressPa', 'magX', 'magY', 'magZ',
        'accelX', 'accelY', 'accelZ', 'gyroX', 'gyroY', 'gyroZ',
        'lat_1e7', 'lon_1e7', 'flags', 'radData0', 'radData1', 'radData2', 'radData3'
    ]

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def export(self, packets: List[TelemetryPacket], output_path: Path) -> None:
        """Export packets to CSV file"""
        if not packets:
            raise ValueError("No packets to export")

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=self.HEADER, delimiter=';')

            # Write header
            writer.writeheader()

            # Write data rows
            for packet in packets:
                packet_dict = packet.to_dict()
                # Ensure all required fields are present
                row_data = {field: packet_dict.get(field, '') for field in self.HEADER}
                writer.writerow(row_data)

        self.logger.debug(f"Exported {len(packets)} packets to {output_path}")