# VideoArrow: Tool Description & Technical Overview

## What is VideoArrow?

**VideoArrow** is a lightweight, standalone Python command-line utility that overlays an animated, high-visibility player-indicator arrow above a person or object in any video.

Inspired by video-game player markers (e.g. sports games, esports highlights, tactical analyses), VideoArrow makes it easy to highlight yourself or any subject in crowded or fast-moving footage without requiring complex video-editing suites like Adobe Premiere or DaVinci Resolve.

---

## Key Capabilities & Features

### 1. Interactive Keyframe & Multi-Waypoint Tracking
- **Scrub & Click**: Navigate through the video frame-by-frame or second-by-second using keyboard shortcuts (<kbd>A</kbd>/<kbd>D</kbd> or <kbd>[</kbd>/<kbd>]</kbd>).
- **Smooth Glide Motion**: Place an arrow at the start, scrub forward to where you move, click again, and the arrow smoothly glides between your waypoints.
- **Hold / Step Mode**: Press <kbd>M</kbd> to toggle between smooth linear motion and step/hold mode (where the arrow stays fixed until you reach the next keyframe).
- **Live Preview**: See the active arrow trajectory and path right in the preview window as you scrub.

### 2. Procedural Downward-Pointing Arrow
- **Zero External Assets**: The arrow is procedurally generated with mathematical precision directly using OpenCV. No PNG images or external graphics needed.
- **High Contrast on Any Background**: Features a bold, dark outline (`LINE_AA`) and a 3D beveled split-shading effect (highlighted left half, shaded right half) so it stays sharp and visible against bright skies, dark crowds, and busy playing fields.
- **Customizable**: Choose between preset colors (`yellow`, `red`, `green`, `cyan`, `orange`, `white`, `magenta`) or any custom hex code (`#RRGGBB`), with customizable arrow height/scale.

### 3. Sinusoidal Vertical Bobbing (`--bounce`)
- Adds a gentle vertical bobbing motion (video game marker style) without camera or tracking jitter.
- Smooth sinusoidal physics where the tip of the arrow reaches the target point at the lowest point of each cycle and bobs gently upward.

### 4. Customizable Display Window & Fade Transitions
- `--start`: Specify when the arrow should appear (e.g. `--start 0:10`).
- `--end` / `--duration`: Specify when the arrow disappears (e.g. `--end 50` for the first 50 seconds), after which the video continues playing normally.
- `--fade`: Add a smooth transition (e.g. `--fade 0.5` for a 0.5s fade-out).

### 5. Lossless Audio Passthrough & Fast Video Encoding
- **Lossless Audio**: Directly stream-copies the original audio track (`-c:a copy`) with FFmpeg, preventing audio degradation or desynchronization.
- **Raw Frame Piping**: Piped directly to FFmpeg (`libx264`, `yuv420p`) via stdin for maximum encoding speed (200+ fps on modern hardware) with minimal memory footprint and zero intermediate disk files.

---

## Quick Installation & Usage

### 1. System Requirements
- Python 3.8+
- FFmpeg (`sudo apt install ffmpeg` on Ubuntu/Debian, `brew install ffmpeg` on macOS)

### 2. Setup
```bash
git clone https://github.com/rossdem699/VideoArrow.git
cd VideoArrow
pip install -r requirements.txt
```

### 3. Quick Run
```bash
# Basic interactive tracker
python add_arrow_overlay.py input.mp4

# With bouncing motion, visible for the first 50 seconds
python add_arrow_overlay.py input.mp4 --bounce --end 50

# Jump to 1:02 to set coordinates on a clear frame
python add_arrow_overlay.py input.mp4 --seek 1:02 --bounce --end 50
```
