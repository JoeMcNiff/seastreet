# iPhone Camera

A small native macOS window for Apple's Continuity Camera. There is no server
and nothing to open on the iPhone.

```bash
zsh run.sh
```

Allow camera access when macOS asks. The Mac and iPhone must use the same Apple
Account, with Wi-Fi, Bluetooth, and Continuity Camera enabled. Keep the iPhone
nearby and locked.

In a second terminal, confirm Python is receiving the feed:

```bash
python3 main.py
```

## Use frames in Python

The viewer publishes frames only on `127.0.0.1:8765`. Read JPEG bytes without
dependencies:

```python
from camera_feed import jpeg_frames

for jpeg in jpeg_frames():
    print(len(jpeg))
```

Or receive decoded OpenCV arrays:

```python
from camera_feed import opencv_frames

for frame in opencv_frames():
    # frame is a NumPy BGR image
    process(frame)
```
