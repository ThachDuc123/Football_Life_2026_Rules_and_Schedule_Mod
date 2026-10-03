# Luật UEFA 2024+ cho Champions League và Europa League (FL26)

Mọi thay đổi chỉ nằm trong bộ nhớ game và trong quy định giải (`livecpk/UEFA36`). Không sửa EXE, không sửa save trên đĩa.

## Thể thức

| Mục | Cách làm |
|---|---|
| Số đội | 36 mỗi giải. UCL: 24 vào thẳng + 8 đội thắng play-off + 4 đội thua play-off xếp cao nhất bảng xếp hạng CLB của game. UEL: 32 đội vào thẳng đầu danh sách + 4 đội thua play-off UCL còn lại |
| Nhóm hạt giống | 4 nhóm × 9 theo bảng xếp hạng CLB thế giới của game (cập nhật mỗi mùa); đương kim vô địch UCL ở nhóm 1 |
| Đối thủ | 2 đội mỗi nhóm (1 sân nhà, 1 sân khách) = 8 trận, 4 nhà 4 khách; không gặp đội cùng nước; tối đa 2 đối thủ cùng nước |
| Quy định 2026/27 | Không lặp lại cùng một trận với cùng đội chủ nhà 3 mùa liên tiếp (lịch sử trong `content/ucl_calendar_guard/league_history.txt`, theo CLB bạn dẫn dắt) |
| Lượt đấu | 8 lượt × 18 trận. Mỗi cặp lượt (1–2, 3–4, 5–6, 7–8) mỗi đội 1 nhà 1 khách, nên không có 3 trận liền cùng sân |
| Ngày | UCL: 15/9, 29/9, 20/10, 3/11, 24/11, 8/12, 19/1, 27/1. UEL (thứ Năm): 24/9, 1/10, 22/10, 5/11, 26/11, 10/12, 21/1, 28/1 |
| Bảng xếp hạng | Một bảng 36 đội trong game cho mỗi giải. Điều 18.01: điểm, hiệu số, bàn thắng, bàn thắng sân khách, trận thắng, trận thắng sân khách, điểm/hiệu số/bàn thắng của các đối thủ, điểm kỷ luật, hệ số CLB (= bảng xếp hạng CLB của game) |
| Đi tiếp | 1–8 vào vòng 16 đội, 9–24 đá play-off, 25–36 bị loại (không xuống giải khác) |
| Nhánh | Play-off 9/10–23/24, 11/12–21/22, 13/14–19/20, 15/16–17/18; vòng 16 đội 1/2 gặp đội thắng cặp 15/16–17/18…; 1 và 2 ở hai nửa nhánh; tứ kết A–D, B–C |
| Lượt về | Đội xếp hạng cao hơn ở vòng phân hạng đá lượt về sân nhà (mọi vòng, cả UEL) |
| Lịch knock-out | UCL: 16 & 23/2, 9 & 16/3, 6 & 13/4, 27/4 & 4/5, chung kết 30/5. UEL: 18 & 25/2, 11 & 18/3, 8 & 15/4, 29/4 & 6/5, chung kết 26/5 |

Mùa của một save được tạo theo quy định cũ (8 bảng) vẫn chạy thể thức 32 đội cũ cho tới hết mùa (với knock-out theo luật mới).

## File

| File | Vai trò |
|---|---|
| `make_regulation.py` → `livecpk/UEFA36/.../CompetitionRegulation.bin` | UCL/UEL: 36 đội, 4 bảng × 9, đá một lượt (144 trận) |
| `euro_league.h` | Bốc thăm 36 đội và xếp 8 lượt (dùng trong `ucl32_format`) |
| `../ucl32_format.cpp` → `modules/ucl32_format_v111.dll` 2.1.0 | Trước khi game xếp ngày từng bảng: ghi cặp đấu + lượt vào 36 trận của bảng và dựng lại 9 vòng của bảng |
| `euro_core.h`, `euro_rules.cpp` → `modules/euro_rules.dll` 1.3.0 | Xếp hạng, nhánh, 24 đội đi tiếp (UCL/UEL), thêm/bớt đội trước bốc thăm, ngày vòng phân hạng, chung kết UEL, mùa 32 đội cũ qua `ucl32_c41` |
| `content/ucl_calendar_guard/euro_rules.py` | Bản Python của `euro_core.h` |
| `content/ucl_calendar_guard/repair_ucl_calendar.py` | Đội hạng cao đá lượt về sân nhà (UCL + UEL), báo cáo nhánh `euro` trong `calendar-status.json` |
| `modules/ucl_schedule_probe.lua` | Bảng 36 (hoặc 32) đội trong game cho UCL và UEL |
| `install_step1.py`, `install_step2.py` | Cài khi game tắt; `install_step1.py --remove` bỏ `UEFA36` khỏi `sider.ini` |
| `original/` | Bản trước khi sửa |

Nhật ký: `D:\FL26\euro_rules.log`, `D:\FL26\ucl32_format.log` (`LEAGUE36`: nhóm hạt giống, 8 lượt, lịch sử).

## Kiểm tra (`test/`)

| Lệnh | Kiểm tra |
|---|---|
| `compare.py test_core.exe <save...>` | C++ == Python (bảng, nhánh, đội thứ 3), kể cả khi mọi trận 0–0 |
| `test_league.exe ucl36.txt 300` | 300 lần bốc thăm: 0 vi phạm, ~10 ms |
| `snapshot_live.py <dir>` + `test_format36.exe <dir> [events_out] [--check]` | Bộ sinh lịch trên dữ liệu chụp từ game: 144 trận, 8×18, vòng/ô trận khớp, quy định 3 mùa |
| `test_probe36.py events_after.bin` | Bảng Lua == Python cho UCL và UEL |
| `test_guard.py <save> <năm>` | Đổi sân lượt về, báo cáo nhánh |
| `inspect_live.py` | Đọc nhanh trạng thái UCL/UEL trong game đang chạy |

## Gỡ

`python install_step1.py --remove` (game tắt) để bỏ quy định 36 đội; chép các file trong `original/` về chỗ cũ để bỏ hết.
