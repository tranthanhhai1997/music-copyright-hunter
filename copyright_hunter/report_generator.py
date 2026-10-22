"""
Report Generator & YouTube Copyright Takedown Notice Builder
"""
import os
import json
from typing import List
from .scanner import ScanHit

class ReportGenerator:
    @staticmethod
    def generate_markdown(song_title: str, hits: List[ScanHit]) -> str:
        md = [f"# BÁO CÁO RÀ SOÁT BẢN QUYỀN & RE-UPLOAD: {song_title.upper()}\n"]
        md.append(f"**Tổng số video phát hiện trùng khớp:** {len(hits)}\n")
        
        if not hits:
            md.append("✅ Không phát hiện bất kỳ video vi phạm bản quyền nào trên YouTube.")
            return "\n".join(md)

        md.append("| Trạng thái | Điểm tương đồng | Video URL | Kênh đăng | Đổi Tone | Tốc độ |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for h in hits:
            tag = "🚨 CHÍNH XÁC (RE-UPLOAD)" if h.verdict == "EXACT_REUPLOAD" else "⚠️ NGHI VẤN (REMIX/COVER)"
            shift = f"{h.pitch_shift_semitones:+d} semitones" if h.pitch_shift_semitones != 0 else "Gốc"
            tempo = f"{h.tempo_multiplier:.2f}x"
            md.append(f"| **{tag}** | **{h.match_score * 100:.1f}%** | [{h.title}]({h.url}) | {h.channel} | {shift} | {tempo} |")

        md.append("\n---\n## 📝 MẪU YÊU CẦU GỠ BẢN QUYỀN (YOUTUBE TAKEDOWN TEMPLATE)\n")
        md.append("```text")
        md.append(f"Kính gửi Đội ngũ Hỗ trợ Bản quyền YouTube,")
        md.append(f"Tôi là chủ sở hữu quyền tác giả hợp pháp của tác phẩm âm nhạc: "{song_title}".")
        md.append(f"Hệ thống phát hiện các đường link sau đây đã sao chép/sử dụng trái phép bản ghi âm thanh của chúng tôi mà không có sự cho phép:")
        for h in hits:
            md.append(f"- URL vi phạm: {h.url} (Kênh: {h.channel}, Độ tương đồng âm thanh: {h.match_score*100:.1f}%)")
        md.append("\nYêu cầu gỡ bỏ theo đạo luật DMCA / Tiêu chuẩn cộng đồng YouTube.")
        md.append("Tôi cam kết thông tin trên là chính xác dưới hình phạt nếu khai man.")
        md.append("```")
        return "\n".join(md)

    @staticmethod
    def save_json(hits: List[ScanHit], filepath: str):
        data = [h.__dict__ for h in hits]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
