# iPhone Camera

An iPhone camera streams to the Python application on the Mac. WebRTC is the
default, with Apple Continuity Camera available as a fallback. Both sources use
the same OpenCV detection, recognition, records, audit, and UI pipeline.

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

### Robin Cam native iPhone app

Robin Cam uses the rear iPhone camera at 1080p/30 fps and sends the
same WebRTC feed to the existing Python receiver. It also receives the existing
criminal-record alerts, including sound and haptics. Criminal-record matches
display the recognition face crop and record summary in a dismissible
document-style sheet. The Safari page remains available as a zero-install fallback.

First, start the laptop receiver as usual:

```bash
python -m app.ui.demo
```

Then open `ios/SeaStreetCamera/SeaStreetCamera.xcodeproj` in Xcode. In the
**SeaStreetCamera** target's **Signing & Capabilities** tab, select your Apple
development team. Connect and trust the iPhone, select it as the run destination,
and press Run. If iOS asks, enable Developer Mode under
**Settings → Privacy & Security → Developer Mode** and run again.

On the iPhone, enter the hostname from the camera URL printed by Python (for
example, `Josephs-MacBook-Air-481.local`) and tap **Start Camera**. Both devices
must be on the same local network. The app uses the same local HTTPS certificate
as the Safari camera, so complete the certificate steps below first if that CA is
not already trusted on the iPhone. Keep the app in the foreground while streaming.

Xcode resolves the app's pinned WebRTC package automatically. A free Personal
Team is enough for installing a development build on your own iPhone; Xcode may
ask you to change the bundle identifier if `com.seastreet.camera` is unavailable.

The terminal prints the iPhone camera URL. Keep the Mac and iPhone on the same
Wi-Fi network, open that URL in Safari, and tap **Start Camera**. Keep Safari
open and the iPhone unlocked while streaming. Press `Q` or Escape to close the
laptop window. Allow incoming network connections if macOS asks. The iPhone
plays an alert only when a matched person has a synthetic criminal record.

To use Apple Continuity Camera instead of the phone webpage:

```bash
python -m app.ui.demo --camera continuity
```

Keep the iPhone nearby with Wi-Fi and Bluetooth enabled and signed in to the
same Apple Account as the Mac. The first run compiles and opens a small native
camera helper; grant it camera permission if macOS asks. The analyzed feed still
appears in the main Python window. Phone alert sounds require the WebRTC page and
are unavailable in Continuity mode.

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
Detection uses OpenCV YuNet at up to 960 pixels on the frame's long side,
smooths tracked boxes, and does not require visible eye landmarks. Before each
recognition request, the live workflow sends one padded face crop. Detection
runs on a latest-frame worker, so it cannot stall the video or build a backlog.
Without API credentials the service
returns `pending_provider` and makes no network request.

The right-side panel shows the selected matched identity, its associated
synthetic criminal records, and the live event timeline. Record lookup starts
automatically after an identity match. Press `Tab` to cycle through multiple
matched people. Events are appended to `data/audit/events.jsonl`; optional
operator, unit, encounter, predicate, and log-path values can be set using the
variables in `.env.example`.

## Clearview and Supabase

Apply the SQL files in `supabase/migrations/` in numeric order to the existing
Supabase schema, then fill in `.env`. Migration `002` adds the criminal-record
fields used by the side panel. Python loads `.env` automatically:

```bash
python -m scripts.check_connections
```

The live workflow sends a padded face crop and its crop-relative OpenCV
rectangle to Clearview `/mlapi/v1/embed`. It sends the returned vector to the Supabase
`match_identity_embeddings` RPC and
returns the strongest image match per identity. It then queries synthetic
criminal records using the matched `identity_id`. It does not use Clearview
`/detect`.

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
