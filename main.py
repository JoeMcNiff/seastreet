"""Example: receive iPhone frames in Python."""

from camera_feed import opencv_frames

print("Waiting for the iPhone Camera app on port 8765…")
try:
    for frame in opencv_frames():
        print(f"\rReceiving {frame.shape[1]} × {frame.shape[0]} frames", end="", flush=True)
except KeyboardInterrupt:
    print("\nStopped")
