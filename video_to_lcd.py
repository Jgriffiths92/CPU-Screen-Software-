import threading
import socket
import json
import time
import numpy as np
import sys
import os
import tempfile
import subprocess
from LCDProtocol import LCDDevice
from frame_utils import rgb24_to_rgb565, make_test_pattern
import cv2
overlay_texts = {'cpu': '', 'gpu': ''}
overlay_lock = threading.Lock()

def process_frames(proc, lcd, frame_count, frame_size, height, width, rotate_angle, cpu_overlay=None, gpu_overlay=None):
    global overlay_texts, overlay_lock
    # Only set initial overlay text if still empty (never clear overlays after a video loop)
    with overlay_lock:
        # Only set initial overlay text if still empty (never clear overlays after a video loop)
        if cpu_overlay and not overlay_texts['cpu']:
            overlay_texts['cpu'] = cpu_overlay[0]
        if gpu_overlay and not overlay_texts['gpu']:
            overlay_texts['gpu'] = gpu_overlay[0]
    print(f"[DEBUG] Initial overlay_texts: {overlay_texts}")

    def overlay_server():
        HOST, PORT = '127.0.0.1', 56789
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(5)  # allow up to 5 queued connections
        s.settimeout(0.2)  # short timeout for accept
        while True:
            try:
                conn, _ = s.accept()
            except socket.timeout:
                continue
            try:
                conn.settimeout(0.2)
                data = b''
                while True:
                    try:
                        chunk = conn.recv(1024)
                        if not chunk:
                            break
                        data += chunk
                    except socket.timeout:
                        break
                try:
                    msg = json.loads(data.decode('utf-8'))
                    with overlay_lock:
                        if 'cpu' in msg and msg['cpu']:
                            overlay_texts['cpu'] = msg['cpu']
                            print(f"[DEBUG] Updated overlay_texts['cpu']: {overlay_texts['cpu']}")
                        if 'gpu' in msg and msg['gpu']:
                            overlay_texts['gpu'] = msg['gpu']
                            print(f"[DEBUG] Updated overlay_texts['gpu']: {overlay_texts['gpu']}")
                except Exception as e:
                    print(f"[OVERLAY SERVER] Bad message: {e}")
            finally:
                conn.close()

    # Start overlay server thread
    threading.Thread(target=overlay_server, daemon=True).start()
    target_fps = 15
    min_frame_time = 1.0 / target_fps
    while True:
        frame_start = time.time()
        raw_frame = proc.stdout.read(frame_size)
        if len(raw_frame) < frame_size:
            return frame_count, False
        frame = np.frombuffer(raw_frame, np.uint8).reshape((height, width, 3)).copy()
        # Draw overlays BEFORE orientation transforms so LCD matches preview
        with overlay_lock:
            cpu_text = overlay_texts['cpu']
            gpu_text = overlay_texts['gpu']
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 1
        if cpu_overlay and cpu_text:
            x, y = cpu_overlay[1:]
            cv2.putText(frame, cpu_text, (x, y), font, font_scale, (0, 255, 255), thickness, cv2.LINE_AA)
        if gpu_overlay and gpu_text:
            x, y = gpu_overlay[1:]
            cv2.putText(frame, gpu_text, (x, y), font, font_scale, (255, 255, 0), thickness, cv2.LINE_AA)
        # Now apply LCD orientation: transpose and rotate 180°
        frame = np.transpose(frame, (1, 0, 2))
        frame = cv2.rotate(frame, cv2.ROTATE_180)
        frame = cv2.flip(frame, 0)  # Vertical flip to fix orientation
        pixel_data = rgb24_to_rgb565(frame)
        lcd.send_frame(pixel_data, width=320, height=240)
        frame_count += 1
        elapsed = time.time() - frame_start
        if elapsed < min_frame_time:
            time.sleep(min_frame_time - elapsed)
    return frame_count, True

# --- Patch: fix cpu_overlay/gpu_overlay undefined in main() ---
def parse_overlay_args():
    cpu_overlay = None
    gpu_overlay = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '--cpu-overlay' and i+1 < len(args):
            try:
                x_str, y_str = args[i+1].split(',')
                x, y = int(x_str), int(y_str)
                cpu_overlay = ("CPU", x, y)
            except Exception:
                pass
            i += 2
        elif arg == '--gpu-overlay' and i+1 < len(args):
            try:
                x_str, y_str = args[i+1].split(',')
                x, y = int(x_str), int(y_str)
                gpu_overlay = ("GPU", x, y)
            except Exception:
                pass
            i += 2
        else:
            i += 1
    return cpu_overlay, gpu_overlay

