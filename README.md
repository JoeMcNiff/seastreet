# iPhone Camera

A native macOS Continuity Camera helper with a local-only Python frame bridge.
Nothing needs to be opened on the iPhone.

## Demo setup

Create the virtual environment once:

```bash
cd /Users/josephmcniff/dnhacks/seastreet
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

After that, run the demo with:

```bash
.venv/bin/python -m app.ui.demo
```

Use `bash scripts/run.sh` when you only want the unannotated native camera
preview. Normally you do not need to run it separately because the demo
launches a fresh copy automatically.

Allow camera access when macOS asks. The Mac and iPhone must use the same Apple
Account, with Wi-Fi, Bluetooth, and Continuity Camera enabled. Keep the iPhone
nearby and locked. Press `Q` or Escape to close the detection window.

The indicator turns green only after one frontal face—with both eyes visible—is
stable for five frames. Those five detected frames are copied into a burst and
passed to the facial-recognition service. Without API credentials the service
returns `pending_provider` and makes no network request.

## Clearview and Supabase

Apply `supabase/migrations/001_face_embeddings.sql` to the existing Supabase
schema, then fill in `.env`. Python loads it automatically:

```bash
.venv/bin/python -m scripts.check_connections
```

The live workflow sends each of the five original burst frames and its OpenCV
face rectangle to Clearview `/mlapi/v1/embed`. It averages and normalizes the
five returned vectors, calls the Supabase `match_identity_embeddings` RPC, and
returns the strongest image match per identity. It does not use Clearview
`/detect`, and it does not retrieve criminal records without a later human
review step.

To enroll fabricated reference images, copy
`data/mock_records/manifest.example.json`, add the referenced JPEG/PNG files,
and run:

```bash
.venv/bin/python -m scripts.enroll_mock_faces data/mock_records/manifest.json
```

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

## Architecture

The prototype is organized as a thin vertical slice. The existing camera
spike remains runnable while the demo workflow is built behind explicit
boundaries.

```text
seastreet/
├── app/
│   ├── capture/       # iPhone/Continuity Camera and rolling frame buffer
│   ├── detection/     # anonymous person/face detection and subject tracks
│   ├── workflow/      # officer-triggered search state machine and predicates
│   ├── providers/     # Clearview embedding adapter and mock provider
│   ├── records/       # Supabase vector search and synthetic records adapters
│   ├── audit/         # append-only evidence events and exportable log
│   └── ui/            # live feed, review, records, and logs
├── data/
│   ├── mock_records/  # synthetic identities and records only
│   └── events/        # local demo event output; ignored by git
├── docs/
│   └── ARCHITECTURE.md
├── tests/
│   ├── unit/
│   └── integration/
└── scripts/run.sh     # native camera build and launch script
```

### Runtime flow

```text
iPhone Camera
    -> capture.FrameSource
    -> detection.SubjectTracker (anonymous until explicitly triggered)
    -> workflow.IdentificationSession
    -> providers.ClearviewEmbeddingProvider
    -> records.SupabaseVectorStore
    -> workflow.HumanReview
    -> records.RecordsProvider
    -> ui.DemoConsole
    -> audit.EventLog
```

The workflow must record the search reason before a provider call. A provider
result is never sufficient to query records: a human review decision is an
explicit prerequisite. The demo provider should be selectable through
configuration so the default path uses deterministic mock results and a real
Clearview integration is opt-in.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for responsibilities,
event fields, and the decisions still needed before implementation.
