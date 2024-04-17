Production Planning
----

Lấy sale.order từ sales, và demand.order từ phòng plan để tạo ra 1 plan order tổng cho tháng, quý. Rồi chạy để sinh ra dữ liệu kho, sản xuất, mua hàng. Các chức năng chính:
 
Hiển thị tổng danh sách vật tư cho plan order
---------------------------

Tổng vật tư dự kiến cho plan order theo từng plan line, kết quả lấy từ Bill of materials của item trên plan line. Kết hợp mới model stock.reservation để tạo reserved stock cho vật tư, component trước khi chạy plan.


Tạo model demand.order
----------------------------

Tạo model demand.order từ sale.order, plan forecaste, claim. Trên từng demand.order.line chọn cách sản xuất item có màu, hoặc chỉ làm hàng white (không có màu).


Chạy plan theo queue.job
----------------------------

Set queue khi chạy plan để sinh ra phiếu kho, sản xuất, mua hàng. Để giảm thời gian chờ cho user