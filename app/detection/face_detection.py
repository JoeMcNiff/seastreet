"""Simple full-frontal-face check using OpenCV's bundled classifiers."""

from pathlib import Path

import cv2


DATA = Path(cv2.data.haarcascades)
FACE = cv2.CascadeClassifier(str(DATA / "haarcascade_frontalface_default.xml"))
EYES = cv2.CascadeClassifier(str(DATA / "haarcascade_eye_tree_eyeglasses.xml"))


def full_face(frame):
    """Return (is_ready, face_boxes, reason) for one unobstructed frontal face."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    height, width = gray.shape
    minimum = max(70, min(width, height) // 7)
    faces = FACE.detectMultiScale(gray, 1.1, 6, minSize=(minimum, minimum))
    boxes = [tuple(map(int, face)) for face in faces]

    if not boxes:
        return False, boxes, "NO FACE"
    if len(boxes) > 1:
        return False, boxes, "ONE PERSON ONLY"

    x, y, w, h = boxes[0]
    margin = min(width, height) * 0.025
    if x < margin or y < margin or x + w > width - margin or y + h > height - margin:
        return False, boxes, "SHOW YOUR FULL FACE"
    if h < height * 0.20:
        return False, boxes, "MOVE CLOSER"

    # A level, well-spaced eye pair is a useful lightweight proxy for a face
    # that is looking forward rather than turned away or heavily obstructed.
    upper_face = gray[y : y + int(h * 0.62), x : x + w]
    eyes = EYES.detectMultiScale(
        upper_face,
        1.1,
        6,
        minSize=(max(12, w // 10), max(8, h // 12)),
    )
    centers = sorted((ex + ew / 2, ey + eh / 2) for ex, ey, ew, eh in eyes)
    for left_index, left in enumerate(centers):
        for right in centers[left_index + 1 :]:
            separation = right[0] - left[0]
            level = abs(right[1] - left[1])
            midpoint = (right[0] + left[0]) / 2
            if w * 0.25 < separation < w * 0.70 and level < h * 0.16 and abs(midpoint - w / 2) < w * 0.16:
                return True, boxes, "FULL FACE READY"

    return False, boxes, "LOOK FORWARD - SHOW BOTH EYES"
