# 测试用例与追踪

自动化用例按参数展开共 40 个 API 用例、3 个 UI 用例。下表按业务场景归并，文件名对应 `tests/api/` 中的实现。

| 编号 | 场景 / 输入 | 预期结果 | 自动化定位 |
| --- | --- | --- | --- |
| AUTH-01 | 注册、重复注册、错误密码、正确登录 | 201 / 409 / 401 / 200 | test_auth_cart.py::test_register_login_and_duplicate |
| AUTH-02 | 短用户名、短密码、空白用户名、非字符串 | 422，4 组参数 | test_invalid_credentials |
| AUTH-03 | 检查数据库密码 | 保存盐和哈希，不存明文 | test_password_is_salted_hash |
| AUTH-04 | 无令牌、有效令牌、过期令牌 | 401 / 200 / 401 | test_missing_and_expired_token |
| AUTH-05 | SQL 注入式用户名 | 登录失败，不绕过认证 | test_sql_injection_does_not_bypass_login |
| CART-01 | 同商品设置数量两次，另一用户查询，删除 | 不累加、用户隔离、删除后为空 | test_cart_set_quantity_is_idempotent_and_isolated |
| CART-02 | 数量 0 / -1 / 101 / true / 1.5 / "2" / null | 422，7 组参数 | test_cart_quantity_boundaries |
| CART-03 | 秒杀商品加入购物车 | 409 FLASH_ONLY | test_flash_product_cannot_enter_cart |
| INPUT-01 | 损坏 JSON、数组请求体 | 400 / 422 | test_invalid_json_and_non_object |
| ORDER-01 | 两个键盘和一个鼠标，下单后支付与重复支付 | 总额 48700 分，库存只扣一次，购物车清理 | test_orders.py::test_cart_checkout_amount_pay_and_inventory |
| ORDER-02 | 连续三次取消同一订单，再支付 | 仅回补一次，支付返回 409 | test_cancel_restock_exactly_once |
| ORDER-03 | 同键同内容重试，再变更数量 | 同一订单，变更内容返回 409 | test_idempotency_replay_and_payload_conflict |
| ORDER-04 | 缺少键，不同用户使用相同键 | 缺键 422；用户之间可分别创建订单 | test_key_required_and_scoped_to_user |
| ORDER-05 | 用户 B 访问用户 A 的订单 | 列表无数据；详情/支付/取消均 404 | test_order_owner_isolation |
| ORDER-06 | 第二商品库存不足 | 整单回滚，首商品库存、购物车不变 | test_multi_item_failure_rolls_back_inventory_and_cart |
| ORDER-07 | 空列表、0 数量、重复商品、空商品项 | 422，4 组参数 | test_invalid_order_items |
| ORDER-08 | 客户端传 price_cents=1 | 服务端仍按 19900 分计价 | test_server_price_cannot_be_overridden |
| ORDER-09 | 最后 1 件库存，连续下单 | 首次成功，第二次 OUT_OF_STOCK | test_last_stock_and_sold_out |
| ORDER-10 | 不存在商品/订单 | 404 | test_unknown_product_and_order |
| FLASH-01 | 活动未开始 / 已结束 | SALE_INACTIVE，2 组参数 | test_flash_concurrency.py::test_flash_time_window |
| FLASH-02 | 错误入口、一次购买两件 | 409 / 422 | test_channel_and_quantity_rules |
| FLASH-03 | 同人重复抢购，取消后再抢 | 限购拒绝；取消后允许 | test_cancel_releases_flash_limit |
| CON-01 | 24 用户同时抢 10 件 | 10 成功，14 售罄，无 5xx，库存为 0 | test_24_buyers_compete_for_10_items |
| CON-02 | 同用户 12 个不同键同时抢购 | 1 成功，11 限购拒绝 | test_same_user_parallel_requests_cannot_bypass_limit |
| CON-03 | 同用户 12 个相同键同时下单 | 同一订单，库存仅扣 1 | test_parallel_same_key_only_deducts_once |
| CON-04 | 12 个请求同时取消 | 全部幂等返回，库存只回补 1 | test_parallel_cancellation_restock_once |
| CON-05 | 同时支付与取消 | 一次 200、一次 409，最终状态与库存匹配 | test_pay_cancel_race_has_one_final_state |
| UI-01 | 注册 → 加车 → 下单 → 模拟支付 | 页面显示正确金额、已支付、库存 99 | tests/ui/test_shopping.py::test_checkout_and_mock_payment |
| UI-02 | 注册 → 秒杀 → 取消 | 订单已取消，库存回到 10 | test_flash_cancellation_restores_inventory |
| UI-03 | 未登录点击秒杀 | 显示“请先登录” | test_anonymous_purchase_requires_login |

手工扩展检查：移动端布局、键盘焦点、活动精确起止时刻、用户名最大长度、超大请求体、网络断开后重试体验。这些检查不计入自动化通过数量。
