# 测试执行报告

执行日期：2026-11-09（Asia/Shanghai）。本报告记录生成项目时的本机实测，结果与下列原始证据一起提交，后续修改后应重新执行更新。

## 环境

Windows 10.0.22621，AMD64，16 个逻辑处理器；Python 3.9.12，SQLite；pytest 8.4.2、Requests 2.32.5、Playwright 1.60.0、pytest-playwright 0.7.1、Locust 2.34.0、gevent 24.11.1。测试依赖位于项目隔离 `.venv`，`pip check` 通过。

服务、回归和负载工具在同一台机器运行；短时压测与最终回归有时间重叠。因此性能数据仅用于验证脚本可运行和业务路径，不能用作容量基线。

## 最终回归

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api tests/ui --browser chromium --junitxml=reports/full-junit.xml --alluredir=reports/final-allure -q
```

| 项目 | 结果 |
| --- | --- |
| 接口与并发用例 | 40 通过 |
| Chromium 浏览器用例 | 3 通过 |
| 失败 / 错误 / 跳过 | 0 / 0 / 0 |
| pytest 总耗时 | 34.20 秒（JUnit suite 时间 34.147 秒） |
| 24 用户抢 10 件 | 10 成功、14 售罄，库存 0，无超卖 |
| 同用户 12 路抢购 | 1 成功、11 限购拒绝 |
| 同键 12 路重试 | 同一订单，仅扣 1 件 |
| 12 路取消 | 仅回补一次 |
| 支付与取消竞争 | 一个 200、一个 409，最终状态与库存匹配 |

证据：[完整 JUnit XML](evidence/full-junit.xml)。该文件记录全部用例及抢购实验的自定义属性。Allure 原始数据已在本地 `reports/final-allure` 生成；未将未安装的 Allure CLI 网页报告声称为已验证。

## 隔离缺陷实验

| 路径 | 买家数 | 初始库存 | 成功预占 | 剩余库存 | 超卖 |
| --- | --- | --- | --- | --- | --- |
| 缺陷样例 | 24 | 10 | 24 | -14 | 14 |
| 修复样例 | 24 | 10 | 10 | 0 | 0 |

证据：[实验 JSON](evidence/defect-replay.json)。这是刻意控制执行顺序的教学样例，具体根因与应用回归的区别见 [缺陷报告](defects.md)。

## Locust 冒烟

负载参数：5 用户，每秒启动 2 用户，配置运行时长 15 秒，随机等待 0.2–0.8 秒。业务为浏览、普通下单取消和秒杀下单取消。退出码 0。

以下从 [Locust 最后一次 CSV 快照](evidence/smoke_stats.csv) 读取；CSV 定时采样，终端收尾统计为 218 次，两者采样时刻不同，不混用计算指标。

| CSV 快照指标 | 实测 |
| --- | --- |
| 请求数 | 215 |
| 失败数 | 0 |
| RPS（该次全程快照） | 15.24 |
| P50 / P95 / P99（近似分位） | 14 / 31 / 64 ms |
| 普通下单 / 秒杀下单 | 70 / 14 |
| 取消请求 | 84 |

负载停止后独立核对应用数据库：

| 商品 | 初始库存 | 剩余库存 | 有效订单占用 | 守恒 |
| --- | --- | --- | --- | --- |
| 键盘 | 100 | 100 | 0 | 通过 |
| 秒杀耳机 | 10 | 9 | 1 | 通过 |
| 鼠标 | 50 | 50 | 0 | 通过 |

证据：[只读库存核对结果](evidence/inventory.json)。收尾时 Locust 中断了一个下单后的取消流程，留下一个 pending 订单，预占库存 1，与业务规则一致。这也说明“库存没有全部恢复”不必然等于库存不一致，须结合有效订单检查。

## 页面检查与尚未验证事项

实际查看了桌面 1440 px 和移动端 390 px 的截图；截图脚本检查无 JavaScript 未捕获异常、移动端无横向溢出。[桌面截图](assets/tradelab.png) 已放入 README。

上述表格是本机执行记录。项目现已上传，远端 Linux / Python 3.9、3.12 与 Chromium 的验证结果见 [GitHub Actions](https://github.com/LxcSyz/ecommerce-flashsale-testing/actions/workflows/test.yml)，以对应提交的实际状态为准。

Firefox / WebKit、真实支付、自动关单、分布式库存和生产级容量未在本轮验证。准确活动时间边界目前只有未来/过去窗口用例，精确等于边界时刻的可控时钟测试仍可扩展。
