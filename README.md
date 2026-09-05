# iPhone Camera

A small native macOS window for Apple's Continuity Camera. There is no server
and nothing to open on the iPhone.

```bash
python3 main.py
```

`bash run.sh` still works when you only want the unannotated native camera
preview. Normally you do not need to run it separately because `main.py`
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
│   ├── providers/     # facial-search adapter; Clearview stays behind an API
│   ├── records/       # synthetic DMV/law-enforcement records adapter
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
├── camera_feed.py     # compatibility shim for app/capture/camera_feed.py
├── face_detection.py  # compatibility shim for app/detection/face_detection.py
├── main.py            # compatibility entry point for app/ui/demo.py
├── run.sh             # compatibility entry point for scripts/run.sh
└── scripts/run.sh     # native camera build and launch script
```

### Runtime flow

```text
iPhone Camera
    -> capture.FrameSource
    -> detection.SubjectTracker (anonymous until explicitly triggered)
    -> workflow.IdentificationSession
    -> providers.FaceSearchProvider
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
