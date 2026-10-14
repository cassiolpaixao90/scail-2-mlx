"""Temporal planning independent of MLX, including incomplete final windows."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    start: int
    end: int
    padded_length: int

    @property
    def padding(self):
        return self.padded_length - (self.end - self.start)


def plan_segments(total_frames, segment_len=81, overlap=5, temporal_stride=4):
    if total_frames < 1 or temporal_stride < 1:
        raise ValueError("Frame count and temporal stride must be positive")
    if not 0 < overlap < segment_len:
        raise ValueError("Overlap must be positive and smaller than segment length")
    if (segment_len - 1) % temporal_stride or (overlap - 1) % temporal_stride:
        raise ValueError("Segment length and overlap must both be stride*k + 1")
    result = []
    start = 0
    while True:
        end = min(start + segment_len, total_frames)
        count = end - start
        padded = ((count - 1 + temporal_stride - 1) // temporal_stride) * temporal_stride + 1
        result.append(Segment(start, end, padded))
        if end == total_frames:
            return result
        start = end - overlap
