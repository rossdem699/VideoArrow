#!/usr/bin/env python3
"""
add_arrow_overlay.py - Place an indicator arrow overlay above a person or object in a video.

Features:
- Interactive coordinate picker on video frame (click to position, Space/Enter to confirm).
- Procedural downward-pointing indicator arrow (bright fill with high-contrast dark outline).
- Optional gentle sinusoidal bobbing motion (--bounce).
- Lossless audio passthrough and fast H.264 encoding via FFmpeg.
- CLI coordinate support for automated / headless workflows.
"""

import argparse
import math
import os
import shutil
import subprocess
import sys
import time
from typing import Optional, Tuple

import cv2
import numpy as np

# Preset color dictionary in BGR format
COLOR_PRESETS = {
    "yellow": (0, 220, 255),    # High visibility bright golden-yellow
    "red": (40, 40, 240),       # High visibility vibrant red
    "green": (50, 220, 50),     # Bright lime green
    "cyan": (240, 220, 0),      # Bright cyan
    "orange": (0, 140, 255),    # Vivid orange
    "white": (245, 245, 245),   # Clean white
    "magenta": (220, 30, 220),  # Bright magenta
}


def parse_color(color_str: str) -> Tuple[int, int, int]:
    """Parse color name or hex (#RRGGBB) to BGR tuple."""
    name = color_str.strip().lower()
    if name in COLOR_PRESETS:
        return COLOR_PRESETS[name]

    if color_str.startswith("#"):
        hex_code = color_str.lstrip("#")
        if len(hex_code) == 6:
            r = int(hex_code[0:2], 16)
            g = int(hex_code[2:4], 16)
            b = int(hex_code[4:6], 16)
            return (b, g, r)

    # Fallback to yellow
    print(f"Warning: Unknown color '{color_str}', falling back to 'yellow'.")
    return COLOR_PRESETS["yellow"]


def parse_timestamp(val: str) -> float:
    """Parse timestamp string (e.g. '1:02', '01:02:15', '62', '62.5') into seconds."""
    val = val.strip()
    if ":" in val:
        parts = val.split(":")
        if len(parts) == 2:
            mins, secs = parts
            return float(mins) * 60.0 + float(secs)
        elif len(parts) == 3:
            hrs, mins, secs = parts
            return float(hrs) * 3600.0 + float(mins) * 60.0 + float(secs)
    return float(val)


def get_interpolated_coords(
    frame_idx: int,
    waypoints: dict,
    motion_mode: str = "linear",
) -> Optional[Tuple[int, int]]:
    """
    Interpolate (x, y) coordinates at frame_idx from waypoints {frame_idx: (x, y)}.
    motion_mode:
        'linear' - Smoothly glides between waypoints.
        'hold'   - Holds previous position until the next waypoint is reached.
    """
    if not waypoints:
        return None

    sorted_frames = sorted(waypoints.keys())

    # Single waypoint or before first waypoint
    if len(sorted_frames) == 1 or frame_idx <= sorted_frames[0]:
        return waypoints[sorted_frames[0]]

    # After last waypoint
    if frame_idx >= sorted_frames[-1]:
        return waypoints[sorted_frames[-1]]

    # Find enclosing waypoints
    for i in range(len(sorted_frames) - 1):
        f0 = sorted_frames[i]
        f1 = sorted_frames[i + 1]
        if f0 <= frame_idx <= f1:
            if motion_mode == "hold":
                return waypoints[f0]

            # Linear interpolation
            alpha = (frame_idx - f0) / float(f1 - f0)
            x0, y0 = waypoints[f0]
            x1, y1 = waypoints[f1]
            ix = int(round(x0 + alpha * (x1 - x0)))
            iy = int(round(y0 + alpha * (y1 - y0)))
            return (ix, iy)

    return waypoints[sorted_frames[-1]]


