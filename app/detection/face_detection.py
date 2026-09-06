"""Fast multi-angle face detection and tracking."""

from dataclasses import dataclass
from math import hypot
from pathlib import Path

import cv2

MODEL = Path(__file__).parent / "models/face_detection_yunet_2023mar.onnx"
DETECTOR = cv2.FaceDetectorYN.create(str(MODEL), "", (480, 320), 0.6, 0.3, 500)


@dataclass(frozen=True)
class DetectedFace:
    rect: tuple
    ready: bool
    reason: str

    def crop(self, frame, padding=0.15):
        """Return an independent, padded copy of this face."""
        x, y, width, height = self.rect
        x_pad, y_pad = round(width * padding), round(height * padding)
        left, top = max(0, x - x_pad), max(0, y - y_pad)
        right = min(frame.shape[1], x + width + x_pad)
        bottom = min(frame.shape[0], y + height + y_pad)
        return frame[top:bottom, left:right].copy()


class FaceTracker:
    """Keep IDs stable through camera movement and brief occlusion."""

    def __init__(self, min_similarity=0.35, max_missed=45):
        self.min_similarity = min_similarity
        self.max_missed = max_missed
        self._next_id = 1
        self._tracks = {}

    @property
    def active_ids(self):
        return self._tracks.keys()

    def clear(self):
        self._tracks.clear()

    def update(self, faces):
        existing = set(self._tracks)
        candidates = sorted(
            (
                (
                    max(
                        _similarity(rect, face.rect),
                        _similarity(_move(rect, velocity, missed + 1), face.rect),
                    ),
                    track_id,
                    index,
                )
                for track_id, (rect, missed, velocity) in self._tracks.items()
                for index, face in enumerate(faces)
            ),
            reverse=True,
        )
        assignments = {}
        matched = set()
        for similarity, track_id, index in candidates:
            if similarity < self.min_similarity:
                break
            if track_id not in matched and index not in assignments:
                assignments[index] = track_id
                matched.add(track_id)
                old_rect, _missed, old_velocity = self._tracks[track_id]
                velocity = _velocity(old_rect, faces[index].rect, old_velocity)
                self._tracks[track_id] = (faces[index].rect, 0, velocity)

        for track_id in existing - matched:
            rect, missed, velocity = self._tracks[track_id]
            if missed >= self.max_missed:
                del self._tracks[track_id]
            else:
                self._tracks[track_id] = (rect, missed + 1, velocity)

        for index, face in enumerate(faces):
            if index not in assignments:
                assignments[index] = self._next_id
                self._tracks[self._next_id] = (face.rect, 0, (0, 0))
                self._next_id += 1

        return tuple((assignments[index], face) for index, face in enumerate(faces))


def _overlap(first, second):
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    width = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    height = max(0, min(ay + ah, by + bh) - max(ay, by))
    intersection = width * height
    return intersection / (aw * ah + bw * bh - intersection)


def _similarity(first, second):
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    distance = hypot(ax + aw / 2 - bx - bw / 2, ay + ah / 2 - by - bh / 2)
    proximity = max(0, 1 - distance / (2 * max(aw, ah, bw, bh)))
    size = min(aw * ah, bw * bh) / max(aw * ah, bw * bh)
    return max(_overlap(first, second), 0.7 * proximity + 0.3 * size)


def _move(rect, velocity, frames):
    x, y, width, height = rect
    return x + velocity[0] * frames, y + velocity[1] * frames, width, height


def _velocity(old_rect, new_rect, old_velocity):
    old_x, old_y, old_width, old_height = old_rect
    new_x, new_y, new_width, new_height = new_rect
    dx = new_x + new_width / 2 - old_x - old_width / 2
    dy = new_y + new_height / 2 - old_y - old_height / 2
    return (old_velocity[0] + dx) / 2, (old_velocity[1] + dy) / 2


def detect_faces(frame):
    """Detect faces without requiring frontal eye landmarks."""
    scale = min(1.0, 480 / frame.shape[1])
    image = cv2.resize(frame, None, fx=scale, fy=scale) if scale < 1 else frame
    height, width = image.shape[:2]
    DETECTOR.setInputSize((width, height))
    _count, faces = DETECTOR.detect(image)
    if faces is None:
        return ()

    results = []
    frame_height, frame_width = frame.shape[:2]
    for x, y, face_width, face_height in faces[:, :4]:
        left = max(0, round(x / scale))
        top = max(0, round(y / scale))
        right = min(frame_width, round((x + face_width) / scale))
        bottom = min(frame_height, round((y + face_height) / scale))
        if right <= left or bottom <= top:
            continue
        results.append(
            DetectedFace((left, top, right - left, bottom - top), True, "SEARCHING...")
        )

    return tuple(results)
