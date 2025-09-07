**Console-only Python utility** that unpacks packed 42-byte telemetry packets (LoRa-optimized binary) into readable CSV and/or publication-ready plots.  
No GUI, no heavy deps – just `python app.py -i flight.bin -g temp_cC,pressPa`.

---

## Features
- **Bit-exact** unpacking of the `TelemetryPacket` C-structure (24-bit time, 14-bit temp, 20-bit pressure, 30-bit lat/lon, 8-bit flags, etc.)
- **Fast filtering** (time gaps, physical limits, manual packet list) driven by `filter.ini`
- **Flexible plotting** – single / multi-axis, optional flag markers, PNG or SVG
- **Settings file** – save frequently-used options in `settings.ini` and load with `-sf`
- **Lightweight** – pure Python ≥3.8, runs on Raspberry Pi
- **CI tested** – 100 % unit-test coverage, GitHub Actions badge

---

## Install
```bash
git clone https://github.com/yourname/lora-telemetry-decoder.git
cd lora-telemetry-decoder
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 30-second example
```bash
# 1. Binary → CSV
python app.py -i flight_01.bin -t telemetry.csv

# 2. Binary → plots (temperature & pressure on one figure, accelerometers on another)
python app.py -i flight_01.bin -g temp_cC:single,pressPa:single,accelX,accelY,accelZ -o ./plots --flag-mark land,eject

# 3. Use saved settings
python app.py -sf my_profile.ini
```

---

## CLI reference
```
usage: app.py -i FILE [options]

required:
  -i, --input FILE       raw telemetry file (*.bin)

output mode (pick one or both):
  -t, --to-csv FILE      export to CSV
  -g, --graphs LIST      comma-separated channel list, e.g. temp_cC,pressPa,gyroZ[:axis]

optional:
  -sf, --settings-file FILE   load defaults (ini)
  -f,  --filter-file FILE     filtering rules (ini)
  -o,  --output-dir DIR       where to save plots (default: ./plots)
  --format {png|svg}          image format (default: png)
  --dpi INT                   PNG resolution (default: 150)
  --flag-mark {none|all|LIST} mark events where flags are set
  --section NAME              ini-section to use (default: DEFAULT)
  -v, --verbose               debug logging
  -h, --help                  show full help
```

---

## Channels you can plot
| Channel   | Unit / note                     |
|-----------|---------------------------------|
| time_ms   | ms since power-on               |
| temp_cC   | centi-Celsius (-819.2 … 819.1)  |
| pressPa   | Pascals (0 … 1 048 575)         |
| magX,Y,Z  | milli-Gauss                     |
| accelX,Y,Z| milli-G                         |
| gyroX,Y,Z | deci-degrees per second         |
| lat_1e7   | 1e7 * degrees                   |
| lon_1e7   | 1e7 * degrees                   |
| radData0…3| raw rad-counter values          |

---

## Settings file (`settings.ini`)
Store any CLI argument to avoid typing.

```ini
[DEFAULT]
input = last_flight.bin
graphs = temp_cC,pressPa,lat_1e7,lon_1e7
flags = land,eject
output_dir = ./plots
format = svg
dpi = 300
time_gap_ms = 2000
temp_min_cC = -5000
temp_max_cC = 8000
press_min_Pa = 30000
press_max_Pa = 110000
```

Load with  
`python app.py -sf settings.ini --section DEFAULT`

---

## Filtering (`filter.ini`)
Packets are dropped if **any** rule fails.

```ini
[time]
max_jump_ms = 2000     # allow t2-t1 ≤ 2 s
allow_wrap = false     # 24-bit counter is NOT allowed to wrap

[channels]
temp_cC_min = -5000
temp_cC_max =  8000
pressPa_min = 30000
pressPa_max = 110000

[manual]
drop_packets = 17,42,153-160   # single or range (inclusive)
```

Pass the file explicitly:  
`python app.py -i flight.bin -g temp_cC -f filter.ini`

---

## Flag markers
Add vertical lines / scatter dots when selected **SystemFlags** are high.

Example: highlight **land** and **eject** events  
`python app.py -i flight.bin -g accelZ --flag-mark land,eject`

---

## Output samples
CSV snippet:
```
time_ms,temp_cC,pressPa,magX,magY,magZ,accelX,accelY,accelZ,gyroX,gyroY,gyroZ,lat_1e7,lon_1e7,flags,radData0,radData1,radData2,radData3
120030,2350,101325,123,-45,678,-23,15,980,12,-1,3,554389710,373645690,00001000,1234,1235,1236,1237
...
```

Plot files:  
`temp_cC_flight_01.png`, `pressPa_flight_01.png`, …