def parse_waypoints_arg(val: str, fps: float) -> dict:
    """
    Parse waypoints string argument into {frame_idx: (x, y)}.
    Formats:
        '0:100,200; 15:300,400; 1:02:450,420'
        or '100,200'
    """
    waypoints = {}
    items = [x.strip() for x in val.split(";") if x.strip()]
    for item in items:
        if ":" in item:
            parts = item.rsplit(":", 1)
            time_str, coord_str = parts[0], parts[1]
            t_sec = parse_timestamp(time_str)
            f_idx = int(round(t_sec * fps))
            x_str, y_str = coord_str.split(",")
            waypoints[f_idx] = (int(round(float(x_str))), int(round(float(y_str))))
        else:
            x_str, y_str = item.split(",")
            waypoints[0] = (int(round(float(x_str))), int(round(float(y_str))))
    return waypoints


def check_ffmpeg() -> bool:
    """Verify that FFmpeg executable is installed and available in PATH."""
    return shutil.which("ffmpeg") is not None


def draw_arrow(
    img: np.ndarray,
    tx: int,
    ty: int,
    height: int = 80,
    color: Tuple[int, int, int] = (0, 220, 255),
    style: str = "modern",
) -> None:
    """
    Procedurally draw a clean, downward-pointing indicator arrow pointing at (tx, ty).

    The arrow is rendered above the tip (from ty - height down to ty).
    """
    h = float(height)
    head_height = h * 0.44
    head_width = h * 0.62
    stem_width = h * 0.28

    # Outer polygon vertices
    # Tip at (tx, ty), extending upwards
    outline_pts = np.array(
        [
            [tx, ty],
            [int(round(tx + head_width / 2.0)), int(round(ty - head_height))],
            [int(round(tx + stem_width / 2.0)), int(round(ty - head_height))],
            [int(round(tx + stem_width / 2.0)), int(round(ty - h))],
            [int(round(tx - stem_width / 2.0)), int(round(ty - h))],
            [int(round(tx - stem_width / 2.0)), int(round(ty - head_height))],
            [int(round(tx - head_width / 2.0)), int(round(ty - head_height))],
        ],
        dtype=np.int32,
    )

    border_thickness = max(2, int(round(h * 0.055)))
    border_color = (15, 15, 15)  # Near-black dark outline

    if style == "modern":
        # 3D beveled effect: split arrow down the center
        # Left half is slightly highlighted, right half is slightly shaded
        b, g, r = color
        left_color = (
            min(255, int(b * 1.08)),
            min(255, int(g * 1.08)),
            min(255, int(r * 1.08)),
        )
        right_color = (
            int(b * 0.78),
            int(g * 0.78),
            int(r * 0.78),
        )

        left_pts = np.array(
            [
                [tx, ty],
                [tx, int(round(ty - h))],
                [int(round(tx - stem_width / 2.0)), int(round(ty - h))],
                [int(round(tx - stem_width / 2.0)), int(round(ty - head_height))],
                [int(round(tx - head_width / 2.0)), int(round(ty - head_height))],
            ],
            dtype=np.int32,
        )

        right_pts = np.array(
            [
                [tx, ty],
                [int(round(tx + head_width / 2.0)), int(round(ty - head_height))],
                [int(round(tx + stem_width / 2.0)), int(round(ty - head_height))],
                [int(round(tx + stem_width / 2.0)), int(round(ty - h))],
                [tx, int(round(ty - h))],
            ],
            dtype=np.int32,
        )

        cv2.fillPoly(img, [left_pts], left_color, lineType=cv2.LINE_AA)
        cv2.fillPoly(img, [right_pts], right_color, lineType=cv2.LINE_AA)

        # Draw subtle center crease line
        cv2.line(
            img,
            (tx, ty),
            (tx, int(round(ty - h))),
            border_color,
            thickness=max(1, border_thickness // 2),
            lineType=cv2.LINE_AA,
        )
    else:
        # Flat style
        cv2.fillPoly(img, [outline_pts], color, lineType=cv2.LINE_AA)

    # Outer border for crisp contrast on light and dark backgrounds
    cv2.polylines(
        img,
        [outline_pts],
        isClosed=True,
        color=border_color,
        thickness=border_thickness,
        lineType=cv2.LINE_AA,
    )


def interactive_pick_coordinates(
    video_path: str,
    arrow_height: int = 80,
    color: Tuple[int, int, int] = (0, 220, 255),
    style: str = "modern",
    seek_frame: int = 0,
    seek_sec: Optional[float] = None,
    initial_waypoints: Optional[dict] = None,
    default_motion: str = "linear",
) -> Optional[Tuple[dict, str]]:
    """
    Open an interactive OpenCV window displaying video frames.
    Allows user to place multiple waypoints across time:
    - Click to add/update arrow position at current frame.
    - Scrub through video with A/D, [/], ,/.
    - Live preview of interpolated motion between waypoints.
    - Toggle motion mode between 'linear' (smooth glide) and 'hold' (step change) with 'M'.
    - Press Enter or Space to confirm all waypoints and begin video encoding.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Unable to open video: {video_path}", file=sys.stderr)
        return None

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    current_frame = seek_frame
    if seek_sec is not None:
        current_frame = int(round(seek_sec * fps))

    current_frame = max(0, min(current_frame, max(0, total_frames - 1)))

    def load_frame(f_idx: int) -> Optional[np.ndarray]:
        cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
        ret, frame = cap.read()
        return frame if ret else None

    base_frame = load_frame(current_frame)
    if base_frame is None:
        print("Error: Could not read frame from video.", file=sys.stderr)
        cap.release()
        return None

    frame_h, frame_w = base_frame.shape[:2]
    window_name = "Keyframe Arrow Tracker - [Click] Set Keyframe | [A/D] Seek | [M] Motion Mode | [Enter] Confirm"

    # State variables
    state = {
        "waypoints": dict(initial_waypoints or {}),
        "motion_mode": default_motion,
        "hover_pt": None,
        "confirmed": False,
        "cancelled": False,
        "current_frame": current_frame,
        "frame_dirty": False,
    }

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            state["waypoints"][state["current_frame"]] = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE:
            state["hover_pt"] = (x, y)

    try:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        disp_w = min(frame_w, 1280)
        disp_h = int(round(frame_h * (disp_w / frame_w)))
        cv2.resizeWindow(window_name, disp_w, disp_h)
        cv2.setMouseCallback(window_name, on_mouse)
    except cv2.error as e:
        print(
            f"Notice: OpenCV GUI error ({e}). If running in a headless environment, "
            "please specify coordinates via --coords X Y or --waypoints.",
            file=sys.stderr,
        )
        cap.release()
        return None

    cur_sec = current_frame / fps
    mins = int(cur_sec // 60)
    secs = cur_sec % 60
    print("\n--- Interactive Multi-Waypoint Arrow Tracker ---")
    print(f"Opened at {mins:02d}:{secs:04.1f} (frame {current_frame}/{total_frames})")
    print("Controls:")
    print("  • Left-Click:     Place or adjust a keyframe at the current frame")
    print("  • A / D:          Seek -1s / +1s")
    print("  • [ / ]:          Seek -5s / +5s")
    print("  • , / .:          Step -1 frame / +1 frame")
    print("  • M:              Toggle motion mode (Smooth Glide vs Hold/Step)")
    print("  • Z / Backspace:  Delete keyframe at current frame (or last keyframe)")
    print("  • C:              Clear all keyframes")
    print("  • Enter / Space:  Confirm all keyframes and render video")
    print("  • Q / Esc:        Cancel\n")

    try:
        while True:
            if state["frame_dirty"]:
                new_frame = load_frame(state["current_frame"])
                if new_frame is not None:
                    base_frame = new_frame
                state["frame_dirty"] = False

            display_frame = base_frame.copy()
            cur_f = state["current_frame"]

            # Draw visual motion path connecting keyframes
            if len(state["waypoints"]) >= 2:
                sorted_f = sorted(state["waypoints"].keys())
                path_pts = np.array([state["waypoints"][f] for f in sorted_f], dtype=np.int32)
                cv2.polylines(display_frame, [path_pts], isClosed=False, color=(50, 180, 255), thickness=1, lineType=cv2.LINE_AA)

            # Draw small marker dots for all keyframes
            for kf_frame, (kx, ky) in state["waypoints"].items():
                if kf_frame == cur_f:
                    # Highlight current keyframe with green ring
                    cv2.circle(display_frame, (kx, ky), 9, (0, 255, 0), 2, lineType=cv2.LINE_AA)
                    cv2.circle(display_frame, (kx, ky), 3, (0, 255, 0), -1, lineType=cv2.LINE_AA)
                else:
                    cv2.circle(display_frame, (kx, ky), 4, (50, 180, 255), -1, lineType=cv2.LINE_AA)

            # Determine arrow position to render on preview
            active_pt = None
            if state["waypoints"]:
                active_pt = get_interpolated_coords(cur_f, state["waypoints"], state["motion_mode"])
            elif state["hover_pt"] is not None:
                active_pt = state["hover_pt"]

            if active_pt is not None:
                ax, ay = active_pt
                draw_arrow(
                    display_frame,
                    tx=ax,
                    ty=ay,
                    height=arrow_height,
                    color=color,
                    style=style,
                )
                cv2.circle(display_frame, (ax, ay), 3, (0, 0, 255), -1, lineType=cv2.LINE_AA)
                cv2.circle(display_frame, (ax, ay), 7, (255, 255, 255), 1, lineType=cv2.LINE_AA)

            # Top banner overlay for status & controls
            banner_h = 50
            overlay = display_frame.copy()
            cv2.rectangle(overlay, (0, 0), (frame_w, banner_h), (20, 20, 20), -1)
            cv2.addWeighted(overlay, 0.80, display_frame, 0.20, 0, display_frame)

            cur_t = cur_f / fps
            m = int(cur_t // 60)
            s = cur_t % 60
            kf_count = len(state["waypoints"])
            mode_lbl = "Smooth Glide" if state["motion_mode"] == "linear" else "Hold/Step"
            line1 = f"Time: {m:02d}:{s:04.1f} [F#{cur_f}/{total_frames}]  |  Keyframes: {kf_count}  |  Mode: [{mode_lbl}] (M)"

            if cur_f in state["waypoints"]:
                px, py = state["waypoints"][cur_f]
                line2 = f"[★ Keyframe @ ({px}, {py})] Click to move | [Z] Delete | [A/D] Seek | [Enter] Confirm"
                line2_color = (0, 255, 0)
            elif active_pt is not None:
                line2 = f"Arrow at ({active_pt[0]}, {active_pt[1]}) | Left-Click to add keyframe here | [Enter] Confirm"
                line2_color = (0, 230, 255)
            else:
                line2 = "Left-Click on yourself to place initial arrow | [A/D] Seek time | [Q] Quit"
                line2_color = (240, 240, 240)

            cv2.putText(display_frame, line1, (16, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (200, 200, 200), 1, lineType=cv2.LINE_AA)
            cv2.putText(display_frame, line2, (16, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.56, line2_color, 2, lineType=cv2.LINE_AA)

            cv2.imshow(window_name, display_frame)
            key = cv2.waitKey(20) & 0xFF

            if key in (13, 32):  # Enter or Space
                if state["waypoints"]:
                    state["confirmed"] = True
                    break
                else:
                    print("Please click on the frame to place at least one arrow position before confirming.")
            elif key in (ord("m"), ord("M")):
                state["motion_mode"] = "hold" if state["motion_mode"] == "linear" else "linear"
                print(f"Motion mode toggled to: {state['motion_mode'].upper()}")
            elif key in (ord("z"), ord("Z"), 8, 127):  # Z or Backspace: delete keyframe
                if cur_f in state["waypoints"]:
                    del state["waypoints"][cur_f]
                    print(f"Deleted keyframe at frame {cur_f}.")
                elif state["waypoints"]:
                    # Delete most recent or closest keyframe
                    closest_f = min(state["waypoints"].keys(), key=lambda f: abs(f - cur_f))
                    del state["waypoints"][closest_f]
                    print(f"Deleted nearest keyframe at frame {closest_f}.")
            elif key in (ord("c"), ord("C")):
                state["waypoints"].clear()
                print("Cleared all keyframes.")
            elif key in (27, ord("q"), ord("Q")):  # Esc or Q
                state["cancelled"] = True
                break
            # Frame scrubbing controls
            elif key in (ord("d"), ord("D"), 83):  # D or Right arrow: +1s
                step = max(1, int(round(fps)))
                state["current_frame"] = min(total_frames - 1, state["current_frame"] + step)
                state["frame_dirty"] = True
            elif key in (ord("a"), ord("A"), 81):  # A or Left arrow: -1s
                step = max(1, int(round(fps)))
                state["current_frame"] = max(0, state["current_frame"] - step)
                state["frame_dirty"] = True
            elif key == ord("]"):  # +5s
                step = max(1, int(round(fps * 5)))
                state["current_frame"] = min(total_frames - 1, state["current_frame"] + step)
                state["frame_dirty"] = True
            elif key == ord("["):  # -5s
                step = max(1, int(round(fps * 5)))
                state["current_frame"] = max(0, state["current_frame"] - step)
                state["frame_dirty"] = True
            elif key in (ord("."), ord(">")):  # +1 frame
                state["current_frame"] = min(total_frames - 1, state["current_frame"] + 1)
                state["frame_dirty"] = True
            elif key in (ord(","), ord("<")):  # -1 frame
                state["current_frame"] = max(0, state["current_frame"] - 1)
                state["frame_dirty"] = True
    finally:
        cap.release()
        cv2.destroyAllWindows()

    if state["confirmed"] and state["waypoints"]:
        return state["waypoints"], state["motion_mode"]
    return None


def process_video(
    input_path: str,
    output_path: str,
    waypoints: dict,
    motion_mode: str = "linear",
    arrow_height: int = 80,
    color: Tuple[int, int, int] = (0, 220, 255),
    style: str = "modern",
    bounce: bool = False,
    bounce_amplitude: Optional[float] = None,
    bounce_speed: float = 1.5,
    start_sec: float = 0.0,
    end_sec: Optional[float] = None,
    fade_sec: float = 0.0,
    crf: int = 18,
    preset: str = "fast",
) -> bool:
    """
    Read input video, apply procedural arrow overlay along waypoints within [start_sec, end_sec],
    and encode with FFmpeg preserving original audio track losslessly.
    """
    if not os.path.exists(input_path):
        print(f"Error: Input video does not exist: {input_path}", file=sys.stderr)
        return False

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f"Error: Unable to open input video: {input_path}", file=sys.stderr)
        return False

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0 or math.isnan(fps):
        fps = 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frames / fps if total_frames > 0 else 0

    end_time_limit = end_sec if end_sec is not None else float("inf")
    end_display = f"{end_sec:.1f}s" if end_sec is not None else "end of video"

    print("\n--- Video Information ---")
    print(f"Input:       {input_path}")
    print(f"Output:      {output_path}")
    print(f"Resolution:  {width}x{height}")
    print(f"Framerate:   {fps:.2f} fps")
    print(f"Frames:      {total_frames} (~{duration_sec:.1f}s)")
    print(f"Keyframes:   {len(waypoints)} waypoint(s), Motion={motion_mode.upper()}")
    print(f"Visibility:  {start_sec:.1f}s to {end_display}")
    print(f"Arrow:       Height={arrow_height}px, Style={style}, Bounce={bounce}")

    if bounce_amplitude is None:
        bounce_amplitude = max(8.0, arrow_height * 0.18)

    # Prepare FFmpeg pipeline
    # Pipe raw BGR frames through stdin to FFmpeg, stream-copying audio from input
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-loglevel", "error",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{width}x{height}",
        "-pix_fmt", "bgr24",
        "-r", f"{fps:.6f}",
        "-i", "-",               # Stream 0: Raw video frames via stdin
        "-i", input_path,         # Stream 1: Original file for audio
        "-map", "0:v:0",          # Video from stream 0
        "-map", "1:a?",           # Audio from stream 1 if present
        "-c:v", "libx264",        # H.264 video
        "-preset", preset,
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",    # Standard player compatibility
        "-c:a", "copy",           # Lossless audio passthrough
    ]
    if total_frames > 0 and fps > 0:
        ffmpeg_cmd.extend(["-t", f"{total_frames / fps:.6f}"])

    ffmpeg_cmd.append(output_path)

    try:
        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as e:
        print(f"Error launching FFmpeg: {e}", file=sys.stderr)
        cap.release()
        return False

    start_time = time.time()
    frame_idx = 0

    print("\nProcessing frames...")

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            t = frame_idx / fps

            # Check if arrow is visible at this timestamp
            if start_sec <= t <= end_time_limit:
                coords = get_interpolated_coords(frame_idx, waypoints, motion_mode)
                if coords is not None:
                    target_x, base_y = coords
                    current_y = base_y
                    if bounce:
                        # Gentle sinusoidal vertical bobbing: tip touches target at lowest point
                        phase = 2.0 * math.pi * bounce_speed * (t - start_sec) - (math.pi / 2.0)
                        dy = -0.5 * (1.0 + math.sin(phase)) * bounce_amplitude
                        current_y = int(round(base_y + dy))

                    # Handle optional fade-in / fade-out
                    alpha = 1.0
                    if fade_sec > 0.0:
                        if t < start_sec + fade_sec and start_sec > 0.0:
                            alpha = (t - start_sec) / fade_sec
                        elif t > end_time_limit - fade_sec and end_time_limit != float("inf"):
                            alpha = (end_time_limit - t) / fade_sec
                        alpha = max(0.0, min(1.0, alpha))

                    if alpha >= 0.999:
                        draw_arrow(
                            frame,
                            tx=target_x,
                            ty=current_y,
                            height=arrow_height,
                            color=color,
                            style=style,
                        )
                    elif alpha > 0.02:
                        overlay = frame.copy()
                        draw_arrow(
                            overlay,
                            tx=target_x,
                            ty=current_y,
                            height=arrow_height,
                            color=color,
                            style=style,
                        )
                        cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, frame)

            # Write frame to FFmpeg stdin
            try:
                proc.stdin.write(frame.tobytes())
            except (BrokenPipeError, IOError):
                # FFmpeg encountered an error
                break

            frame_idx += 1

            # Progress indicator
            if frame_idx % 15 == 0 or frame_idx == total_frames:
                elapsed = time.time() - start_time
                proc_fps = frame_idx / elapsed if elapsed > 0 else 0
                pct = (frame_idx / total_frames * 100) if total_frames > 0 else 0
                eta = (total_frames - frame_idx) / proc_fps if (proc_fps > 0 and total_frames > 0) else 0
                sys.stdout.write(
                    f"\rProgress: [{frame_idx}/{total_frames}] {pct:5.1f}% | "
                    f"Speed: {proc_fps:5.1f} fps | ETA: {eta:4.1f}s"
                )
                sys.stdout.flush()

    finally:
        cap.release()
        if proc.stdin:
            proc.stdin.close()
        stderr_data = proc.stderr.read() if proc.stderr else b""
        proc.wait()

    sys.stdout.write("\n")
    elapsed_total = time.time() - start_time

    if proc.returncode != 0:
        print(f"FFmpeg failed with return code {proc.returncode}:", file=sys.stderr)
        if stderr_data:
            print(stderr_data.decode("utf-8", errors="replace"), file=sys.stderr)
        return False

    out_size_mb = os.path.getsize(output_path) / (1024 * 1024) if os.path.exists(output_path) else 0
    print(f"Successfully created: {output_path} ({out_size_mb:.2f} MB)")
    print(f"Rendered {frame_idx} frames in {elapsed_total:.2f}s ({frame_idx / elapsed_total:.1f} fps avg).\n")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Add a procedural indicator arrow overlay above a person in a video."
    )
    parser.add_argument("input", help="Path to input video file (e.g., input.mp4)")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Path to output MP4 file (default: <input_stem>_arrow.mp4)",
    )
    parser.add_argument(
        "-c",
        "--coords",
        nargs=2,
        type=int,
        metavar=("X", "Y"),
        default=None,
        help="Target coordinates (tip of arrow). Skips interactive picker if provided.",
    )
    parser.add_argument(
        "--waypoints",
        default=None,
        help="Predefined waypoints (e.g. '0:100,200; 15:300,400; 1:02:450,420').",
    )
    parser.add_argument(
        "--motion",
        choices=["linear", "hold"],
        default="linear",
        help="Motion mode: 'linear' (smooth glide) or 'hold' (step change). Default: linear.",
    )
    parser.add_argument(
        "--bounce",
        action="store_true",
        help="Enable gentle sinusoidal vertical bobbing motion (video game player marker style).",
    )
    parser.add_argument(
        "--bounce-amplitude",
        type=float,
        default=None,
        help="Vertical bounce amplitude in pixels (default: 18%% of arrow height).",
    )
    parser.add_argument(
        "--bounce-speed",
        type=float,
        default=1.5,
        help="Bobbing frequency in Hz (cycles per second, default: 1.5).",
    )
    parser.add_argument(
        "--arrow-height",
        "--scale",
        type=int,
        default=80,
        dest="arrow_height",
        help="Total height of the arrow in pixels (default: 80).",
    )
    parser.add_argument(
        "--color",
        default="yellow",
        help="Arrow fill color (yellow, red, green, cyan, orange, white, magenta, or hex #RRGGBB; default: yellow).",
    )
    parser.add_argument(
        "--style",
        choices=["modern", "flat"],
        default="modern",
        help="Visual style: 'modern' (3D beveled with contrast outline) or 'flat' (solid fill with contrast outline).",
    )
    parser.add_argument(
        "--seek-frame",
        type=int,
        default=0,
        help="Frame number to display in interactive coordinate picker (default: 0).",
    )
    parser.add_argument(
        "--seek",
        "--seek-sec",
        "--seek-time",
        dest="seek_time",
        default=None,
        help="Timestamp to seek to in the coordinate picker (e.g. '1:02', '01:02:15', or seconds '62').",
    )
    parser.add_argument(
        "--start",
        "--start-time",
        dest="start_time",
        default="0",
        help="Timestamp when arrow should appear (e.g. '0:00', '10', or '1:02'; default: 0).",
    )
    parser.add_argument(
        "--end",
        "--end-time",
        "--until",
        dest="end_time",
        default=None,
        help="Timestamp when arrow should disappear (e.g. '50', '0:50', or '1:20'; default: end of video).",
    )
    parser.add_argument(
        "--duration",
        default=None,
        help="Duration the arrow remains visible (e.g. '50' or '0:50').",
    )
    parser.add_argument(
        "--fade",
        type=float,
        default=0.0,
        help="Fade-in and fade-out transition in seconds (e.g. 0.5; default: 0.0 = instant).",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=18,
        help="H.264 Constant Rate Factor (CRF, lower = higher quality, default: 18).",
    )
    parser.add_argument(
        "--preset",
        default="fast",
        choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
        help="FFmpeg x264 encoding preset (default: fast).",
    )

    args = parser.parse_args()

    # Parse seek timestamp if provided
    seek_seconds = None
    if args.seek_time:
        try:
            seek_seconds = parse_timestamp(args.seek_time)
        except ValueError:
            print(f"Error: Invalid seek timestamp '{args.seek_time}'. Use formats like '1:02', '62', or '01:02:30'.", file=sys.stderr)
            sys.exit(1)

    # Parse visibility time window
    start_sec = 0.0
    if args.start_time:
        try:
            start_sec = parse_timestamp(args.start_time)
        except ValueError:
            print(f"Error: Invalid --start timestamp '{args.start_time}'.", file=sys.stderr)
            sys.exit(1)

    end_sec = None
    if args.end_time:
        try:
            end_sec = parse_timestamp(args.end_time)
        except ValueError:
            print(f"Error: Invalid --end timestamp '{args.end_time}'.", file=sys.stderr)
            sys.exit(1)
    elif args.duration:
        try:
            dur = parse_timestamp(args.duration)
            end_sec = start_sec + dur
        except ValueError:
            print(f"Error: Invalid --duration '{args.duration}'.", file=sys.stderr)
            sys.exit(1)

    if end_sec is not None and end_sec <= start_sec:
        print(f"Error: --end time ({end_sec}s) must be greater than --start time ({start_sec}s).", file=sys.stderr)
        sys.exit(1)

    # Verify FFmpeg
    if not check_ffmpeg():
        print(
            "Error: FFmpeg is required but not found in system PATH.\n"
            "Please install FFmpeg (e.g. 'sudo apt install ffmpeg' or 'brew install ffmpeg').",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate input video
    if not os.path.isfile(args.input):
        print(f"Error: Input video file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Determine output filename
    if args.output:
        output_path = args.output
    else:
        root, _ = os.path.splitext(args.input)
        output_path = f"{root}_arrow.mp4"

    # Arrow color
    arrow_color = parse_color(args.color)

    # Coordinate and waypoints selection
    waypoints = {}
    motion_mode = args.motion

    if args.waypoints:
        cap_temp = cv2.VideoCapture(args.input)
        video_fps = cap_temp.get(cv2.CAP_PROP_FPS) or 30.0
        cap_temp.release()
        waypoints = parse_waypoints_arg(args.waypoints, video_fps)
        print(f"Using {len(waypoints)} predefined CLI waypoint(s).")
    elif args.coords is not None:
        target_x, target_y = args.coords
        waypoints = {0: (target_x, target_y)}
        print(f"Using supplied coordinates: ({target_x}, {target_y})")
    else:
        # Launch interactive keyframe tracker
        picked = interactive_pick_coordinates(
            video_path=args.input,
            arrow_height=args.arrow_height,
            color=arrow_color,
            style=args.style,
            seek_frame=args.seek_frame,
            seek_sec=seek_seconds,
            default_motion=args.motion,
        )
        if picked is None:
            print("Keyframe selection cancelled or unavailable. Exiting.")
            sys.exit(0)
        waypoints, motion_mode = picked

        cap_temp = cv2.VideoCapture(args.input)
        video_fps = cap_temp.get(cv2.CAP_PROP_FPS) or 30.0
        cap_temp.release()
        print(f"\nLocked in {len(waypoints)} waypoint(s) [{motion_mode.upper()} mode]:")
        for f in sorted(waypoints.keys()):
            sec = f / video_fps
            m = int(sec // 60)
            s = sec % 60
            print(f"  • {m:02d}:{s:04.1f} (frame {f}) -> Tip at {waypoints[f]}")

    # Render video
    success = process_video(
        input_path=args.input,
        output_path=output_path,
        waypoints=waypoints,
        motion_mode=motion_mode,
        arrow_height=args.arrow_height,
        color=arrow_color,
        style=args.style,
        bounce=args.bounce,
        bounce_amplitude=args.bounce_amplitude,
        bounce_speed=args.bounce_speed,
        start_sec=start_sec,
        end_sec=end_sec,
        fade_sec=args.fade,
        crf=args.crf,
        preset=args.preset,
    )

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
