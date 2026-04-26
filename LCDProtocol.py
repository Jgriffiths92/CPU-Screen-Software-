
# Ensure local DLLs (e.g., libusb-1.0.dll) are loaded from Dependensies folder
import os
import sys
dll_dir = os.path.join(os.path.dirname(__file__), 'Dependensies')
os.environ['PATH'] = dll_dir + os.pathsep + os.environ['PATH']

# LCDProtocol.py
import usb.core
import usb.util
import platform

VENDOR_ID = 0x0416
PRODUCT_ID = 0x5302
EP_OUT = 0x02
EP_IN = 0x81

class LCDDevice:
    def __init__(self):
        self.dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
        if self.dev is None:
            raise ValueError("Device not found")
        if platform.system() != "Windows":
            if self.dev.is_kernel_driver_active(0):
                self.dev.detach_kernel_driver(0)
        self.dev.set_configuration()
        self.handshake()

    def handshake(self):
        handshake = bytearray(512)
        handshake[0:4] = b'\xDA\xDB\xDC\xDD'
        handshake[12] = 0x01
        # All other bytes are zero by default
        print(f"[DEBUG] Full handshake buffer (512 bytes): {handshake.hex()}")
        print(f"[DEBUG] Sending handshake: {handshake[:20].hex()}")
        self.dev.write(EP_OUT, handshake, timeout=1000)
        try:
            response = self.dev.read(EP_IN, 512, timeout=1000)
            print(f"[DEBUG] Full handshake response (512 bytes): {bytes(response).hex()}")
            print(f"[DEBUG] Received response: {bytes(response[:20]).hex()}")
        except Exception as e:
            print(f"[ERROR] Exception during handshake read: {e}")
            raise RuntimeError("Handshake failed (read error)")
        if bytes(response[0:4]) != b'\xDA\xDB\xDC\xDD':
            print(f"[ERROR] Handshake header mismatch: {bytes(response[0:4]).hex()} != dadbdcdd")
            raise RuntimeError("Handshake failed (header mismatch)")
        if response[12] != 0x01:
            print(f"[ERROR] Handshake byte 12 mismatch: {response[12]:02x} != 01")
            raise RuntimeError("Handshake failed (byte 12 mismatch)")
        if response[16] != 0x10:
            print(f"[ERROR] Handshake byte 16 mismatch: {response[16]:02x} != 10")
            raise RuntimeError("Handshake failed (byte 16 mismatch)")
        print("Handshake OK")

    def send_frame(self, frame_data, width=320, height=240):
        # Prepend 20-byte header as in Linux port
        header = bytearray(20)
        header[0:4] = b'\xDA\xDB\xDC\xDD'  # magic
        header[4:6] = b'\x02\x00'           # command type = PICTURE
        header[6:8] = b'\x01\x00'           # RGB565 mode
        header[8:10] = (width).to_bytes(2, 'little')
        header[10:12] = (height).to_bytes(2, 'little')
        header[12:16] = b'\x02\x00\x00\x00'  # sub-flag
        header[16:20] = len(frame_data).to_bytes(4, 'little')
        packet = header + frame_data
        print(f"[DEBUG] send_frame: header={header.hex()} len(pixel_data)={len(frame_data)} total_len={len(packet)}")
        # Send in 512-byte HID interrupt packets (test for vertical line artifact)
        chunk_size = 512
        total_len = len(packet)
        offset = 0
        while offset < total_len:
            chunk = packet[offset:offset+chunk_size]
            # Pad last chunk if needed
            if len(chunk) < chunk_size:
                chunk += b'\x00' * (chunk_size - len(chunk))
            self.dev.write(EP_OUT, chunk, timeout=2000)
            offset += chunk_size
        print(f"[DEBUG] Frame sent in {((total_len-1)//chunk_size)+1} chunks of {chunk_size} bytes.")