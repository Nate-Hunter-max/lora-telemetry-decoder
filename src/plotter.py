"""
Plotting module
Generates publication-ready plots from telemetry data
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

from .decoder import TelemetryPacket


class PlotManager:
    """Manages plot generation for telemetry data"""

    # Available channels and their display properties
    CHANNEL_INFO = {
        'time_ms': {'label': 'Time (s)', 'unit': 's'},
        'temp_cC': {'label': 'Temperature (Â°C)', 'unit': 'Â°C', 'scale': 0.01},
        'pressPa': {'label': 'Pressure (Pa)', 'unit': 'Pa'},
        'magX': {'label': 'Magnetometer X (mG)', 'unit': 'mG'},
        'magY': {'label': 'Magnetometer Y (mG)', 'unit': 'mG'},
        'magZ': {'label': 'Magnetometer Z (mG)', 'unit': 'mG'},
        'accelX': {'label': 'Accelerometer X (mG)', 'unit': 'mG'},
        'accelY': {'label': 'Accelerometer Y (mG)', 'unit': 'mG'},
        'accelZ': {'label': 'Accelerometer Z (mG)', 'unit': 'mG'},
        'gyroX': {'label': 'Gyroscope X (dps)', 'unit': 'dps', 'scale': 0.1},
        'gyroY': {'label': 'Gyroscope Y (dps)', 'unit': 'dps', 'scale': 0.1},
        'gyroZ': {'label': 'Gyroscope Z (dps)', 'unit': 'dps', 'scale': 0.1},
        'lat_1e7': {'label': 'Latitude (Â°)', 'unit': 'Â°', 'scale': 1e-7},
        'lon_1e7': {'label': 'Longitude (Â°)', 'unit': 'Â°', 'scale': 1e-7},
        'radData0': {'label': 'Rad Counter 0', 'unit': 'counts'},
        'radData1': {'label': 'Rad Counter 1', 'unit': 'counts'},
        'radData2': {'label': 'Rad Counter 2', 'unit': 'counts'},
        'radData3': {'label': 'Rad Counter 3', 'unit': 'counts'},
    }

    FLAG_NAMES = ['err', 'wait', 'ok', 'ping', 'command', 'land', 'eject', 'start']
    # Неяркие цвета для выделения областей
    FLAG_COLORS = ['#e6b8d6', '#c9c9c9', '#e6b8b8', '#e6d1b8', '#b8e6b8', '#b8d1e6', '#d1b8e6', '#bfa47f']

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        plt.style.use('default')  # Ensure consistent style

    def create_plots(self, packets: List[TelemetryPacket], graphs_spec: str, config_manager) -> int:
        """Create plots based on specification string"""
        if not packets:
            raise ValueError("No packets to plot")

        # Parse graph specification
        plot_groups = self._parse_graphs_spec(graphs_spec)

        # Extract time data (convert to seconds)
        time_data = np.array([p.time_ms / 1000.0 for p in packets])

        # Get flag regions
        flag_regions = self._get_flag_regions(packets, config_manager.get('flag_mark', 'none'))

        # Get output settings
        output_dir = Path(config_manager.get('output_dir', './plots'))
        output_dir.mkdir(parents=True, exist_ok=True)

        img_format = config_manager.get('format', 'png')
        dpi = config_manager.get('dpi', 150)

        # Get base filename from input
        input_path = Path(config_manager.get('input', 'telemetry.bin'))
        base_name = input_path.stem

        plot_count = 0

        # Create plots for each group
        for group_idx, (channels, axis_mode) in enumerate(plot_groups):
            fig, axes = self._create_figure(channels, axis_mode)

            # Add flag regions first (so they appear behind the data)
            if flag_regions:
                if axis_mode == 'single':
                    self._add_flag_regions(axes, flag_regions)
                else:
                    for ax in axes:
                        self._add_flag_regions(ax, flag_regions)

            # Plot each channel in the group
            for i, channel in enumerate(channels):
                ax = axes[i] if axis_mode == 'multi' else axes
                self._plot_channel(ax, channel, packets, time_data)

            # Configure and save plot
            self._configure_plot(fig, axes, channels, axis_mode, flag_regions)

            # Generate filename
            if len(channels) == 1:
                filename = f"{channels[0]}_{base_name}.{img_format}"
            else:
                filename = f"multi_{group_idx}_{base_name}.{img_format}"

            output_path = output_dir / filename

            # Save plot
            save_kwargs = {'format': img_format, 'bbox_inches': 'tight'}
            if img_format == 'png':
                save_kwargs['dpi'] = dpi

            fig.savefig(output_path, **save_kwargs)
            plt.close(fig)

            plot_count += 1
            self.logger.debug(f"Saved plot: {output_path}")

        return plot_count

    def _parse_graphs_spec(self, graphs_spec: str) -> List[Tuple[List[str], str]]:
        """Parse graphs specification like 'temp_cC:single,pressPa,accelX'"""
        plot_groups = []
        current_group = []
        current_axis = 'multi'  # default

        for item in graphs_spec.split(','):
            item = item.strip()
            if not item:
                continue

            # Check for axis specification
            if ':' in item:
                channel, axis_spec = item.split(':', 1)
                channel = channel.strip()
                axis_spec = axis_spec.strip()

                if axis_spec not in ['single', 'multi']:
                    self.logger.warning(f"Invalid axis spec '{axis_spec}', using 'multi'")
                    axis_spec = 'multi'

                # If switching axis modes, start new group
                if current_group and axis_spec != current_axis:
                    plot_groups.append((current_group.copy(), current_axis))
                    current_group = []

                current_axis = axis_spec
            else:
                channel = item

            # Validate channel
            if channel not in self.CHANNEL_INFO:
                available = ', '.join(sorted(self.CHANNEL_INFO.keys()))
                raise ValueError(f"Unknown channel '{channel}'. Available: {available}")

            current_group.append(channel)

            # For multi mode, each channel gets its own group
            if current_axis == 'multi':
                plot_groups.append(([channel], current_axis))
                current_group = []

        # Add remaining group for single mode
        if current_group:
            plot_groups.append((current_group, current_axis))

        return plot_groups

    def _create_figure(self, channels: List[str], axis_mode: str) -> Tuple[plt.Figure, Any]:
        """Create matplotlib figure and axes"""
        if axis_mode == 'single':
            fig, ax = plt.subplots(figsize=(12, 6))
            return fig, ax
        else:
            # Multi mode - one subplot per channel
            n_channels = len(channels)
            fig, axes = plt.subplots(n_channels, 1, figsize=(12, 4 * n_channels), squeeze=False)
            return fig, axes.flatten()

    def _plot_channel(self, ax, channel: str, packets: List[TelemetryPacket], time_data: np.ndarray) -> None:
        """Plot single channel data"""
        # Extract channel data
        data = []
        for packet in packets:
            value = getattr(packet, channel)

            # Apply scaling if specified
            if 'scale' in self.CHANNEL_INFO[channel]:
                value *= self.CHANNEL_INFO[channel]['scale']

            data.append(value)

        data = np.array(data)

        # Plot the data
        ax.plot(time_data, data, linewidth=1.0, label=self.CHANNEL_INFO[channel]['label'])
        ax.set_xlabel('Time (s)')
        ax.set_ylabel(self.CHANNEL_INFO[channel]['label'])
        ax.grid(True, alpha=0.3)

    def _get_flag_regions(self, packets: List[TelemetryPacket], flag_spec: str) -> Dict[str, List[Tuple[float, float]]]:
        """Extract flag active regions for highlighting"""
        if flag_spec == 'none':
            return {}

        # Determine which flags to track
        if flag_spec == 'all':
            track_flags = set(self.FLAG_NAMES)
        else:
            track_flags = set(flag_spec.split(','))
            # Validate flag names
            invalid_flags = track_flags - set(self.FLAG_NAMES)
            if invalid_flags:
                available = ', '.join(self.FLAG_NAMES)
                raise ValueError(f"Invalid flags: {invalid_flags}. Available: {available}")

        flag_regions = {flag: [] for flag in track_flags}

        # Find continuous regions where each flag is active
        for flag_name in track_flags:
            in_region = False
            region_start = None

            for i, packet in enumerate(packets):
                time_sec = packet.time_ms / 1000.0

                # Get flag value
                flags_dict = {
                    'err': packet.flags.err,
                    'wait': packet.flags.wait,
                    'ok': packet.flags.ok,
                    'ping': packet.flags.ping,
                    'command': packet.flags.command,
                    'land': packet.flags.land,
                    'eject': packet.flags.eject,
                    'start': packet.flags.start
                }

                flag_active = flags_dict.get(flag_name, False)

                if flag_active and not in_region:
                    # Start of new region
                    in_region = True
                    region_start = time_sec
                elif not flag_active and in_region:
                    # End of region
                    in_region = False
                    if region_start is not None:
                        flag_regions[flag_name].append((region_start, time_sec))

            # Close any remaining open region
            if in_region and region_start is not None:
                final_time = packets[-1].time_ms / 1000.0
                flag_regions[flag_name].append((region_start, final_time))

        # Remove empty flag lists
        return {flag: regions for flag, regions in flag_regions.items() if regions}

    def _add_flag_regions(self, ax, flag_regions: Dict[str, List[Tuple[float, float]]]) -> None:
        """Add colored regions for flag events with dashed borders"""
        for flag_idx, (flag_name, regions) in enumerate(flag_regions.items()):
            color = self.FLAG_COLORS[flag_idx % len(self.FLAG_COLORS)]

            for start_time, end_time in regions:
                # Add colored vertical span for the region
                ax.axvspan(start_time, end_time, color=color, alpha=0.7, zorder=0)

                # Add thin dashed lines at region boundaries
                y_min, y_max = ax.get_ylim()
                ax.axvline(x=start_time, color='black', linestyle='--', alpha=1,
                           linewidth=0.8, ymin=0, ymax=1, zorder=1)
                ax.axvline(x=end_time, color='black', linestyle='--', alpha=1,
                           linewidth=0.8, ymin=0, ymax=1, zorder=1)

    def _configure_plot(self, fig: plt.Figure, axes: Any, channels: List[str],
                        axis_mode: str, flag_regions: Dict[str, List[Tuple[float, float]]]) -> None:
        """Configure plot appearance and legend"""
        # Set overall title
        if len(channels) == 1:
            title = self.CHANNEL_INFO[channels[0]]['label']
        else:
            title = f"Telemetry Data ({len(channels)} channels)"

        fig.suptitle(title, fontsize=14)

        # Add flag legend if regions are present
        if flag_regions:
            legend_elements = []
            for flag_idx, (flag_name, regions) in enumerate(flag_regions.items()):
                if regions:  # Only add to legend if there are actual regions
                    color = self.FLAG_COLORS[flag_idx % len(self.FLAG_COLORS)]
                    total_duration = sum(end - start for start, end in regions)
                    legend_elements.append(
                        mpatches.Patch(color=color, alpha=0.7,
                                       label=f'{flag_name} ({len(regions)} regions, {total_duration:.1f}s total)')
                    )

            if legend_elements:
                if axis_mode == 'single':
                    axes.legend(handles=legend_elements)
                else:
                    # Add legend to the top subplot
                    axes[0].legend(handles=legend_elements)

        # Adjust layout
        fig.tight_layout()
