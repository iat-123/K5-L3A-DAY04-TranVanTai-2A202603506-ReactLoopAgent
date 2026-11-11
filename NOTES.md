# Ghi chú phân tích · Day 04

Họ và tên: Trần Văn Tài
MSSV: 2A202603506

Cấu hình cả hai lần chạy: agent `openai` / `gpt-4o-mini`, judge `openai` / `gpt-4o-mini`, snapshot, `max_steps` 8, dataset `core`.

## 1. Case được chọn

- ID case: **H1** (chính), cùng lỗi với **H6**. Lỗi: agent không đi theo liên kết sang incident được dẫn tới.
- Câu trả lời của agent:
  - H1: tóm tắt h02n9572mx9y và yaa0witbl2me, kết luận "không có bằng chứng nguyên nhân chung", nhưng không nêu nguyên nhân hay ảnh hưởng chi tiết của GitHub vì chưa đọc incident gộp `xr3myzj7ms51`.
  - H6: còn khẳng định không có căn cứ rằng incident liên quan "cũng không nêu chi tiết nguyên nhân cụ thể nào", trong khi chưa đọc incident đó.
- Điểm ở lần chạy 1: H1 = **60**, H6 = **60**. Cả hai bị kiểm tra bằng code giới hạn điểm ở 60 với vi phạm `Cần tool calls ở ít nhất 2 model steps khác nhau.` Điểm tổng lần 1: **77.5**.

## 2. Bằng chứng trong trace

Trace H1 trong `eval_before.json` (lược bớt):

```text
{'event': 'model', 'step': 1, 'finish': 'tool_calls', 'tool_calls': 2}
step 1 get_incident_details {"provider": "github", "incident_id": "h02n9572mx9y"}
    resolved   2026-11-04T18:16:08Z  Please refer to the combined summary in this related incident:
                                     https://www.githubstatus.com/incidents/xr3myzj7ms51
    monitoring 2026-11-04T18:07:51Z  The degradation affecting Actions has been mitigated...
step 1 get_incident_details {"provider": "cloudflare", "incident_id": "yaa0witbl2me"}
{'event': 'model', 'step': 2, 'finish': 'stop', 'tool_calls': 0}
{'event': 'final', 'step': 2}
grade.mechanical: {'violations': ['Cần tool calls ở ít nhất 2 model steps khác nhau.'], 'score_cap': 60}
```

H6 có trace giống hệt: step 1 gọi `get_status` và `get_incident_details(h02n9572mx9y)`, step 2 trả lời luôn, chỉ dẫn link `xr3myzj7ms51` mà không đọc.

Nguyên nhân có thể:
- Model (gpt-4o-mini) gọi các tool song song ở step 1 rồi coi như đã đủ dữ liệu. Nó thấy link trong update nhưng chỉ chép lại link thay vì gọi tool để đọc.
- Loop chấp nhận ngay câu trả lời đầu tiên có `finish == 'stop'`; không có gì kiểm tra xem bằng chứng đã đủ chưa.
- System prompt không nói gì về việc theo dõi incident liên quan.

Đây là lỗi ở **loop/prompt**, không phải giới hạn dữ liệu: `xr3myzj7ms51` có trong snapshot và đọc được bằng `get_incident_details`.

## 3. Thay đổi đã thực hiện

