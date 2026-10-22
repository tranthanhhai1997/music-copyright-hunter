#!/usr/bin/env python3
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import argparse
from copyright_hunter.scanner import ReuploadScanner
from copyright_hunter.fingerprint import compute_fingerprint, match_fingerprint
from copyright_hunter.report_generator import ReportGenerator

def main():
    parser = argparse.ArgumentParser(description="Music Copyright & Re-upload Hunter CLI")
    subparsers = parser.add_subparsers(dest="cmd")

    # Command 1: scan
    p_scan = subparsers.add_parser("scan", help="Scan YouTube for re-uploads of your song")
    p_scan.add_argument("audio", help="Path to your original audio file (mp3, wav, m4a)")
    p_scan.add_argument("-t", "--title", required=True, help="Official title of the song")
    p_scan.add_argument("-l", "--lyrics", help="Lyrics or prominent hooks")
    p_scan.add_argument("-o", "--out", default="report.md", help="Output Markdown report path")
    p_scan.add_argument("--json", help="Optional output JSON path")

    # Command 2: compare
    p_comp = subparsers.add_parser("compare", help="Compare two audio files directly")
    p_comp.add_argument("original", help="Reference original audio file")
    p_comp.add_argument("suspect", help="Suspect audio file")

    args = parser.parse_args()
    scanner = ReuploadScanner()

    if args.cmd == "compare":
        print(f"Comparing: {args.original} vs {args.suspect}...")
        ref_pcm = scanner.pcm_from_media(args.original)
        cand_pcm = scanner.pcm_from_media(args.suspect)
        ref_fp = compute_fingerprint(ref_pcm)
        cand_fp = compute_fingerprint(cand_pcm)
        match = match_fingerprint(ref_fp, cand_fp)
        print("--------------------------------------------------")
        print(f"Score:               {match.score * 100:.2f}%")
        print(f"Detected Shift:      {match.semitones:+d} semitones")
        print(f"Detected Tempo:      {match.tempo:.2f}x")
        print(f"Matched Timestamp:   {match.ref_at:.2f}s")
        print(f"Verdict:             {'EXACT MATCH' if match.is_match else ('SUSPECT' if match.is_suspect else 'DIFFERENT')}")
        print("--------------------------------------------------")
        return

    if args.cmd == "scan":
        hits = scanner.scan_song(
            original_audio_path=args.audio,
            song_title=args.title,
            lyrics=args.lyrics
        )
        md = ReportGenerator.generate_markdown(args.title, hits)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"\n[HOÀN TẤT] Đã xuất báo cáo ra file: {args.out}")
        if args.json:
            ReportGenerator.save_json(hits, args.json)
            print(f"Đã lưu JSON ra file: {args.json}")
        return

    parser.print_help()

if __name__ == "__main__":
    main()
