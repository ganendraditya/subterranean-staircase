"""Subtitle history tracking and temporal stabilization with Jaccard fuzzy matching.

Stabilizes OCR noise across successive video frames, preventing visual flickering
and deduplicating identical subtitle lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import time
from typing import Dict, List, Optional

from core.contracts import SubtitleBox, SubtitleDetection

_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]|\w+")


def text_similarity(a: str, b: str) -> float:
    """Calculate token-level Jaccard similarity between two text strings."""
    if not a or not b:
        return 0.0
    tokens_a = set(_TOKEN_PATTERN.findall(a.lower()))
    tokens_b = set(_TOKEN_PATTERN.findall(b.lower()))
    if not tokens_a or not tokens_b:
        return 0.0

    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return float(intersection / union) if union > 0 else 0.0


def should_replace_best_text(
    current_best: str,
    current_conf: float,
    new_text: str,
    new_conf: float,
) -> bool:
    """Determine whether new OCR candidate text is superior to existing best text."""
    if not current_best:
        return True

    tokens_current = len(_TOKEN_PATTERN.findall(current_best.lower()))
    tokens_new = len(_TOKEN_PATTERN.findall(new_text.lower()))

    # 1. Significantly longer complete sentence with reasonable confidence
    if tokens_new > tokens_current and new_conf >= (current_conf - 0.15):
        return True

    # 2. Similar length but noticeably higher OCR confidence
    if tokens_new >= tokens_current and new_conf > (current_conf + 0.05):
        return True

    return False


@dataclass
class SubtitleTrack:
    """Represents an active or historical subtitle line tracked across video frames."""
    text: str
    best_text: str
    best_conf: float
    first_seen: float
    last_seen: float
    count: int = 1
    boxes: List[SubtitleBox] = field(default_factory=list)
    confidences: List[float] = field(default_factory=list)

    def update(
        self,
        box: SubtitleBox,
        confidence: float,
        timestamp: float,
        new_text: str = "",
        max_history: int = 50,
    ) -> None:
        """Update tracker with newly observed frame detection with bounded memory buffer."""
        self.last_seen = timestamp
        self.count += 1
        self.boxes.append(box)
        self.confidences.append(confidence)

        if len(self.boxes) > max_history:
            self.boxes = self.boxes[-max_history:]
            self.confidences = self.confidences[-max_history:]

        candidate = new_text or self.text
        if should_replace_best_text(self.best_text, self.best_conf, candidate, confidence):
            self.best_text = candidate
            self.best_conf = confidence

    @property
    def lifetime(self) -> float:
        """Total duration this subtitle line has been on screen in seconds."""
        return max(0.0, self.last_seen - self.first_seen)

    @property
    def stable_text(self) -> str:
        """Return the highest quality recognized string for this track."""
        return self.best_text if self.best_text else self.text


class SubtitleHistoryTracker:
    """Manages active and recently expired subtitle tracks across video frames."""

    def __init__(
        self,
        similarity_threshold: float = 0.60,
        expire_seconds: float = 3.0,
        stable_min_count: int = 2,
    ) -> None:
        self.similarity_threshold = similarity_threshold
        self.expire_seconds = expire_seconds
        self.stable_min_count = stable_min_count
        self._tracks: Dict[str, SubtitleTrack] = {}

    def update(
        self,
        detections: List[SubtitleDetection],
        now: Optional[float] = None,
    ) -> List[SubtitleTrack]:
        """Ingest new frame detections, match against active tracks, and prune stale entries.

        Returns list of currently stable tracks.
        """
        current_time = now if now is not None else time.time()

        for det in detections:
            text = det.text.strip()
            if not text:
                continue

            # Find best existing track by Jaccard similarity
            best_match_key: Optional[str] = None
            best_sim = 0.0

            for key, track in self._tracks.items():
                sim = text_similarity(text, track.stable_text)
                if sim > best_sim and sim >= self.similarity_threshold:
                    best_sim = sim
                    best_match_key = key

            if best_match_key is not None:
                track = self._tracks[best_match_key]
                track.update(det.box, det.confidence, current_time, new_text=text)
            else:
                # Spawn new track with collision-safe key
                base_key = f"{text}_{current_time:.3f}"
                new_key = base_key
                idx = 0
                while new_key in self._tracks:
                    idx += 1
                    new_key = f"{base_key}_{idx}"

                self._tracks[new_key] = SubtitleTrack(
                    text=text,
                    best_text=text,
                    best_conf=det.confidence,
                    first_seen=current_time,
                    last_seen=current_time,
                    count=1,
                    boxes=[det.box],
                    confidences=[det.confidence],
                )

        # Prune expired tracks
        self._prune(current_time)

        # Return active tracks meeting stability requirements
        active_stable = [
            t for t in self._tracks.values()
            if t.count >= self.stable_min_count or (current_time - t.first_seen) >= 0.3
        ]
        active_stable.sort(key=lambda t: t.boxes[-1].center_y if t.boxes else 0.0)
        return active_stable

    def _prune(self, now: float) -> None:
        """Remove tracks that have not been seen for longer than expire_seconds."""
        cutoff = now - self.expire_seconds
        expired = [k for k, t in self._tracks.items() if t.last_seen < cutoff]
        for k in expired:
            del self._tracks[k]

    def reset(self) -> None:
        """Clear all tracked history."""
        self._tracks.clear()
