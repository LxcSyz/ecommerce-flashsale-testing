# 性能实验说明

## 两类实验

`tests/api/test_flash_concurrency.py` 是确定性业务正确性回归，24 个用户竞争 10 件库存；它不用于提供系统最大吞吐结论。

`performance/locustfile.py` 是可重复的混合业务负载脚本，按权重执行浏览商品、普通下单取消、秒杀下单取消。每位虚拟用户先独立注册和登录；注册登录的 PBKDF2 开销会计入 Locust 统计，应与稳定阶段业务请求分开解读。

## 运行步骤

1. 使用单独的数据库启动服务：`python -m app.server --db data/load.db`。首次建立数据库会种入 10 件秒杀库存，活动持续 24 小时。
2. 安装 `requirements-performance.txt`。
3. 先跑 5 用户短时冒烟，再逐步提高到 20 / 50 用户；每轮记录参数、机器信息、时间和数据文件。
4. 停止负载后运行 `python scripts/check_inventory.py --db data/load.db`，检查全部商品守恒。需要完全独立数据时使用一个新的数据库文件名。

```powershell
.\.venv\Scripts\python.exe -m locust -f performance/locustfile.py --host http://127.0.0.1:8000 --headless -u 5 -r 2 -t 15s --csv reports/smoke --html reports/smoke.html
```

每个成功订单会再请求取消，实现有限库存循环使用。库存不足 OUT_OF_STOCK 是符合规则的业务拒绝，在 Locust 中单独命名并标记为成功处理的请求；它不是“抢购成功”，不能混入业务成交率。SALE_INACTIVE、PURCHASE_LIMIT、5xx 等均记录为失败，需排查活动数据或系统行为。

负载停止可能中断“下单后取消”的后半段，从而留下待支付订单；对应库存应仍被预占。核对时以有效订单守恒为准，不能直接要求所有库存都回到初始值。CSV 为周期快照，可能比终端最终统计少几个收尾请求；报告须明确采用哪个数据源。

## 应记录的指标

| 指标 | 解读 |
| --- | --- |
| 请求数 / RPS | 按接口及业务拒绝分类查看 |
| P50 / P95 / P99 | 同时列出用户数、预热和观测时长 |
| 技术失败率 | 非预期 4xx、5xx、网络超时 |
| 订单成功数 / 售罄拒绝数 | 分开表达业务吞吐和业务拒绝 |
| 库存守恒 | 压测停止后核对库存和有效订单 |
| CPU / 内存 | 手工通过系统监控采样，当前脚本未自动采集 |

SQLite 写锁会限制写入吞吐；服务与负载工具在同一机器时还会竞争资源。短时低并发冒烟只说明脚本与业务路径可运行。当前实测摘要见 `docs/test-report.md`，不要把它描述为生产压测结论。
