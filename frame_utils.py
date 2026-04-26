import numpy as np

def rgb24_to_rgb565(arr):
    """
    Convert a numpy array of shape (H, W, 3) in BGR or RGB order (uint8)
    to a bytes object in RGB565 format (little endian).
    """
    # Convert to uint16: (R >> 3) << 11 | (G >> 2) << 5 | (B >> 3)
    r = (arr[..., 0] >> 3).astype(np.uint16)
    g = (arr[..., 1] >> 2).astype(np.uint16)
    b = (arr[..., 2] >> 3).astype(np.uint16)
    rgb565 = (r << 11) | (g << 5) | b
    # Convert to bytes (little endian)
    return rgb565.flatten().astype('<u2').tobytes()

def make_test_pattern(height, width, color):
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
