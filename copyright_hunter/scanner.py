"""
YouTube Re-Upload Scanner & Audio Inspector
Uses yt-dlp to search query variants and FFmpeg to stream-inspect 40s audio slices without full download.
"""
import os
import json
import re
import unicodedata
import subprocess
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from .fingerprint import FP_RATE, compute_fingerprint, match_fingerprint, FpMatch

REUP_MATCH_THRESHOLD = 0.60
REUP_MAYBE_THRESHOLD = 0.48
WINDOW_SECONDS = 40.0

@dataclass
class ScanHit:
    video_id: str
    url: str
    title: str
    channel: str
    duration: float
    match_score: float
    ref_timestamp: float
    pitch_shift_semitones: int
    tempo_multiplier: float
    verdict: str  # "EXACT_REUPLOAD", "SUSPECT_REMIX", "DIFFERENT"

def unaccent(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def extract_lyric_hooks(lyrics: Optional[str], max_hooks: int = 2) -> List[str]:
    """Finds chorus hooks and prominent lines to search."""
    if not lyrics:
        return []
    lines = [l.strip() for l in lyrics.splitlines() if l.strip() and not l.startswith("[") and not l.startswith("(")]
    # Pick lines with 4+ words
    meaningful = [l for l in lines if len(l.split()) >= 4]
    return meaningful[:max_hooks]

class ReuploadScanner:
    def __init__(self, ytdlp_path: str = "yt-dlp", ffmpeg_path: str = "ffmpeg"):
        self.ytdlp = ytdlp_path
        self.ffmpeg = ffmpeg_path

    def pcm_from_media(self, media_path: str, start_sec: float = 0.0, duration: float = 0.0) -> np.ndarray:
        """Extracts mono float32 PCM at 11,025 Hz using FFmpeg pipe."""
        import numpy as np
        cmd = [
            self.ffmpeg, "-hide_banner", "-loglevel", "error",
            *(["-ss", str(start_sec)] if start_sec > 0 else []),
            *(["-t", str(duration)] if duration > 0 else []),
            "-i", media_path,
            "-vn", "-ac", "1", "-ar", str(FP_RATE),
            "-f", "f32le", "pipe:1"
        ]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        raw_bytes, err = p.communicate()
        if p.returncode != 0 and len(raw_bytes) == 0:
            raise RuntimeError(f"FFmpeg PCM decode failed: {err.decode('utf-8', errors='ignore')}")
        return np.frombuffer(raw_bytes, dtype=np.float32)

    def search_candidates(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Performs flat search on YouTube via yt-dlp."""
        cmd = [
            self.ytdlp,
            "--flat-playlist", "--dump-json", "--no-warnings",
            "--encoding", "utf-8",
            f"ytsearch{limit}:{query}"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        candidates = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                j = json.loads(line)
                vid_id = j.get("id", "")
                if re.match(r"^[\w-]{6,20}$", vid_id):
                    candidates.append({
                        "id": vid_id,
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                        "title": j.get("title", ""),
                        "channel": j.get("channel") or j.get("uploader") or "",
                        "duration": float(j.get("duration") or 0.0)
                    })
            except Exception:
                pass
        return candidates

    def get_audio_stream_url(self, video_id: str) -> Optional[str]:
        cmd = [
            self.ytdlp,
            "-f", "bestaudio/best", "-g", "--no-warnings", "--no-playlist",
            f"https://www.youtube.com/watch?v={video_id}"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith("http"):
                return line
        return None

    def scan_song(
        self,
        original_audio_path: str,
        song_title: str,
        lyrics: Optional[str] = None,
        max_search_candidates: int = 30
    ) -> List[ScanHit]:
        """
        Full scan pipeline:
        1. Fingerprint original audio
        2. Generate query variants
        3. Search YouTube
        4. Stream-probe 40s audio slices of candidates
        5. Match correlation
        """
        print(f"Fingerprinting original song: {original_audio_path}...")
        ref_pcm = self.pcm_from_media(original_audio_path)
        ref_fp = compute_fingerprint(ref_pcm)
        ref_duration = len(ref_pcm) / FP_RATE
        print(f"Original duration: {ref_duration:.1f}s, {ref_fp.frames} frames.")

        # Build search queries
        queries = [
            song_title,
            f"{song_title} lyrics",
            f"{song_title} cover",
            f"{song_title} remix",
            unaccent(song_title),
            f"{unaccent(song_title)} karaoke",
        ]
        for hook in extract_lyric_hooks(lyrics):
            queries.append(f'"{hook}"')

        # Gather candidates
        seen_ids = set()
        candidates = []
        for q in queries:
            if len(candidates) >= max_search_candidates:
                break
            print(f"Searching query: [{q}]...")
            for c in self.search_candidates(q, limit=10):
                if c["id"] not in seen_ids:
                    seen_ids.add(c["id"])
                    # Filter candidates whose duration is within +/- 50% of reference
                    if ref_duration > 0 and c["duration"] > 0:
                        if abs(c["duration"] - ref_duration) > ref_duration * 0.6:
                            continue
                    candidates.append(c)

        print(f"Found {len(candidates)} plausible candidates. Probing audio fingerprints...")
        hits: List[ScanHit] = []

        for idx, cand in enumerate(candidates, start=1):
            vid_id = cand["id"]
            stream_url = self.get_audio_stream_url(vid_id)
            if not stream_url:
                continue

            try:
                # Probe a 40s slice from second 20 to 60
                probe_start = 20.0 if cand["duration"] > 60 else 0.0
                cand_pcm = self.pcm_from_media(stream_url, start_sec=probe_start, duration=WINDOW_SECONDS)
                cand_fp = compute_fingerprint(cand_pcm)
                match = match_fingerprint(ref_fp, cand_fp)

                verdict = "DIFFERENT"
                if match.is_match:
                    verdict = "EXACT_REUPLOAD"
                elif match.is_suspect:
                    verdict = "SUSPECT_REMIX"

                if match.is_suspect:
                    hit = ScanHit(
                        video_id=vid_id,
                        url=cand["url"],
                        title=cand["title"],
                        channel=cand["channel"],
                        duration=cand["duration"],
                        match_score=match.score,
                        ref_timestamp=match.ref_at,
                        pitch_shift_semitones=match.semitones,
                        tempo_multiplier=match.tempo,
                        verdict=verdict
                    )
                    hits.append(hit)
                    print(f"  [{idx}/{len(candidates)}] MATCH ({match.score:.2f}) -> {cand['title']} ({verdict})")
                else:
                    print(f"  [{idx}/{len(candidates)}] Checked ({match.score:.2f}) -> {cand['title']}")
            except Exception as e:
                pass

        hits.sort(key=lambda h: -h.match_score)
        return hits
