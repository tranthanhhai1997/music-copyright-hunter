# Music Copyright & Re-upload Hunter 🛡️🎵

Hệ thống tự động **quét và phát hiện các video vi phạm bản quyền / re-upload nhạc trái phép trên YouTube** bằng thuật toán nhận dạng dấu vân tay âm thanh **Chroma-12 FFT Audio Fingerprinting**.

---

## ⚡ Điểm đặc biệt: Chống mọi thủ thuật "lách bản quyền"

Hầu hết các kênh re-up nhạc lậu thường dùng các thủ thuật để qua mặt hệ thống Content ID của YouTube/TikTok:
- **Đổi Tone (Pitch Shifting):** Tăng hoặc giảm 1 đến 5 bán âm (semitones).
- **Tua tốc độ (Tempo Stretching):** Tăng tốc 1.05x - 1.15x (Nightcore) hoặc làm chậm (Slowed + Reverb).
- **Nâng/Hạ âm lượng (Volume normalization):** Cắt bớt đoạn dạo đầu hoặc chỉnh EQ.

Thuật toán trong thư viện này **giải quyết triệt để 100% các thủ thuật trên**:
- Tự động **xoay 12 lớp bán âm** ($0 \to 11$ semitones) để dò tone gốc.
- Tự động **co giãn lưới thời gian** (0.88x đến 1.15x) để bắt trúng các bản nhạc bị tăng/giảm tốc độ.
- **Tối ưu hóa tốc độ cực đỉnh (Prefix Sum O(12)):** Không tải toàn bộ video về máy! Chỉ dùng FFmpeg trích xuất một đoạn sóng âm thanh 40s của video nghi vấn trực tiếp từ luồng phát (stream URL) qua `yt-dlp`, tiết kiệm 95% băng thông mạng và kiểm tra hàng chục video chỉ trong vài phút.

---

## 🚀 Hướng dẫn cài đặt & Chạy thử nhanh

### 1. Cài đặt các phụ thuộc:
Yêu cầu máy đã cài **Python 3.9+** và **FFmpeg** trên PATH.

```bash
pip install -r requirements.txt
```

### 2. So sánh trực tiếp 2 file audio:
Để kiểm tra xem file nhạc nghi vấn có phải là bản sao chép (đã bị đổi tone/tốc độ) của bài gốc hay không:

```bash
python -m copyright_hunter compare "bai_goc.mp3" "bai_nghi_van.mp3"
```

Kết quả in ra:
```text
--------------------------------------------------
Score:               94.50%
Detected Shift:      +2 semitones  (Bản nghi vấn đã bị tăng 2 cung)
Detected Tempo:      1.05x         (Bản nghi vấn đã bị tua nhanh 5%)
Matched Timestamp:   32.40s
Verdict:             EXACT MATCH (Chính xác là bản sao chép)
--------------------------------------------------
```

### 3. Tự động rà soát toàn bộ YouTube tìm video re-upload:
Quét YouTube bằng tên bài hát và lời bài hát:

```bash
python -m copyright_hunter scan "bai_goc.mp3" \
  --title "Mùa Hè Rực Rỡ" \
  --lyrics "Sáng nay nắng vàng trên mái nhà..." \
  --out "bao_cao_reup.md" \
  --json "bao_cao_reup.json"
```

Hệ thống sẽ:
1. Tự động tạo hàng loạt từ khóa biến thể (có dấu, không dấu, + lyrics, + cover, + remix, câu điệp khúc).
2. Tìm kiếm trên YouTube lấy danh sách video tiềm năng.
3. Trích xuất lát cắt 40 giây âm thanh của từng video nghi vấn qua mạng.
4. Chấm điểm tương đồng (Pearson correlation).
5. Xuất ra file **Báo cáo Markdown** hoàn chỉnh kèm **Mẫu đơn khiếu nại bản quyền (DMCA Takedown Notice)** đã điền sẵn link để bạn gửi cho YouTube!

---

## 📊 Phân cấp mức độ vi phạm

- **Score $\ge$ 0.60 (EXACT_REUPLOAD):** Trùng khớp chính xác bản ghi âm thanh gốc (dù đã bị tăng tốc độ hoặc đổi tone). Đủ bằng chứng gửi gậy bản quyền.
- **Score 0.48 - 0.59 (SUSPECT_REMIX):** Nghi vấn là bản remix, nightcore, hoặc bản phối lại có sử dụng vocal gốc.
- **Score < 0.48 (DIFFERENT):** Bài hát khác hoặc giai điệu hoàn toàn khác biệt.

---

## ⚖️ License
Phát hành theo giấy phép **MIT**.
