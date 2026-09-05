# iPhone Camera

A native macOS Continuity Camera helper with a local-only Python frame bridge.
Nothing needs to be opened on the iPhone.

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

Use `bash scripts/run.sh` when you only want the unannotated native camera
preview. Normally you do not need to run it separately because the demo
launches a fresh copy automatically.

Allow camera access when macOS asks. The Mac and iPhone must use the same Apple
Account, with Wi-Fi, Bluetooth, and Continuity Camera enabled. Keep the iPhone
nearby and locked. Press `Q` or Escape to close the detection window.

The indicator turns green only after one frontal face—with both eyes visible—is
stable for five frames. Those frames form a burst passed to the facial-recognition
service. Without API credentials the service
returns `pending_provider` and makes no network request.

## Clearview and Supabase

Apply `supabase/migrations/001_face_embeddings.sql` to the existing Supabase
schema, then fill in `.env`. Python loads it automatically:

```bash
python -m scripts.check_connections
```

The live workflow sends each of the five original burst frames and its OpenCV
face rectangle to Clearview `/mlapi/v1/embed`. It averages and normalizes the
five returned vectors, calls the Supabase `match_identity_embeddings` RPC, and
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

The viewer publishes frames only on `127.0.0.1:8765`. Read JPEG bytes without
dependencies:

```python
from app.capture.camera_feed import jpeg_frames

for jpeg in jpeg_frames():
    print(len(jpeg))
```

Or receive decoded OpenCV arrays:

```python
from app.capture.camera_feed import opencv_frames

for frame in opencv_frames():
    # frame is a NumPy BGR image
    process(frame)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design notes.
