"""
Chroma-based Audio Fingerprinter (Invariant to Pitch Shifts and Tempo Changes)
Based on 12-pitch chroma FFT frames, prefix sum optimization, and Pearson correlation.
"""
import math
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Optional

FP_RATE = 11025
N = 2048
HOP = 2205 # ~0.2s per frame
FP_FPS = FP_RATE / HOP

# FFT bin -> pitch class (-1 = outside 80 Hz - 4000 Hz)
BIN_CLASS = np.full(N // 2, -1, dtype=np.int8)
for k in range(N // 2):
    f = (k * FP_RATE) / N
    if 80 <= f <= 4000:
        BIN_CLASS[k] = (((round(12 * math.log2(f / 440.0)) % 12) + 12 + 9) % 12)

WINDOW = 0.5 - 0.5 * np.cos((2 * math.pi * np.arange(N)) / (N - 1))

# Standard tempo changes suspect re-uploaders apply (+/- 12%)
TEMPOS = [1.0, 1.03, 0.97, 1.06, 0.94, 1.09, 0.91, 1.12, 0.88]

@dataclass
class Fingerprint:
    frames: int
    data: np.ndarray # shape: (frames, 12) float32

@dataclass
class FpMatch:
    score: float       # Pearson correlation (0.0 to 1.0)
    ref_at: float      # Seconds into reference where candidate matched
    semitones: int     # Pitch shift detected (-5 to +6 semitones)
    tempo: float       # Speed multiplier (suspect speed / original speed)

    @property
    def is_match(self) -> bool:
        return self.score >= 0.60

    @property
    def is_suspect(self) -> bool:
        return self.score >= 0.48

def compute_fingerprint(pcm_float32: np.ndarray) -> Fingerprint:
    """Computes normalized 12-pitch chroma fingerprint from mono PCM at 11,025 Hz."""
    total_samples = len(pcm_float32)
    frames = max(0, (total_samples - N) // HOP + 1)
    if frames == 0:
        return Fingerprint(frames=0, data=np.zeros((0, 12), dtype=np.float32))

    data = np.zeros((frames, 12), dtype=np.float32)
    for f in range(frames):
        offset = f * HOP
        chunk = pcm_float32[offset : offset + N] * WINDOW
        fft_vals = np.abs(np.fft.rfft(chunk)[:-1]) # N/2 bins
        
        c = np.zeros(12, dtype=np.float64)
        valid_mask = BIN_CLASS >= 0
        valid_bins = np.where(valid_mask)[0]
        valid_classes = BIN_CLASS[valid_bins]
        for b, cls in zip(valid_bins, valid_classes):
            c[cls] += fft_vals[b]

        c = np.log1p(c)
        norm = np.linalg.norm(c)
        if norm >= 1e-3:
            data[f] = c / norm

    return Fingerprint(frames=frames, data=data)

def _prepare(cand: Fingerprint, tempo: float, rot: int) -> np.ndarray:
    cand_frames = math.floor(cand.frames * tempo)
    out = np.zeros((cand_frames, 12), dtype=np.float32)
    if cand.frames == 0 or cand_frames == 0:
        return out
    
    src_indices = np.clip(np.round(np.arange(cand_frames) / tempo).astype(int), 0, cand.frames - 1)
    rotated_cols = (np.arange(12) + rot) % 12
    out = cand.data[src_indices][:, rotated_cols]
    return out

def _centre(x: np.ndarray, length: int) -> Tuple[np.ndarray, float]:
    sub = x[:length]
    mean = np.mean(sub, axis=0, keepdims=True)
    centered = sub - mean
    aa = float(np.sum(centered ** 2))
    return centered, aa

def _prefix_sums(ref: Fingerprint) -> Tuple[np.ndarray, np.ndarray]:
    s = np.zeros((ref.frames + 1, 12), dtype=np.float64)
    q = np.zeros((ref.frames + 1, 12), dtype=np.float64)
    s[1:] = np.cumsum(ref.data, axis=0)
    q[1:] = np.cumsum(ref.data ** 2, axis=0)
    return s, q

def match_fingerprint(ref: Fingerprint, cand: Fingerprint) -> FpMatch:
    """Finds best alignment of suspect audio inside reference audio across pitch & tempo axes."""
    empty = FpMatch(score=0.0, ref_at=0.0, semitones=0, tempo=1.0)
    if ref.frames < 25 or cand.frames < 25:
        return empty

    s_pre, q_pre = _prefix_sums(ref)

    # 1. Coarse search: all 12 key rotations x standard tempos
    coarse = _search_grid(ref, cand, s_pre, q_pre, TEMPOS, list(range(12)), empty)
    
    # 2. Fine search: refine tempo in 0.5% steps around best tempo
    fine_tempos = [round((coarse.tempo + d) * 1000) / 1000.0 for d in np.arange(-0.02, 0.0201, 0.005)]
    rot = (coarse.semitones + 12) % 12
    return _search_grid(ref, cand, s_pre, q_pre, fine_tempos, [rot], coarse)

def _search_grid(
    ref: Fingerprint,
    cand: Fingerprint,
    s_pre: np.ndarray,
    q_pre: np.ndarray,
    tempos: List[float],
    rots: List[int],
    start: FpMatch
) -> FpMatch:
    best = start
    for speed in tempos:
        for rot in rots:
            c = _prepare(cand, speed, rot)
            length = min(len(c), ref.frames)
            if length < 25:
                continue

            a, aa = _centre(c, length)
            if aa <= 0:
                continue

            max_offset = ref.frames - length
            for o in range(max_offset + 1):
                ref_slice = ref.data[o : o + length]
                ab = float(np.sum(a * ref_slice))
                if ab <= 0:
                    continue

                sum_b = s_pre[o + length] - s_pre[o]
                sum_sq_b = q_pre[o + length] - q_pre[o]
                bb = float(np.sum(sum_sq_b - (sum_b ** 2) / length))
                if bb <= 0:
                    continue

                score = ab / math.sqrt(aa * bb)
                if score > best.score:
                    st = rot - 12 if rot > 6 else rot
                    best = FpMatch(score=round(score, 4), ref_at=round(o / FP_FPS, 2), semitones=st, tempo=round(speed, 3))

    return best
