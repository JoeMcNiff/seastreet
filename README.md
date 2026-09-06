# iPhone Camera

An iPhone camera streams over WebRTC to the Python application on the Mac.
The Mac displays and processes the video with OpenCV; Continuity Camera is not
used.

## Demo setup

Create the virtual environment once:

```bash
cd /Users/josephmcniff/dnhacks/seastreet
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

After that, run the demo with:

```bash
python -m app.ui.demo
```

The terminal prints the iPhone camera URL. Keep the Mac and iPhone on the same
Wi-Fi network, open that URL in Safari, and tap **Start Camera**. Keep Safari
open and the iPhone unlocked while streaming. Press `Q` or Escape to close the
laptop window. Allow incoming network connections if macOS asks. The iPhone
plays a short two-tone alert whenever a new candidate match is found.

### First-time iPhone certificate setup

Safari requires HTTPS before it will allow a webpage to use the camera. The
demo generates its own local certificate and prints a separate certificate URL.
On the iPhone, open that HTTP URL and then:

1. Allow the configuration profile to download.
2. Open **Settings → General → VPN & Device Management** and install it.
3. Open **Settings → General → About → Certificate Trust Settings** and enable
   full trust for **SeaStreet Camera Local CA**.
4. Return to Safari and open the HTTPS camera URL printed by the demo.

This setup is required once. The generated certificate and private keys stay
in the ignored `.camera-feed/` directory on the Mac.

Each detected face gets its own box and is searched independently; multiple
people can be searched concurrently. Candidate names and scores
remain attached to their tracked faces through brief movement or occlusion.
Detection uses OpenCV YuNet and does not require visible eye landmarks.
Without API credentials the service
returns `pending_provider` and makes no network request.

## Clearview and Supabase

Apply `supabase/migrations/001_face_embeddings.sql` to the existing Supabase
schema, then fill in `.env`. Python loads it automatically:

```bash
python -m scripts.check_connections
```

The live workflow sends one frame and its OpenCV face rectangle to Clearview
`/mlapi/v1/embed`. It sends the returned vector to the Supabase
`match_identity_embeddings` RPC and
returns the strongest image match per identity. It does not use Clearview
`/detect`, and it does not retrieve criminal records without a later human
review step.

To import images already in the Supabase bucket, organize them by identity:

```text
identity-images/
├── jane-doe/
│   ├── front.jpg
│   └── alternate.png
└── john-smith/
    └── front.jpg
```

The top-level folder becomes the identity's `external_ref`; its readable form
is used as the initial display name. Apply the latest migration, then run:

```bash
python -m scripts.import_bucket_faces
```

The importer downloads each JPEG/PNG, calls Clearview
`/mlapi/v1/detect_and_embed`, and creates or reuses the identity, image, link,
and embedding rows. It accepts exactly one face per image and skips unchanged
images on later runs. Use `--force` to regenerate existing embeddings.

## Use frames in Python

The WebRTC receiver exposes only the latest decoded OpenCV frame so latency
cannot accumulate:

```python
from app.capture.camera_feed import WebRTCCamera
import time

camera = WebRTCCamera()
camera.start()
try:
    while not camera.frames:
        time.sleep(0.05)
    frame = camera.frames.pop()  # NumPy BGR image
finally:
    camera.stop()
```

Detect and crop every usable face independently:

```python
from app.detection.face_detection import detect_faces

clips = [face.crop(frame) for face in detect_faces(frame) if face.ready]
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design notes.