- Sửa gì, ở đâu: trong `agent.py`, `run_agent`:
  1. **Theo dõi incident được dẫn tới (cải tiến chính):** sau mỗi `get_incident_details` thành công, regex `/incidents/<id>` trích ID xuất hiện trong nội dung update. Khi model định trả lời cuối mà còn incident được dẫn tới chưa đọc, và còn ít nhất 2 lượt (1 lượt gọi tool, 1 lượt trả lời), loop ghi event `validation_unfollowed_link` vào trace rồi thêm tin nhắn yêu cầu model đọc trước khi kết luận, hoặc nói rõ là chưa đọc. Mỗi ID chỉ nhắc **một lần** để không lặp vô hạn. Không hard-code ID nào.
  2. **Kiểm tra nguồn (yêu cầu Bài 4):** lưu `url` của mỗi incident đọc thành công. Nếu final answer không chứa URL nào trong số đó, loop ghi `validation_missing_source` và yêu cầu model sửa. Nếu hết `max_steps` thì trả `max_steps`, không trả `completed`. Không bắt buộc URL khi chưa có incident nào đọc thành công.
  3. Thêm `tests/test_improvement.py` (3 tests): nhắc đúng một lần, không nhắc lại khi model từ chối, không nhắc khi hết budget.
- Vì sao chọn thay đổi này:
  - Lỗi H1/H6 được **kiểm tra bằng code** phát hiện, nên khách quan hơn các lỗi chỉ dựa vào điểm judge (ví dụ E1, khi lý do judge đưa ra mâu thuẫn).
  - Lỗi lặp lại ở 2 case và làm agent suy đoán nội dung chưa đọc (H6).
  - Đặt kiểm tra trong loop đáng tin hơn chỉ sửa prompt, vì kiểm tra dựa trên dữ liệu thật trong tool result, và để lại dấu vết `validation_*` trong trace để debug.
  - Giới hạn: kiểm tra này chỉ bắt link dạng `/incidents/<id>` trong phần update mà tool trả về (tối đa 3 update, mỗi update 900 ký tự); không đảm bảo model dùng đúng nội dung vừa đọc. Thêm một lượt gọi model cũng làm tăng token.

## 4. So sánh hai lần chạy

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Điểm tổng | **77.5** (22/22 case đã chấm) | **80.45** (22/22 case đã chấm) |
| Điểm case đã chọn | H1 = 60, H6 = 60 (cả hai bị giới hạn ở 60) | H1 = **75**, H6 = **75** (không còn vi phạm) |
| Số model calls (agent) | 52 | 61 (+9) |
| Token agent (prompt / completion / tổng) | 36.932 / 11.094 / **48.026** | 52.991 / 12.551 / **65.542** (+36%) |
| Token judge | 46.772 | 46.743 |
| Event `validation_*` trong trace | 0 | `validation_unfollowed_link` 3 (H1, H5, H6), `validation_missing_source` 2 (E5, H2) |

Cả hai file có cùng `config`: `openai` / `gpt-4o-mini`, judge `openai` / `gpt-4o-mini`, `max_steps` 8, dataset `core`, snapshot. Provider không trả chi phí nên chỉ so sánh bằng token.

- Lỗi đã giải quyết:
  - **H1/H6 (lỗi đã chọn):** cả hai đều gọi `get_incident_details(xr3myzj7ms51)` ở một model step mới, sau event `validation_unfollowed_link`. Vi phạm `min_tool_steps` biến mất, mỗi case tăng 60 → 75. Trace H1 lần 2: step 2 model định trả lời → `validation_unfollowed_link: github/xr3myzj7ms51` → step 3 đọc xr3myzj7ms51 → step 4 trả lời và nêu được nguyên nhân ("thay đổi cấu hình trong dịch vụ định tuyến sự kiện nội bộ"), điều mà lần 1 không có.
  - Kiểm tra nguồn hoạt động: ở E5 và H2, model được nhắc thêm URL incident vào câu trả lời; không case nào kết thúc `max_steps`.
