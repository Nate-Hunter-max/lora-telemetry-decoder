"""
Packet filtering module
Handles time, channel range, and manual filtering
"""

import configparser
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple

from .decoder import TelemetryPacket


class FilterManager:
    """Manages packet filtering based on various criteria"""

    def __init__(self):
        self.time_settings = {}
        self.channel_limits = {}
        self.manual_drops = set()
        self.logger = logging.getLogger(__name__)

    def load_filters(self, filter_file: str) -> None:
        """Load filter rules from INI file"""
        filter_path = Path(filter_file)
        if not filter_path.exists():
            raise FileNotFoundError(f"Filter file not found: {filter_file}")

        parser = configparser.ConfigParser()
        parser.read(filter_path, encoding='utf-8')

        # Load time filtering settings
        if 'time' in parser:
            time_section = parser['time']
            if 'max_jump_ms' in time_section:
                self.time_settings['max_jump_ms'] = int(time_section['max_jump_ms'])
            if 'allow_wrap' in time_section:
                self.time_settings['allow_wrap'] = time_section.getboolean('allow_wrap')

        # Load channel limits
        if 'channels' in parser:
            channel_section = parser['channels']
            for key, value in channel_section.items():
                if key.endswith('_min') or key.endswith('_max'):
                    channel_name = key.rsplit('_', 1)[0]
                    limit_type = key.rsplit('_', 1)[1]

                    if channel_name not in self.channel_limits:
                        self.channel_limits[channel_name] = {}

                    self.channel_limits[channel_name][limit_type] = float(value)

        # Load manual drop list
        if 'manual' in parser and 'drop_packets' in parser['manual']:
            drop_list = parser['manual']['drop_packets']
            self.manual_drops = self._parse_packet_list(drop_list)

        self.logger.debug(f"Loaded filters: time={bool(self.time_settings)}, "
                          f"channels={len(self.channel_limits)}, manual={len(self.manual_drops)}")

    def apply_filters(self, packets: List[TelemetryPacket], config_manager) -> List[TelemetryPacket]:
        """Apply all filters in order: time -> channels -> manual"""
        if not packets:
            return packets

        # Merge filter settings from config manager
        self._merge_config_settings(config_manager)

        filtered_packets = []
        prev_time = None

        for idx, packet in enumerate(packets):
            # Time filtering
            if not self._passes_time_filter(packet, prev_time, idx):
                continue

            # Channel range filtering
            if not self._passes_channel_filter(packet):
                continue

            # Manual drop filtering
            if idx in self.manual_drops:
                self.logger.debug(f"Manually dropped packet {idx}")
                continue

            filtered_packets.append(packet)
            prev_time = packet.time_ms

        return filtered_packets

    def _merge_config_settings(self, config_manager) -> None:
        """Merge time and channel settings from config manager"""
        # Merge time settings
        time_config = config_manager.get_time_settings()
        self.time_settings.update(time_config)

        # Merge channel limits
        channel_config = config_manager.get_channel_limits()
        for channel, limits in channel_config.items():
            if channel not in self.channel_limits:
                self.channel_limits[channel] = {}
            self.channel_limits[channel].update(limits)

    def _passes_time_filter(self, packet: TelemetryPacket, prev_time: int, idx: int) -> bool:
        """Check if packet passes time filtering rules"""
        if not self.time_settings or prev_time is None:
            return True

        time_diff = packet.time_ms - prev_time
        max_jump = self.time_settings.get('max_jump_ms', float('inf'))
        allow_wrap = self.time_settings.get('allow_wrap', False)

        # Handle 24-bit counter wrap-around
        if time_diff < 0 and allow_wrap:
            # Assume 24-bit counter wrapped around
            time_diff += (1 << 24)

        # Check for excessive time jumps
        if time_diff > max_jump:
            self.logger.debug(f"Dropped packet {idx}: time jump {time_diff}ms > {max_jump}ms")
            return False

        # Check for negative time (non-monotonic) when wrap not allowed
        if time_diff < 0 and not allow_wrap:
            self.logger.debug(f"Dropped packet {idx}: negative time jump {time_diff}ms")
            return False

        return True

    def _passes_channel_filter(self, packet: TelemetryPacket) -> bool:
        """Check if packet passes channel range filtering"""
        packet_dict = packet.to_dict()

        for channel, limits in self.channel_limits.items():
            if channel not in packet_dict:
                continue

            value = packet_dict[channel]

            # Skip flag field (string)
            if channel == 'flags':
                continue

            # Check min limit
            if 'min' in limits and value < limits['min']:
                self.logger.debug(f"Dropped packet: {channel}={value} < {limits['min']}")
                return False

            # Check max limit
            if 'max' in limits and value > limits['max']:
                self.logger.debug(f"Dropped packet: {channel}={value} > {limits['max']}")
                return False

        return True

    def _parse_packet_list(self, drop_list: str) -> Set[int]:
        """Parse manual drop list like '17,42,153-160'"""
        drops = set()

        for item in drop_list.split(','):
            item = item.strip()
            if not item:
                continue

            if '-' in item:
                # Range like '153-160'
                start, end = item.split('-', 1)
                try:
                    start_idx = int(start.strip())
                    end_idx = int(end.strip())
                    drops.update(range(start_idx, end_idx + 1))  # Inclusive
                except ValueError:
                    self.logger.warning(f"Invalid range in drop list: {item}")
            else:
                # Single packet like '17'
                try:
                    drops.add(int(item))
                except ValueError:
                    self.logger.warning(f"Invalid packet number in drop list: {item}")

        return drops