# iPhone Camera

A small native macOS window for Apple's Continuity Camera. There is no server
and nothing to open on the iPhone.

```bash
python3 -m app.ui.demo
```

Use `bash scripts/run.sh` when you only want the unannotated native camera
preview. Normally you do not need to run it separately because the demo
launches a fresh copy automatically.

Allow camera access when macOS asks. The Mac and iPhone must use the same Apple
Account, with Wi-Fi, Bluetooth, and Continuity Camera enabled. Keep the iPhone
nearby and locked. Press `Q` or Escape to close the detection window.

The indicator turns green only after one frontal face—with both eyes visible—is
stable for several frames. This reduces false triggers before a future photo
burst.

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
│   └── ui/            # live feed, review, records, logs, and notifications
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