# --- Main program ---
def main():
    def rotate_video(input_path, output_path, angle):
        cap = cv2.VideoCapture(input_path)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if angle in [90, 270]:
            out_size = (height, width)
        else:
            out_size = (width, height)
        out = cv2.VideoWriter(output_path, fourcc, fps, out_size)
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if angle == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif angle == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif angle == 270:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            out.write(frame)
        cap.release()
        out.release()

    print("[DEBUG] Entered main()")
    width, height = 320, 240
    lcd = LCDDevice()
    print("[DEBUG] LCDDevice instantiated in main()")

    # Check for test pattern argument
    test_pattern = None
    input_file = 'input.mp4'
    rotate_angle = 0
    crop_arg = None

    # Parse overlays
    global overlay_texts, overlay_lock
    cpu_overlay, gpu_overlay = parse_overlay_args()

    for i, arg in enumerate(sys.argv[1:]):
        if arg.startswith('--test-pattern'):
            parts = arg.split('=')
            if len(parts) == 2:
                test_pattern = parts[1].strip().lower()
            else:
                test_pattern = 'red'
        elif arg == '--input' and i+2 <= len(sys.argv[1:]):
            input_file = sys.argv[i+2]
        elif arg == '--rotate' and i+2 <= len(sys.argv[1:]):
            try:
                rotate_angle = int(sys.argv[i+2])
            except Exception:
                rotate_angle = 0
        elif arg.startswith('--crop'):
            # Accept --crop=WxH+X+Y or --crop WxH+X+Y
            if '=' in arg:
                crop_arg = arg.split('=', 1)[1].strip()
            elif i+2 <= len(sys.argv[1:]):
                crop_arg = sys.argv[i+2]

    # If rotate_angle is set, rotate the video in Python and use the temp file as input
    if rotate_angle in [90, 180, 270]:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.mp4')
        os.close(tmp_fd)
        print(f"[DEBUG] Rotating video {input_file} by {rotate_angle} degrees to {tmp_path}")
        rotate_video(input_file, tmp_path, rotate_angle)
        input_file = tmp_path


    try:
        if test_pattern:
            frame = make_test_pattern(240, 320, test_pattern)  # shape (320,240,3)
            # No rotation applied
            # Convert hex color string to BGR tuple
            # Test pattern loop (not shown for brevity)
            # ...existing test pattern loop code...
        else:
            # Video playback mode
            # Build ffmpeg command
            ffmpeg_cmd = [
                'ffmpeg',
                '-hide_banner', '-loglevel', 'error',
                '-noautorotate',
                '-i', input_file,
                '-vf', 'scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2,setdar=4/3',
                '-f', 'rawvideo',
                '-pix_fmt', 'rgb24',
                '-r', '15',
                '-an', '-sn', '-dn',
                '-y', '-'
            ]
            if crop_arg:
                # Always use crop=w:h:x:y (colons) for ffmpeg -vf filter
                crop_ffmpeg = crop_arg
                if ':' in crop_arg:
                    parts = crop_arg.split(':')
                    if len(parts) == 4 and all(p.isdigit() for p in parts):
                        w, h, x, y = parts
                        crop_ffmpeg = f'{w}:{h}:{x}:{y}'
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-hide_banner', '-loglevel', 'error',
                    '-noautorotate',
                    '-i', input_file,
                    '-vf', f'crop={crop_ffmpeg},scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2,setdar=4/3',
                    '-f', 'rawvideo',
                    '-pix_fmt', 'rgb24',
                    '-r', '15',
                    '-an', '-sn', '-dn',
                    '-y', '-'
                ]
            frame_size = width * height * 3
            frame_count = 0
            while True:
                try:
                    proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**8)
                    process_frames(proc, lcd, frame_count, frame_size, height, width, rotate_angle, cpu_overlay=cpu_overlay, gpu_overlay=gpu_overlay)
                    if proc.stdout:
                        proc.stdout.close()
                    proc.wait()
                    # Always read and print/log ffmpeg stderr after process ends
                    try:
                        if proc.stderr:
                            err = proc.stderr.read()
                            if err:
                                print(f"[DEBUG] ffmpeg stderr (main loop):\n{err.decode(errors='replace')}")
                                with open('output.txt', 'a') as outf:
                                    outf.write(f"[DEBUG] ffmpeg stderr (main loop):\n{err.decode(errors='replace')}")
                            else:
                                print("[DEBUG] ffmpeg stderr is empty (main loop).")
                                with open('output.txt', 'a') as outf:
                                    outf.write("[DEBUG] ffmpeg stderr is empty (main loop).\n")
                    except Exception as e:
                        print(f"[DEBUG] Could not read ffmpeg stderr in main loop: {e}")
                    if proc.stderr:
                        proc.stderr.close()
                except Exception as e:
                    print(f"[DEBUG] Exception in video loop: {e}")
                print("[DEBUG] End of video reached, looping...")
                import time as _time
                _time.sleep(0.2)
    except KeyboardInterrupt:
        print("[DEBUG] Video loop interrupted by user.")

if __name__ == "__main__":
    main()