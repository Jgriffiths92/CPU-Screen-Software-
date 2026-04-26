import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import subprocess
import os
import sys
from PIL import Image, ImageTk
import numpy as np
import cv2

# Path to your video_to_lcd.py script
VIDEO_SCRIPT = os.path.join(os.path.dirname(__file__), 'video_to_lcd.py')


class LCDVideoUI:
    def update_stats(self):
        import psutil
        import GPUtil
        import socket
        import json
        # CPU usage and temperature
        cpu_percent = psutil.cpu_percent(interval=None)
        cpu_temp = None
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    for entry in entries:
                        if 'cpu' in entry.label.lower() or 'core' in entry.label.lower():
                            cpu_temp = entry.current
                            break
                    if cpu_temp is not None:
                        break
        except Exception:
            cpu_temp = None
        # GPU usage and temperature
        gpus = GPUtil.getGPUs()
        gpu_percent = gpus[0].load * 100 if gpus else None
        gpu_temp = gpus[0].temperature if gpus else None
        gpu_mem = gpus[0].memoryUtil * 100 if gpus and hasattr(gpus[0], 'memoryUtil') else None
        # Patch: If GPU percent is nan, treat as unavailable
        if gpu_percent is not None and (isinstance(gpu_percent, float) and (gpu_percent != gpu_percent or gpu_percent < 0 or gpu_percent > 100)):
            gpu_percent = None
        self.cpu_stat_text = f"CPU: {cpu_percent:.0f}%" + (f" {cpu_temp:.0f}°C" if cpu_temp is not None else "")
        if gpu_percent is not None:
            self.gpu_stat_text = f"GPU: {gpu_percent:.0f}%" + (f" {gpu_temp:.0f}°C" if gpu_temp is not None else "")
        elif gpu_temp is not None or gpu_mem is not None:
            parts = []
            if gpu_temp is not None:
                parts.append(f"{gpu_temp:.0f}°C")
            if gpu_mem is not None:
                parts.append(f"{gpu_mem:.0f}% mem")
            self.gpu_stat_text = "GPU: " + " ".join(parts)
        else:
            self.gpu_stat_text = "GPU: N/A"
        # Send live overlay stats to backend TCP server
        try:
            msg = json.dumps({"cpu": self.cpu_stat_text, "gpu": self.gpu_stat_text}).encode("utf-8")
            print(f"[DEBUG] UI sending overlay update: {msg} (gpu_stat_text={self.gpu_stat_text!r})")
            print(f"[DEBUG] CPU overlay enabled: {self.cpu_overlay_enabled.get()} | GPU overlay enabled: {self.gpu_overlay_enabled.get()}")
            with socket.create_connection(("127.0.0.1", 56789), timeout=0.2) as s:
                s.sendall(msg)
        except Exception as e:
            print(f"[DEBUG] UI failed to send overlay update: {e}")
        # Redraw overlays
        self.update_overlay_canvas()
        # Also force overlay redraw in preview video (if playing)
        if self.preview_playing:
            self.update_overlay_canvas()
        # Schedule next update
        self.root.after(1000, self.update_stats)

    
    def update_overlay_canvas(self):
        # Remove old overlay items (both rectangle and text)
        for item in getattr(self, 'overlay_canvas_items', []):
            self.preview_canvas.delete(item)
        self.overlay_canvas_items = []
        # Draw overlays as rectangles with text (show stats in preview)
        cpu_text = getattr(self, 'cpu_stat_text', 'CPU')
        gpu_text = getattr(self, 'gpu_stat_text', 'GPU')
        if self.cpu_overlay_enabled.get():
            x, y = self.cpu_overlay_pos
            rect = self.preview_canvas.create_rectangle(x, y, x+80, y+18, fill="#222", outline="yellow")
            text = self.preview_canvas.create_text(x+40, y+9, text=cpu_text, fill="yellow", font=("Arial", 10, "bold"))
            self.overlay_canvas_items.extend([rect, text])
        if self.gpu_overlay_enabled.get():
            x, y = self.gpu_overlay_pos
            rect = self.preview_canvas.create_rectangle(x, y, x+80, y+18, fill="#222", outline="cyan")
            text = self.preview_canvas.create_text(x+40, y+9, text=gpu_text, fill="cyan", font=("Arial", 10, "bold"))
            self.overlay_canvas_items.extend([rect, text])
        self.preview_canvas.update_idletasks()

    # Duplicate __init__ removed. Only one __init__ should exist in the class.
    def on_overlay_press(self, event):
        overlays = []
        if self.cpu_overlay_enabled.get():
            overlays.append(('cpu', self.cpu_overlay_pos))
        if self.gpu_overlay_enabled.get():
            overlays.append(('gpu', self.gpu_overlay_pos))
        for name, pos in overlays:
            x, y = pos
            if x <= event.x <= x+60 and y <= event.y <= y+16:
                self.active_overlay = name
                self.overlay_drag_offset = (event.x - x, event.y - y)
                return
        self.active_overlay = None

    def on_overlay_motion(self, event):
        if not self.active_overlay:
            return
        overlay_w, overlay_h = 80, 18
        preview_w, preview_h = 192, 144
        x = max(0, min(event.x - self.overlay_drag_offset[0], preview_w - overlay_w))
        y = max(0, min(event.y - self.overlay_drag_offset[1], preview_h - overlay_h))
        if self.active_overlay == 'cpu':
            self.cpu_overlay_pos = [x, y]
            # Send CPU overlay position live to backend
            try:
                import socket, json
                msg = json.dumps({"cpu_pos": f"{x},{y}"}).encode("utf-8")
                with socket.create_connection(("127.0.0.1", 56789), timeout=0.2) as s:
                    s.sendall(msg)
            except Exception as e:
                print(f"[DEBUG] UI failed to send CPU overlay position: {e}")
        elif self.active_overlay == 'gpu':
            self.gpu_overlay_pos = [x, y]
            # Send GPU overlay position live to backend
            try:
                import socket, json
                msg = json.dumps({"gpu_pos": f"{x},{y}"}).encode("utf-8")
                with socket.create_connection(("127.0.0.1", 56789), timeout=0.2) as s:
                    s.sendall(msg)
            except Exception as e:
                print(f"[DEBUG] UI failed to send GPU overlay position: {e}")
        self.update_overlay_canvas()

    def on_overlay_release(self, event):
        self.active_overlay = None
        self.update_overlay_canvas()


    def on_window_unmap(self, event):
        self.window_visible = False

    def on_window_map(self, event):
        self.window_visible = True
    def __init__(self, root):
        self.cpu_stat_text = 'CPU'
        self.gpu_stat_text = 'GPU'
        self.preview_playing = False
        self.preview_cap = None
        self.root = root
        self.root.title("LCD Video Controller")
        self.video_path = tk.StringVar()
        self.pattern = tk.StringVar(value="None")
        self.rotation = tk.StringVar(value="0")
        self.proc = None
        self.is_playing = False
        self.preview_img = None
        # Create a blank placeholder image for preview
        self.blank_img = ImageTk.PhotoImage(Image.new('RGB', (192, 144), (34, 34, 34)))
        # Overlay state (must be after root exists)
        self.cpu_overlay_enabled = tk.BooleanVar(value=False)
        self.gpu_overlay_enabled = tk.BooleanVar(value=False)
        # Center overlays by default (staggered)
        preview_w, preview_h = 192, 144
        overlay_w, overlay_h = 80, 18
        center_x = (preview_w - overlay_w) // 2
        center_y = (preview_h - overlay_h) // 2
        self.cpu_overlay_pos = [center_x, center_y - 20]  # Centered, slightly above
        self.gpu_overlay_pos = [center_x, center_y + 20]  # Centered, slightly below
        self.active_overlay = None  # 'cpu', 'gpu', or None

        # Video file selection
        tk.Label(root, text="Video File:").grid(row=0, column=0, sticky="e")
        tk.Entry(root, textvariable=self.video_path, width=40).grid(row=0, column=1, padx=5)
        tk.Button(root, text="Browse", command=self.browse_file).grid(row=0, column=2)

        # Preview area
        # Use Canvas for interactive crop selection
        self.preview_canvas = tk.Canvas(root, width=192, height=144, bg="#222", highlightthickness=0)
        self.preview_canvas.grid(row=0, column=3, rowspan=4, padx=10, pady=5)
        self.preview_img_id = self.preview_canvas.create_image(0, 0, anchor="nw", image=self.blank_img)
        self.crop_rect_id = None
        self.drag_start = None
        self.crop_rect = None  # (left, top, right, bottom) in canvas coords
        self.drag_mode = None  # 'new' or 'move'
        self.drag_offset = (0, 0)
        self.preview_canvas.bind("<ButtonPress-1>", self.on_crop_press)
        self.preview_canvas.bind("<B1-Motion>", self.on_crop_motion)
        self.preview_canvas.bind("<ButtonRelease-1>", self.on_crop_release)

        # Bind right mouse button for overlay dragging
        self.preview_canvas.bind("<ButtonPress-3>", self.on_overlay_press)
        self.preview_canvas.bind("<B3-Motion>", self.on_overlay_motion)
        self.preview_canvas.bind("<ButtonRelease-3>", self.on_overlay_release)

        # Test pattern dropdown
        tk.Label(root, text="Test Pattern:").grid(row=1, column=0, sticky="e")
        patterns = ["None", "red", "green", "blue", "white", "black", "bars"]
        pattern_menu = tk.OptionMenu(root, self.pattern, *patterns, command=self.update_preview)
        pattern_menu.grid(row=1, column=1, sticky="w")

        # Rotation dropdown
        tk.Label(root, text="Rotation:").grid(row=2, column=0, sticky="e")
        rotations = ["0", "90", "180", "270"]
        tk.OptionMenu(root, self.rotation, *rotations).grid(row=2, column=1, sticky="w")

        # Crop controls
        tk.Label(root, text="Crop (x,y,w,h):").grid(row=4, column=0, sticky="e")
        self.crop_x = tk.StringVar(value="")
        self.crop_y = tk.StringVar(value="")
        self.crop_w = tk.StringVar(value="")
        self.crop_h = tk.StringVar(value="")
        tk.Entry(root, textvariable=self.crop_x, width=4).grid(row=4, column=1, sticky="w")
        tk.Entry(root, textvariable=self.crop_y, width=4).grid(row=4, column=1, padx=(40,0), sticky="w")
        tk.Entry(root, textvariable=self.crop_w, width=4).grid(row=4, column=1, padx=(80,0), sticky="w")
        tk.Entry(root, textvariable=self.crop_h, width=4).grid(row=4, column=1, padx=(120,0), sticky="w")

        # Play/Stop buttons
        self.play_btn = tk.Button(root, text="Play", command=self.start)
        self.play_btn.grid(row=5, column=0, pady=10)
        self.stop_btn = tk.Button(root, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.grid(row=5, column=1, pady=10)
        tk.Button(root, text="Quit", command=root.quit).grid(row=5, column=2, pady=10)

        # Start periodic stats and overlay updates
        self.update_stats()


        # Overlay controls (must be at the end of __init__)
        overlay_frame = tk.LabelFrame(root, text="Overlays")
        overlay_frame.grid(row=6, column=0, columnspan=3, pady=5, sticky="ew")
        tk.Checkbutton(overlay_frame, text="CPU Overlay", variable=self.cpu_overlay_enabled, command=self.update_preview).grid(row=0, column=0, sticky="w")
        tk.Checkbutton(overlay_frame, text="GPU Overlay", variable=self.gpu_overlay_enabled, command=self.update_preview).grid(row=0, column=1, sticky="w")
        tk.Label(overlay_frame, text="(Drag overlays in preview)").grid(row=0, column=2, sticky="w")

    def browse_file(self):
        path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4;*.avi;*.mov;*.mkv"), ("All Files", "*.*")])
        if path:
            self.video_path.set(path)
            self.pattern.set("None")
            self.update_preview()
            self.start_preview_video()
    def update_preview(self, *_):
        # Test pattern preview
        if self.pattern.get() != "None":
            arr = self.make_test_pattern(320, 240, self.pattern.get())
            img = Image.fromarray(arr, 'RGB')
            self.preview_img = ImageTk.PhotoImage(img.resize((192, 144)))
            self.preview_canvas.itemconfig(self.preview_img_id, image=self.preview_img)
            self.stop_preview_video()
            self.update_overlay_canvas()
            return
        # Video preview
        path = self.video_path.get()
        if path and os.path.exists(path):
            # Only start preview video if no crop or all crop fields are set
            crop_vals = [self.crop_x.get(), self.crop_y.get(), self.crop_w.get(), self.crop_h.get()]
            if all(crop_vals) and all(v.isdigit() for v in crop_vals):
                self.start_preview_video()
            else:
                # Clear crop so backend uses full video
                self.crop_x.set("")
                self.crop_y.set("")
                self.crop_w.set("")
                self.crop_h.set("")
                self.start_preview_video()
            return
        # Always show the blank image if no preview is available
        self.preview_canvas.itemconfig(self.preview_img_id, image=self.blank_img)
        self.stop_preview_video()
        self.update_overlay_canvas()

    def start_preview_video(self):
        if self.preview_playing:
            return
        path = self.video_path.get()
        if not path or not os.path.exists(path):
            return
        self.preview_playing = True
        if self.preview_cap:
            self.preview_cap.release()
        self.preview_cap = cv2.VideoCapture(path)
        self.root.after(0, self.update_preview_video)

    def stop_preview_video(self):
        self.preview_playing = False
        if self.preview_cap:
            self.preview_cap.release()
            self.preview_cap = None

    def update_preview_video(self):
        if not self.preview_playing or not self.preview_cap or not self.preview_cap.isOpened():
            return
        ret, frame = self.preview_cap.read()
        if not ret:
            self.preview_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.preview_cap.read()
            if not ret:
                self.root.after(33, self.update_preview_video)
                return
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # Shrink-to-fit: scale to fit 192x144, preserve aspect ratio, add black bars
        target_w, target_h = 192, 144
        h, w = frame.shape[:2]
        scale = min(target_w / w, target_h / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        preview = np.zeros((target_h, target_w, 3), dtype=np.uint8)
        x_offset = (target_w - new_w) // 2
        y_offset = (target_h - new_h) // 2
        preview[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized

        self.preview_img = ImageTk.PhotoImage(Image.fromarray(preview))
        self.preview_canvas.itemconfig(self.preview_img_id, image=self.preview_img)
        self.update_overlay_canvas()  # <-- ensure overlays are redrawn every frame
        self.root.after(33, self.update_preview_video)

    def on_crop_press(self, event):
        # Check if click is inside existing crop rect
        if self.crop_rect:
            l, t, r, b = self.crop_rect
            if l <= event.x <= r and t <= event.y <= b:
                self.drag_mode = 'move'
                self.drag_offset = (event.x - l, event.y - t)
                return
        # Otherwise, start new crop
        self.drag_mode = 'new'
        self.drag_start = (event.x, event.y)
        if self.crop_rect_id:
            self.preview_canvas.delete(self.crop_rect_id)
            self.crop_rect_id = None
        self.crop_rect = None

    def on_crop_motion(self, event):
        if self.drag_mode == 'move' and self.crop_rect:
            # Move the crop rect, keeping it in bounds
            l, t, r, b = self.crop_rect
            w = r - l
            h = b - t
            new_l = event.x - self.drag_offset[0]
            new_t = event.y - self.drag_offset[1]
            # Clamp to canvas
            new_l = max(0, min(new_l, 192 - w))
            new_t = max(0, min(new_t, 144 - h))
            new_r = new_l + w
            new_b = new_t + h
            # Remove previous rectangle
            if self.crop_rect_id:
                self.preview_canvas.delete(self.crop_rect_id)
            self.crop_rect_id = self.preview_canvas.create_rectangle(new_l, new_t, new_r, new_b, outline="yellow", width=2)
            self.crop_rect = (new_l, new_t, new_r, new_b)
        elif self.drag_mode == 'new' and self.drag_start:
            x0, y0 = self.drag_start
            dx = event.x - x0
            dy = event.y - y0
            # Always keep 4:3 aspect ratio (width:height = 4:3)
            if abs(dx) > abs(dy):
                width = dx
                height = int(abs(width) * 3 / 4) * (1 if dy >= 0 else -1)
            else:
                height = dy
                width = int(abs(height) * 4 / 3) * (1 if dx >= 0 else -1)
            x1 = x0 + width
            y1 = y0 + height
            # Clamp to canvas bounds
            x1 = max(0, min(x1, 191))
            y1 = max(0, min(y1, 143))
            # Remove previous rectangle
            if self.crop_rect_id:
                self.preview_canvas.delete(self.crop_rect_id)
            self.crop_rect_id = self.preview_canvas.create_rectangle(x0, y0, x1, y1, outline="yellow", width=2)
            # Store rect for use on release
            self.crop_rect = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    def on_crop_release(self, event):
        # On release, update crop fields from self.crop_rect
        if not self.crop_rect:
            self.drag_mode = None
            self.drag_start = None
            return
        l, t, r, b = self.crop_rect
        w = r - l
        h = b - t
        # Store preview canvas coordinates directly
        crop_x = int(l)
        crop_y = int(t)
        crop_w = int(w)
        crop_h = int(h)
        self.crop_x.set(str(crop_x))
        self.crop_y.set(str(crop_y))
        self.crop_w.set(str(crop_w))
        self.crop_h.set(str(crop_h))
        self.drag_mode = None
        self.drag_start = None

    def make_test_pattern(self, width, height, color):
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        if color == 'red':
            arr[..., 0] = 255
        elif color == 'green':
            arr[..., 1] = 255
        elif color == 'blue':
            arr[..., 2] = 255
        elif color == 'white':
            arr[...] = 255
        elif color == 'black':
            arr[...] = 0
        elif color == 'bars':
            bar_w = width // 8
            colors = [
                (255,0,0), (0,255,0), (0,0,255), (255,255,255),
                (0,0,0), (0,255,255), (255,0,255), (255,255,0)
            ]
            for i, c in enumerate(colors):
                arr[:, i*bar_w:(i+1)*bar_w, :] = c
            arr[:, 8*bar_w:, :] = (128,128,128)
        else:
            arr[..., 0] = 255
        return arr

    def start(self):
        if self.proc is not None:
            messagebox.showinfo("Info", "Video is already playing.")
            return
        if self.pattern.get() != "None":
            cmd = [sys.executable, VIDEO_SCRIPT, f"--test-pattern={self.pattern.get()}"]
        else:
            if not self.video_path.get():
                messagebox.showerror("Error", "Please select a video file or test pattern.")
                return
            cmd = [sys.executable, VIDEO_SCRIPT, "--input", self.video_path.get()]
        # Add rotation argument if not 0
        if self.rotation.get() != "0":
            cmd += ["--rotate", self.rotation.get()]
        # Add crop argument only if all crop values are set
        crop_vals = [self.crop_x.get(), self.crop_y.get(), self.crop_w.get(), self.crop_h.get()]
        if all(crop_vals) and all(v.isdigit() for v in crop_vals):
            preview_w, preview_h = 192, 144
            crop_x, crop_y, crop_w, crop_h = map(int, crop_vals)
            # Get input video size using OpenCV
            input_w, input_h = None, None
            if self.video_path.get() and os.path.exists(self.video_path.get()):
                cap = cv2.VideoCapture(self.video_path.get())
                if cap.isOpened():
                    input_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    input_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
            if input_w and input_h:
                # Calculate how the video is letterboxed/pillarboxed in the preview
                scale = min(preview_w / input_w, preview_h / input_h)
                disp_w = int(input_w * scale)
                disp_h = int(input_h * scale)
                x_offset = (preview_w - disp_w) // 2
                y_offset = (preview_h - disp_h) // 2
                # Clamp crop rect to video area
                crop_left = max(crop_x, x_offset)
                crop_top = max(crop_y, y_offset)
                crop_right = min(crop_x + crop_w, x_offset + disp_w)
                crop_bottom = min(crop_y + crop_h, y_offset + disp_h)
                # Map crop rect from preview video area to input video frame
                rel_x = (crop_left - x_offset) / disp_w
                rel_y = (crop_top - y_offset) / disp_h
                rel_w = (crop_right - crop_left) / disp_w
                rel_h = (crop_bottom - crop_top) / disp_h
                v_crop_x = int(rel_x * input_w)
                v_crop_y = int(rel_y * input_h)
                v_crop_w = int(rel_w * input_w)
                v_crop_h = int(rel_h * input_h)
                # Always send colon-separated format for backend conversion
                crop_str = f"{v_crop_w}:{v_crop_h}:{v_crop_x}:{v_crop_y}"
                cmd += ["--crop", crop_str]

        # Add overlay arguments
        if self.cpu_overlay_enabled.get():
            x, y = self.cpu_overlay_pos
            cmd += ["--cpu-overlay", f"{x},{y}"]
        if self.gpu_overlay_enabled.get():
            x, y = self.gpu_overlay_pos
            cmd += ["--gpu-overlay", f"{x},{y}"]

        # Debug: print overlay args being sent
        print(f"[DEBUG] Launching backend with cmd: {' '.join(map(str, cmd))}")

        # Start the process
        try:
            self.proc = subprocess.Popen(cmd)
            self.is_playing = True
            self.play_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
        except Exception as e:
            self.proc = None
            messagebox.showerror("Error", f"Failed to start video: {e}")

        # Only schedule overlay updates for the preview, not for the backend process
        self.root.after(1000, self.update_lcd_overlays)

    def stop(self):
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to stop video: {e}")
            self.proc = None
        self.is_playing = False
        self.play_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def update_lcd_overlays(self):
        # Only update overlays if process is running
        # Instead of restarting the process, just update the preview overlays
        self.update_overlay_canvas()
        self.root.after(1000, self.update_lcd_overlays)

if __name__ == "__main__":
    root = tk.Tk()
    app = LCDVideoUI(root)
    root.mainloop()
