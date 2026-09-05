"""Fast multi-face detection using OpenCV's bundled classifiers."""

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import cv2

DATA = Path(cv2.data.haarcascades)
FACE = cv2.CascadeClassifier(str(DATA / "haarcascade_frontalface_default.xml"))
EYES = cv2.CascadeClassifier(str(DATA / "haarcascade_eye_tree_eyeglasses.xml"))


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
    """Keep lightweight IDs on faces across nearby frames."""

    def __init__(self, min_overlap=0.15, max_missed=15):
        self.min_overlap = min_overlap
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
                (_overlap(rect, face.rect), track_id, index)
                for track_id, (rect, _missed) in self._tracks.items()
                for index, face in enumerate(faces)
            ),
            reverse=True,
        )
        assignments = {}
        matched = set()
        for overlap, track_id, index in candidates:
            if overlap < self.min_overlap:
                break
            if track_id not in matched and index not in assignments:
                assignments[index] = track_id
                matched.add(track_id)
                self._tracks[track_id] = (faces[index].rect, 0)

        for track_id in existing - matched:
            rect, missed = self._tracks[track_id]
            if missed >= self.max_missed:
                del self._tracks[track_id]
            else:
                self._tracks[track_id] = (rect, missed + 1)

        for index, face in enumerate(faces):
            if index not in assignments:
                assignments[index] = self._next_id
                self._tracks[self._next_id] = (face.rect, 0)
                self._next_id += 1

        return tuple((assignments[index], face) for index, face in enumerate(faces))


def _overlap(first, second):
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    width = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    height = max(0, min(ay + ah, by + bh) - max(ay, by))
    intersection = width * height
    return intersection / (aw * ah + bw * bh - intersection)


def detect_faces(frame):
    """Detect and independently assess every frontal face in a frame."""
    scale = min(1.0, 640 / frame.shape[1])
    image = cv2.resize(frame, None, fx=scale, fy=scale) if scale < 1 else frame
    gray = cv2.equalizeHist(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
    height, width = gray.shape
    minimum = max(36, min(width, height) // 14)
    faces = FACE.detectMultiScale(gray, 1.1, 3, minSize=(minimum, minimum))

    results = []
    for x, y, face_width, face_height in faces:
        rect = tuple(round(value / scale) for value in (x, y, face_width, face_height))
        margin = min(width, height) * 0.005
        if (
            x < margin
            or y < margin
            or x + face_width > width - margin
            or y + face_height > height - margin
        ):
            results.append(DetectedFace(rect, False, "FACE DETECTED"))
            continue
        if face_height < height * 0.11:
            results.append(DetectedFace(rect, False, "FACE DETECTED"))
            continue

        upper_face = gray[y : y + round(face_height * 0.75), x : x + face_width]
        eyes = EYES.detectMultiScale(
            upper_face,
            1.1,
            3,
            minSize=(max(8, face_width // 14), max(6, face_height // 16)),
        )
        centers = sorted((ex + ew / 2, ey + eh / 2) for ex, ey, ew, eh in eyes)
        ready = any(
            face_width * 0.15 < right[0] - left[0] < face_width * 0.82
            and abs(right[1] - left[1]) < face_height * 0.28
            and abs((right[0] + left[0]) / 2 - face_width / 2) < face_width * 0.30
            for left, right in combinations(centers, 2)
        )
        reason = "FULL FACE READY" if ready else "FACE DETECTED"
        results.append(DetectedFace(rect, ready, reason))

    return tuple(results)
