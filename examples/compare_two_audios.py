import sys, os
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from copyright_hunter.scanner import ReuploadScanner
from copyright_hunter.fingerprint import compute_fingerprint, match_fingerprint

scanner = ReuploadScanner()

# So sánh 2 file âm thanh
file_a = "original.mp3"
file_b = "suspect_pitch_shifted.mp3"

if not os.path.exists(file_a) or not os.path.exists(file_b):
    print("Vui lòng chuẩn bị 2 file audio để so sánh: original.mp3 và suspect_pitch_shifted.mp3")
    sys.exit(0)

print("Đang tính dấu vân tay âm thanh (Chroma 12-pitch FFT)...")
fp_a = compute_fingerprint(scanner.pcm_from_media(file_a))
fp_b = compute_fingerprint(scanner.pcm_from_media(file_b))

result = match_fingerprint(fp_a, fp_b)
print(f"Độ trùng khớp: {result.score * 100:.1f}%")
print(f"Độ lệch cao độ: {result.semitones:+d} bán âm")
print(f"Tỉ lệ tốc độ: {result.tempo:.2f}x")
print(f"Khớp tại giây thứ: {result.ref_at:.1f}s")
