#!/usr/bin/env python3
"""
LoRa Telemetry Decoder CLI
Decodes packed 42-byte telemetry packets to CSV and/or plots
"""

import argparse
import logging
import sys
from pathlib import Path

from src.config import ConfigManager
from src.csv_exporter import CSVExporter
from src.decoder import TelemetryDecoder
from src.filters import FilterManager
from src.plotter import PlotManager


def setup_logging(verbose: bool = False) -> None:
    """Configure logging to stderr"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s',
        stream=sys.stderr
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Decode LoRa telemetry packets to CSV and/or plots',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python app.py -i flight.bin -t telemetry.csv
  python app.py -i flight.bin -g temp_cC,pressPa --flag-mark land,eject
  python app.py -sf settings.ini
        """
    )

    # Required
    parser.add_argument('-i', '--input', metavar='FILE', required=True,
                        help='Input binary file (*.bin)')

    # Output modes (at least one required)
    output_group = parser.add_argument_group('output modes (pick one or both)')
    output_group.add_argument('-t', '--to-csv', metavar='FILE',
                              help='Export to CSV file')
    output_group.add_argument('-g', '--graphs', metavar='LIST',
                              help='Comma-separated channel list for plotting')

    # Optional
    optional_group = parser.add_argument_group('optional')
    optional_group.add_argument('-sf', '--settings-file', metavar='FILE',
                                help='INI file with saved settings')
    optional_group.add_argument('-f', '--filter-file', metavar='FILE',
                                help='INI file with filtering rules')
    optional_group.add_argument('-o', '--output-dir', metavar='DIR', default='./plots',
                                help='Directory for plot output (default: ./plots)')
    optional_group.add_argument('--format', choices=['png', 'svg'], default='png',
                                help='Image format for plots (default: png)')
    optional_group.add_argument('--dpi', type=int, default=150,
                                help='PNG resolution (default: 150)')
    optional_group.add_argument('--flag-mark', metavar='{none|all|LIST}', default='none',
                                help='Mark flag events (default: none)')
    optional_group.add_argument('--section', default='DEFAULT',
                                help='INI section name (default: DEFAULT)')
    optional_group.add_argument('-v', '--verbose', action='store_true',
                                help='Enable debug logging')

    args = parser.parse_args()

    # Validate that at least one output mode is specified
    if not args.to_csv and not args.graphs:
        parser.error("At least one output mode required: -t/--to-csv or -g/--graphs")

    return args


def main() -> int:
    """Main entry point"""
    try:
        args = parse_args()
        setup_logging(args.verbose)

        # Load configuration
        config_manager = ConfigManager()
        if args.settings_file:
            config_manager.load_settings(args.settings_file, args.section)
        config_manager.apply_cli_args(args)

        # Validate input file
        input_path = Path(config_manager.get('input'))
        if not input_path.exists():
            logging.error(f"Input file not found: {input_path}")
            return 2

        if input_path.stat().st_size == 0:
            logging.error("Input file is empty")
            return 2

        if input_path.stat().st_size % 42 != 0:
            logging.error(f"File size {input_path.stat().st_size} is not divisible by 42")
            return 3

        # Decode packets
        decoder = TelemetryDecoder(args.verbose, logging.getLogger().level)
        packets = decoder.decode_file(input_path)
        logging.info(f"Read {len(packets)} packets from {input_path}")

        if not packets:
            logging.error("No valid packets found")
            return 2

        # Apply filters
        filter_manager = FilterManager()
        if config_manager.get('filter_file'):
            filter_manager.load_filters(config_manager.get('filter_file'))

        filtered_packets = filter_manager.apply_filters(packets, config_manager)
        dropped_count = len(packets) - len(filtered_packets)
        if dropped_count > 0:
            logging.info(f"Filtered out {dropped_count} packets")

        if not filtered_packets:
            logging.error("No packets remain after filtering")
            return 4

        # Export to CSV
        if config_manager.get('to_csv'):
            csv_exporter = CSVExporter()
            csv_path = Path(config_manager.get('to_csv'))
            try:
                csv_exporter.export(filtered_packets, csv_path)
                logging.info(f"Exported {len(filtered_packets)} packets to {csv_path}")
            except Exception as e:
                logging.error(f"Failed to write CSV: {e}")
                return 4

        # Generate plots
        if config_manager.get('graphs'):
            plot_manager = PlotManager()
            try:
                plot_count = plot_manager.create_plots(
                    filtered_packets,
                    config_manager.get('graphs'),
                    config_manager
                )
                logging.info(f"Generated {plot_count} plot files")
            except Exception as e:
                logging.error(f"Failed to generate plots: {e}")
                return 4

        logging.info("Processing completed successfully")
        return 0

    except KeyboardInterrupt:
        logging.error("Interrupted by user")
        return 1
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
