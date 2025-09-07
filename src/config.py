"""
Configuration management module
Handles INI files and CLI argument processing
"""

import configparser
import logging
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigManager:
    """Manages application configuration from CLI and INI files"""

    def __init__(self):
        self.config = {}
        self.logger = logging.getLogger(__name__)

    def load_settings(self, settings_file: str, section: str = 'DEFAULT') -> None:
        """Load settings from INI file"""
        settings_path = Path(settings_file)
        if not settings_path.exists():
            raise FileNotFoundError(f"Settings file not found: {settings_file}")

        parser = configparser.ConfigParser()
        parser.read(settings_path, encoding='utf-8')

        if section not in parser:
            available = ', '.join(parser.sections() + ['DEFAULT'])
            raise ValueError(f"Section '{section}' not found. Available: {available}")

        # Load all values from the specified section
        for key, value in parser[section].items():
            self.config[key] = self._parse_value(value)

        self.logger.debug(f"Loaded {len(self.config)} settings from [{section}] in {settings_file}")

    def apply_cli_args(self, args) -> None:
        """Apply command line arguments, overriding INI settings"""
        # Map argparse namespace to config dict
        arg_dict = vars(args)

        for key, value in arg_dict.items():
            if value is not None:
                self.config[key] = value

        self.logger.debug(f"Applied {len([v for v in arg_dict.values() if v is not None])} CLI arguments")

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self.config.get(key, default)

    def _parse_value(self, value: str) -> Any:
        """Parse string value to appropriate type"""
        # Boolean values
        if value.lower() in ('true', 'yes', '1', 'on'):
            return True
        elif value.lower() in ('false', 'no', '0', 'off'):
            return False

        # Try integer
        try:
            return int(value)
        except ValueError:
            pass

        # Try float
        try:
            return float(value)
        except ValueError:
            pass

        # Return as string
        return value

    def get_channel_limits(self) -> Dict[str, Dict[str, float]]:
        """Extract channel limit settings for filtering"""
        limits = {}

        channels = [
            'temp_cC', 'pressPa', 'magX', 'magY', 'magZ',
            'accelX', 'accelY', 'accelZ', 'gyroX', 'gyroY', 'gyroZ',
            'lat_1e7', 'lon_1e7', 'radData0', 'radData1', 'radData2', 'radData3'
        ]

        for channel in channels:
            min_key = f"{channel}_min"
            max_key = f"{channel}_max"

            if min_key in self.config or max_key in self.config:
                limits[channel] = {}
                if min_key in self.config:
                    limits[channel]['min'] = float(self.config[min_key])
                if max_key in self.config:
                    limits[channel]['max'] = float(self.config[max_key])

        return limits

    def get_time_settings(self) -> Dict[str, Any]:
        """Extract time filtering settings"""
        settings = {}

        if 'time_gap_ms' in self.config:
            settings['max_jump_ms'] = int(self.config['time_gap_ms'])
        elif 'max_jump_ms' in self.config:
            settings['max_jump_ms'] = int(self.config['max_jump_ms'])

        if 'allow_wrap' in self.config:
            settings['allow_wrap'] = bool(self.config['allow_wrap'])

        return settings