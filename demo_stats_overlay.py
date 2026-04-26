import cv2
import numpy as np
import psutil
import time

# Generate a solid color image (simulating a video frame)
frame = np.full((240, 320, 3), (40, 60, 90), dtype=np.uint8)  # BGR

# Example stats (fake values for demo)
cpu = 42.5
gpu = 37.1  # Replace with real value if GPUtil is available
ram = 58.3
fps = 59.9

# Overlay text (OpenCV)
def overlay_stats(img, cpu, gpu, ram, fps):
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.6
    color = (255, 255, 255)
    thickness = 2
    y = 30
    cv2.putText(img, f"CPU: {cpu:.1f}%", (10, y), font, font_scale, color, thickness, cv2.LINE_AA)
    y += 30
    cv2.putText(img, f"GPU: {gpu:.1f}%", (10, y), font, font_scale, color, thickness, cv2.LINE_AA)
    y += 30
    cv2.putText(img, f"RAM: {ram:.1f}%", (10, y), font, font_scale, color, thickness, cv2.LINE_AA)
    y += 30
    cv2.putText(img, f"FPS: {fps:.1f}", (10, y), font, font_scale, color, thickness, cv2.LINE_AA)
    return img

# Apply overlay
output = overlay_stats(frame.copy(), cpu, gpu, ram, fps)

# Save to file
cv2.imwrite("demo_stats_overlay.png", output)
print("Demo image saved as demo_stats_overlay.png")
