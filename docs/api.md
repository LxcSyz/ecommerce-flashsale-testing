# 接口约定

Base URL：`http://127.0.0.1:8000`。请求体为 JSON 对象，受保护接口使用 `Authorization: Bearer <token>`。下单接口还必须传 `Idempotency-Key`，1–128 字符。金额单位为分，时间字段为 Unix 秒。

| 方法 | 路径 | 请求体 | 认证 | 成功响应 |
| --- | --- | --- | --- | --- |
| GET | /api/health | 无 | 无 | 200 服务状态 |
| POST | /api/auth/register | username, password | 无 | 201 用户 id 与用户名 |
| POST | /api/auth/login | username, password | 无 | 200 token、expires_in、username |
| GET | /api/me | 无 | 是 | 200 当前用户 |
| GET | /api/products | 无 | 无 | 200 商品列表 |
| GET | /api/cart | 无 | 是 | 200 购物车列表 |
| POST | /api/cart | product_id, quantity | 是 | 200 更新后的购物车（设置数量） |
| DELETE | /api/cart/{product_id} | 无 | 是 | 200 更新后的购物车 |
| POST | /api/orders | items | 是 | 201 订单（同键重试也返回 201） |
| POST | /api/flash-sale/orders | items | 是 | 201 秒杀订单 |
| GET | /api/orders | 无 | 是 | 200 本人订单列表 |
| GET | /api/orders/{id} | 无 | 是 | 200 本人订单详情 |
| POST | /api/orders/{id}/pay | 无或 {} | 是 | 200 模拟支付后的订单 |
| POST | /api/orders/{id}/cancel | 无或 {} | 是 | 200 取消后的订单 |

下单请求：

```json
{"items": [{"product_id": 1, "quantity": 2}]}
```

订单示例（created_at 随实际运行变化）：

```json
{
  "id": 1,
  "user_id": 1,
  "status": "pending",
  "total_cents": 39800,
  "kind": "regular",
  "created_at": 1794211200,
  "items": [{"product_id": 1, "quantity": 2, "price_cents": 19900}]
}
```

错误响应统一为：

```json
{"error": {"code": "OUT_OF_STOCK", "message": "库存不足"}}
```

| HTTP | 常见 code | 含义 |
| --- | --- | --- |
| 400 | INVALID_JSON | JSON 无法解析 |
| 401 | UNAUTHORIZED / INVALID_CREDENTIALS | 登录失效或凭据错误 |
| 404 | PRODUCT_NOT_FOUND / ORDER_NOT_FOUND / NOT_FOUND | 资源不存在；他人订单也返回 404 |
| 409 | USERNAME_EXISTS | 用户名重复 |
| 409 | OUT_OF_STOCK / PURCHASE_LIMIT / SALE_INACTIVE | 库存不足、限购、活动窗口外 |
| 409 | IDEMPOTENCY_CONFLICT / INVALID_ORDER_STATE | 幂等键内容冲突、状态流转非法 |
| 409 | WRONG_CHANNEL / FLASH_ONLY | 商品下单入口不匹配 |
| 413 | BODY_TOO_LARGE | 请求体超过 64 KiB |
| 422 | INVALID_ARGUMENT / DUPLICATE_PRODUCT / FLASH_LIMIT / IDEMPOTENCY_KEY_REQUIRED | 参数不合法 |
| 503 | DATABASE_BUSY | 数据库写入竞争超时等不可用情况 |

幂等键范围是“用户 + 键”，不同下单入口共用该命名空间；同键改变入口也会冲突。失败下单不会持久化幂等记录；成功订单重试返回订单当前状态。客户端价格字段会被忽略。