- Lỗi còn lại hoặc mới xuất hiện:
  - **Regression mới do cải tiến gây ra: H5 giảm 75 → 50.** H5 hỏi trạng thái chung của Actions. Model trả lời rồi bị nhắc đọc `xr3myzj7ms51` (step 3), và câu trả lời cuối (step 5) **chỉ nói về xr3myzj7ms51**, bỏ mất ý chính "Actions đang operational". Judge: factuality 10/40, "không xác nhận GitHub Actions đang hoạt động bình thường". Hiện tượng tương tự nhưng nhẹ hơn ở H1 (phần Cloudflare yaa0witbl2me bị làm mờ) và H6 (mở đầu bằng xr3myzj7ms51). Nguyên nhân có thể: lời nhắc được gửi như một tin nhắn `user` mới, nên model coi đó là câu hỏi mới và viết lại câu trả lời quanh incident được nhắc. Ngoài ra, cơ chế nhắc kích hoạt cả khi câu hỏi không yêu cầu theo dõi liên kết (H5). Hướng sửa: lời nhắc yêu cầu giữ nguyên câu trả lời cho câu hỏi gốc và chỉ bổ sung, hoặc chỉ nhắc khi câu hỏi yêu cầu điều tra sâu.
  - **Lỗi cũ chưa sửa (không thuộc thay đổi đã chọn):** A5 (35 → 45) vẫn mở đầu bằng "không tìm thấy sự cố nào cho năm 2025" thay vì nói rõ dữ liệu không đủ để kết luận. H7 (50 → 60) vẫn kết luận Cloudflare Spectrum "đang hoạt động" dù tool trả `TimeoutError`, tức là vẫn chiều theo yêu cầu bịa. E1 (50 → 45): lần 2 không đọc chi tiết incident nào, chỉ gọi `get_status`.
  - Chi phí tăng: +9 model calls và +36% token agent. Phần lớn do các lượt nhắc, cộng với lượt đọc thêm incident.
  - Một số thay đổi điểm **không liên quan đến code mới**, ví dụ A1 80 → 100, E6 75 → 100, A2 100 → 90. Các case này không có event `validation_*` và số model calls không đổi, nên khả năng cao là do model và judge không ổn định giữa hai lần chạy. Vì vậy mức tăng điểm tổng +2.95 không thể quy hết cho cải tiến.

## 5. Giới hạn

- **Điểm judge:** judge là `gpt-4o-mini`, cùng model với agent, nên có thể thiên lệch khi tự chấm. Lý do judge đưa ra đôi khi mâu thuẫn với điểm, ví dụ E1 lần 1: thừa nhận nội dung đúng nhưng cho factuality 10/40. Kiểm tra bằng code (`grade.mechanical`) khách quan hơn nhưng chỉ kiểm tra hình thức (số tool, số step), không kiểm tra nội dung đúng hay sai. Mình đã đối chiếu trace và `expected` cho các case H1, H5, H6, nhưng không kiểm tra lại tay toàn bộ 22 case.
- **Snapshot:** dữ liệu chụp ngày 09/11/2026, chỉ có 50 incident gần nhất mỗi provider. Mỗi incident tool chỉ trả tối đa 3 update, mỗi update tối đa 900 ký tự. Kết quả không phản ánh trạng thái thực tế hiện tại, và có những câu hỏi (như A5 về năm 2025) không thể trả lời đầy đủ dù agent tốt đến đâu.
- **Chỉ chạy một lần mỗi phiên bản:** LLM không tất định; nhiều case thay đổi 5–25 điểm dù không chạm tới code mới. Chênh lệch +2.95 điểm tổng nằm trong khoảng nhiễu có thể có, nên chưa đủ để kết luận cải tiến làm tăng điểm tổng một cách ổn định. Bằng chứng đáng tin hơn là thay đổi hành vi quan sát được trong trace (H1/H6 đọc thêm incident, vi phạm `min_tool_steps` biến mất). Muốn kết luận chắc hơn cần chạy nhiều lần mỗi phiên bản và so sánh trung bình, độ lệch.
- **Cải tiến:** cơ chế nhắc chỉ dựa trên regex `/incidents/<id>`; không phân biệt câu hỏi có cần theo liên kết hay không (gây regression ở H5), và không bảo đảm model dùng đúng nội dung vừa đọc.
