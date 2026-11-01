# VideoArrow (`add_arrow_overlay.py`)

A standalone Python video utility that renders a crisp, procedural downward-pointing indicator arrow above a person or object in a video.

## Features

- **Interactive Multi-Waypoint Tracking**: Place multiple arrow keyframes over time. Click to set an arrow point at the start, scrub forward, click again, and the arrow will smoothly track between your waypoints!
- **Smooth Glide vs. Hold/Step Motion**: Choose between smooth linear path interpolation (default) or step-wise hold mode (press <kbd>M</kbd> to toggle).
- **Procedural Arrow Rendering**: Procedurally generates a clean downward-pointing indicator arrow with a high-contrast dark border and beveled 3D appearance. No external PNG files or assets needed.
- **Sinusoidal Bobbing (`--bounce`)**: Optional smooth vertical bobbing motion (like a video game player marker) without tracking jitter.
- **Lossless Audio Passthrough**: Uses FFmpeg stream copy (`-c:a copy`) to preserve original audio tracks without re-encoding quality loss.
- **Fast H.264 Video Encoding**: Streams frames directly to FFmpeg via stdin pipe for high throughput.
- **Headless & Script Friendly**: Supports explicit `--coords X Y` to bypass the interactive picker for automation and batch workflows.

---

## Installation

### Prerequisites

1. **Python 3.8+**
2. **FFmpeg** installed on your system:
   - **Ubuntu/Debian**: `sudo apt install ffmpeg`
   - **macOS** (Homebrew): `brew install ffmpeg`
   - **Windows** (Chocolatey / Scoop): `choco install ffmpeg` or `scoop install ffmpeg`

### Install Python Dependencies

```bash
pip install -r requirements.txt
```

*(Or manually: `pip install opencv-python numpy`)*

---

## Usage

### 1. Interactive Multi-Waypoint Tracking

Launch the tracker with your video:

```bash
python add_arrow_overlay.py input.mp4 --bounce
```

**How to track as you move:**
1. **At the start (or any frame)**: Left-click on yourself to place the first arrow position.
2. **Skip forward**:
   - Press <kbd>A</kbd> / <kbd>D</kbd> to seek **-1s / +1s**.
   - Press <kbd>[</kbd> / <kbd>]</kbd> to seek **-5s / +5s**.
   - Press <kbd>,</kbd> / <kbd>.</kbd> to step single frames.
3. **Click again**: Left-click on your new position to add another keyframe.
4. **Repeat**: Repeat whenever you move or change direction. The arrow will smoothly glide along your path between each point!
5. **Preview**: As you scrub back and forth with <kbd>A</kbd>/<kbd>D</kbd>, you'll see the arrow actively tracking you across the screen in real-time.
6. **Motion Style**: Press <kbd>M</kbd> to toggle between **Smooth Glide** (linear interpolation) and **Hold/Step** (stays put until next point).
7. **Confirm**: Press <kbd>Enter</kbd> or <kbd>Space</kbd> when done to encode the video.

*(To delete a misplaced keyframe, press <kbd>Z</kbd> or <kbd>Backspace</kbd>).*

---

### 2. Animated Bouncing Arrow

Add a gentle sinusoidal vertical bobbing motion:

```bash
python add_arrow_overlay.py input.mp4 --bounce
```

You can customize the bounce amplitude (pixels) and frequency (cycles per second):

```bash
python add_arrow_overlay.py input.mp4 --bounce --bounce-speed 2.0 --bounce-amplitude 20
```

---

### 3. Custom Arrow Size and Colors

Change the arrow height (default: 80 pixels) and color:

```bash
# Red arrow with 100px height
python add_arrow_overlay.py input.mp4 --color red --scale 100

# Custom hex color (#33CCFF)
python add_arrow_overlay.py input.mp4 --color "#33CCFF" --arrow-height 90
```

Supported preset color names: `yellow` (default), `red`, `green`, `cyan`, `orange`, `white`, `magenta`, or any `#RRGGBB` hex code.

---

### 4. Non-Interactive / Scripting Mode

Specify coordinates directly via `--coords X Y` to bypass the interactive GUI:

```bash
python add_arrow_overlay.py input.mp4 --coords 640 360 --bounce -o output.mp4
```

---

### 5. Seek to a Specific Time & Set Display Duration

If there is a clear frame of you at `1:02` where you want to lock the arrow, but you want the arrow to appear **from the start of the video (0:00) up to 50 seconds**:

```bash
python add_arrow_overlay.py input.mp4 --seek 1:02 --end 50 --bounce
```

- `--seek 1:02`: Opens the interactive picker directly at **1:02** so you can click on yourself.
- `--end 50` (or `--duration 50` or `--end 0:50`): Keeps the arrow visible from `0:00` until `0:50` (50 seconds in), then the arrow disappears while the rest of the video plays normally.
- `--fade 0.5`: *(Optional)* Adds a 0.5-second smooth fade-out when the arrow disappears.

---

## Command-Line Options

| Argument | Description | Default |
|---|---|---|
| `input` | Path to input video file (e.g. `input.mp4`) | *Required* |
| `-o`, `--output` | Destination output file path | `<input_stem>_arrow.mp4` |
| `-c`, `--coords X Y` | Single coordinate of arrow tip (bypasses GUI) | Interactive tracker |
| `--waypoints` | Predefined waypoints (e.g. `'0:100,200; 15:300,400'`) | Interactive tracker |
| `--motion` | Motion mode: `linear` (smooth glide) or `hold` (step) | `linear` |
| `--bounce` | Enable gentle sinusoidal bobbing motion | `False` |
| `--bounce-amplitude` | Vertical bounce distance in pixels | 18% of arrow height |
| `--bounce-speed` | Bounce frequency in Hz (cycles/sec) | `1.5` |
| `--scale`, `--arrow-height` | Total arrow height in pixels | `80` |
| `--color` | Fill color (preset name or `#RRGGBB`) | `yellow` |
| `--style` | Visual style (`modern` or `flat`) | `modern` |
| `--seek` | Timestamp to open in picker (e.g. `1:02` or `62`) | `0:00` |
| `--start` | Timestamp when arrow appears | `0:00` |
| `--end`, `--until` | Timestamp when arrow disappears (e.g. `50` or `0:50`) | End of video |
| `--duration` | Total duration arrow stays visible (e.g. `50`) | Full video |
| `--fade` | Smooth fade-in / fade-out duration in seconds | `0.0` (instant) |
| `--seek-frame` | Frame index for interactive picker | `0` |
| `--crf` | H.264 video quality (lower = higher quality) | `18` |
| `--preset` | FFmpeg x264 encoding preset | `fast` |

---

## Technical Details

- **Video Stream**: Encoded in H.264 (`libx264`) with `yuv420p` pixel format for universal compatibility across browsers, media players, and mobile devices.
- **Audio Stream**: Passed directly through with FFmpeg stream copy (`-c:a copy`), ensuring zero audio transcoding delay, zero quality degradation, and full preservation of multichannel or AAC/MP3 audio.
- **Piping Architecture**: Processed video frames are piped as raw BGR bytes to FFmpeg's standard input in real time, avoiding large uncompressed intermediate files on disk.
