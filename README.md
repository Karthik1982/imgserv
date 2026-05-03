# imgserv

`imgserv` is a lightweight photo-frame web server that serves images from a local folder as an auto-advancing slideshow.

It also supports:
- optional weather display (OpenWeather API)
- optional sleep mode schedule (screen dim/off hours)
- optional photo metadata overlay (date and location from EXIF)

## Features

- Serves local images over HTTP and displays them in a fullscreen browser view
- Shuffles images for a non-repeating slideshow experience
- Supports common image formats: JPG, JPEG, PNG, GIF, BMP, WebP, HEIC, HEIF
- Reads EXIF date/location metadata when available
- Shows current weather with icon and temperature when configured
- Includes configurable sleep window (for overnight display pause)

## Requirements

- Python 3.11+

## Installation

From the project root:

```bash
python3 -m pip install .
```

Or install in editable mode for development:

```bash
python3 -m pip install -e .
```

## Quick Start

Run the server and point it to your photo directory:

```bash
python3 -m imgserv /path/to/photos
```

Then open:

- [http://localhost:8000](http://localhost:8000)

## CLI Usage

```bash
python3 -m imgserv /path/to/images [--port 8000] [--interval 5]
```

### Arguments

- `image_dir` (required): Path to directory containing images

### Options

- `--port`, `-p`: Server port (default: `8000`)
- `--interval`, `-i`: Seconds between images (default: `5`)
- `--weather-api-key`: OpenWeather API key (or set `OPENWEATHER_API_KEY`)
- `--city`: City name for weather display (for example: `"New York"` or `"London,UK"`)
- `--sleep-start`: Sleep mode start time in `HH:MM` (default: `23:00`)
- `--sleep-end`: Sleep mode end time in `HH:MM` (default: `06:00`)

### Examples

```bash
python3 -m imgserv ./photos
python3 -m imgserv ./photos --port 8080
python3 -m imgserv ./photos --interval 10
python3 -m imgserv ./photos --city "New York" --weather-api-key YOUR_API_KEY
python3 -m imgserv ./photos --sleep-start 22:30 --sleep-end 06:30
```

## Weather Setup (Optional)

1. Create an API key at [OpenWeather](https://openweathermap.org/api)
2. Run with key + city via flags, or use environment variable:

```bash
export OPENWEATHER_API_KEY="your_api_key_here"
python3 -m imgserv ./photos --city "New York"
```

## Building a Standalone Executable

Use the included build script:

```bash
./build.sh
```

Output binary:

- `dist/imgserv`

Run example:

```bash
./dist/imgserv /path/to/photos --city "New York" --weather-api-key YOUR_API_KEY
```

## Running as a `systemd` service (Debian / Raspberry Pi OS)

[Raspberry Pi OS](https://www.raspberrypi.com/software/) is Debian-based and uses **systemd**, so you can start `imgserv` at boot like any other long-running service.

### 1. Install into a virtual environment (recommended)

On the Pi or Debian host:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip

mkdir -p ~/venvs
python3 -m venv ~/venvs/imgserv
source ~/venvs/imgserv/bin/activate
pip install --upgrade pip
pip install /path/to/imgserv   # or: pip install git+https://github.com/you/imgserv.git
```

Use the venv’s Python in the service unit (see below), for example `~/venvs/imgserv/bin/python`.

### 2. Optional: secrets in an environment file

Avoid putting API keys directly in the unit if others can read it. Create a root-owned file readable only by root:

```bash
sudo install -m 600 /dev/null /etc/imgserv.env
sudo nano /etc/imgserv.env
```

Example contents:

```ini
OPENWEATHER_API_KEY=your_key_here
```

Reference it from the service with `EnvironmentFile=-/etc/imgserv.env` (the `-` makes a missing file non-fatal).

### 3. Create a `systemd` unit

```bash
sudo nano /etc/systemd/system/imgserv.service
```

Example unit (adjust **user**, **paths**, **port**, and **CLI flags**):

```ini
[Unit]
Description=imgserv photo frame
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/home/pi
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-/etc/imgserv.env
ExecStart=/home/pi/venvs/imgserv/bin/python -m imgserv /home/pi/Photos --port 8000 --interval 5 --city "Boston,US"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

- **`User` / `Group`**: use a dedicated account if you prefer isolation from the default `pi` user.
- **`ExecStart`**: must be a single line; add any flags you need (`--sleep-start`, `--sleep-end`, etc.). If you use `OPENWEATHER_API_KEY` in `/etc/imgserv.env`, you can omit `--weather-api-key` from the command line.

### 4. Enable and run

```bash
sudo systemctl daemon-reload
sudo systemctl enable imgserv.service
sudo systemctl start imgserv.service
sudo systemctl status imgserv.service
```

Logs:

```bash
journalctl -u imgserv.service -f
```

### 5. Kiosk browser (typical on a Pi frame)

Point Chromium or your fullscreen browser at `http://127.0.0.1:8000` (or the host’s LAN IP from another device). Exact kiosk setup depends on your desktop or Wayland stack; the service above only keeps the HTTP server running.

## Notes

- HEIC/HEIF support requires the `pillow-heif` dependency (already included in this project).
- Browser support for rendering HEIC directly may vary by browser/OS.
- If no images are found, the server still starts and waits for files to be added.
