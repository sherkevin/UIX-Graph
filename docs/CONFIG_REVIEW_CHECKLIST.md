# 诊断配置评审清单

> **谁需要这份文档?**
> - **专家** 在编辑 [`config/reject_errors.diagnosis.json`](../config/reject_errors.diagnosis.json) 等诊断配置后,提 PR 前自查
> - **PR 评审者** 按本清单逐项打勾,作为 merge 标准
> - **新接手人** 第一次理解「一份合格的配置长什么样」
>
> **核心原则**:本项目目标是**配置驱动**——专家只改 JSON,不写 Python。任何配置错误都应该在
> 启动期(rule_validator)或 PR 期(`scripts/check_config.py`)被发现,而不是上线后用户拿到错根因才暴露。

---

## 0. 评审前 30 秒:跑两个工具

```bash
# 1. 自助配置检查(本地)
python scripts/check_config.py
# 期望:每个 pipeline 显示 [OK];exit code 0

# 2. 不依赖 DB 的回归测试
cd src/backend
python -m pytest tests/test_rule_validator_metric.py tests/test_rules_validator.py \
                  tests/test_diagnosis_config_store.py tests/test_rules_engine_conditions.py -v
# 期望:全过(包括 test_current_rules_config_is_valid 这个回归保险)
```

任何一项失败,**先修了再 review**。

---

## 1. metric 元数据(在 [`metrics`](../config/reject_errors.diagnosis.json) 字典里)

### 1.1 必填项

| 字段 | 何时必填 | 检查 |
|------|---------|------|
| `source_kind` | 所有 metric(除非 `role: derived` 占位) | 在 `failure_record_field` / `request_param` / `mysql_nearest_row` / `clickhouse_window` / `intermediate` 之一(允许别名 `mysql` / `clickhouse`) |
| `field` | `failure_record_field` / `request_param` 类必填 | 对应故障记录字段名或请求 params 的键 |
| `table_name` | DB 类必填 | 含 schema 前缀(如 `datacenter.lo_batch_equipment_performance`、`las.LOG_EH_UNION_VIEW`) |
| `column_name` | DB 类必填 | 内网真实列名,大小写敏感(注意 `WS_pos_x` 是大写,不是 `ws_pos_x`) |
| `time_column` | DB 类必填 | 用于时间窗筛选(常用 `file_time` / `last_modify_date` / `wafer_product_start_time`) |
| `duration` | DB 类必填 | **单位:天**(整数字符串)。`Tx_history` 这类历史窗口通常 30,触发指标通常 7 |

### 1.2 可选但推荐

- `fallback.policy`:DB 类**强烈推荐**显式写 `nearest_in_window` 或 `none`(否则 `check_config.py` 会 warning)
- `role`:`trigger_only` 仅触发用不展示;`internal` 中间窗口列表不展示;默认 `diagnostic` 进入接口 3 metrics 列表
- `unit`:展示给前端,纯描述
- `_note`:任何后人需要知道的设计决策(如「按 stage4 业务清单切到此表」)

### 1.3 命名

- `metric_id` 用 **snake_case**,与现有风格一致(`Mwx_0`、`mark_pos_x`、`trigger_log_mwx_cgg6_range`)
- **触发用 metric** 名字以 `trigger_` 开头(惯例,便于一眼识别)
- **历史窗口 metric** 名字以 `_history` 结尾(惯例,便于一眼识别 `role: internal`)

### 1.4 容易踩坑

- ClickHouse `=` 比较时,String vs Int32 可能不命中 → `MetricFetcher` 已对 `=`/`!=` 包了 `toString(...)`,但仍建议 `linking.keys` 类型尽量对齐内网真实
- `linking.keys` 中 `source` 解析为 `null` 时,该次查询直接返回空集(不报错,**静默失败**),所以 source 必须是真存在于上下文的字段名(如 `equipment` / `chuck_id` / `lot_id` / `wafer_index` / `wafer_id`)
- `extraction_rule` 用 `regex:` 时:**有捕获组** → 取第 1 组;**无捕获组** → 匹配成功 = `True`。混用时配置语义会颠倒
- `extraction_rule` 用 `jsonpath:` 时,路径中**纯数字段**表示数组下标;`{var}` 占位符会被上下文渲染。**注意当前 fetcher 实现对 `name[N]` 形式的兼容性,见 [`docs/intranet/databases/mysql_datacenter.md`](intranet/databases/mysql_datacenter.md) §mc_config_commits_history「已知 issue」**

---

## 2. `diagnosis_scenes`(场景触发)

### 2.1 必填

- `id`:全局唯一(数字或字符串)
- `start_node`:**必须**等于 `steps` 中某个 `id`(`check_config.py` 会校验)
- `metric_id`:数组,场景**预取**的指标 id 列表
- `trigger_condition`:数组,**任一条**为真就命中场景(条目之间是 OR)

### 2.2 评审重点

- **场景之间互斥**:`diagnosis_scenes` 数组按顺序匹配,**第一个命中**就走那条;后续场景不再尝试。如果你想用「兜底场景」,**必须放数组最后一项**且配 `default: true`
- `trigger_condition[i]` 表达式中的 `{var}` **必须**全部出现在本场景的 `metric_id` 数组里(否则 `rule_validator` 报错)
- 多个场景共用同一 `start_node` → `check_config.py` warning(可能配置冗余)

---

## 3. `steps`(决策树)

### 3.1 必填 / 可选

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 全局唯一 |
| `description` | 推荐 | 评审时描述「这一节点在排查什么」 |
| `metric_id` | 视 step 类型 | 该 step 关联的主指标(condition 里 `{var}` 不显式时的回退) |
| `details` | 视 step 类型 | 顺序执行的 action 列表;每项含 `action` / `params` / `results` / `result` |
| `next` | 非叶子 step 必填 | 分支列表;每个分支含 `target` + `condition` |
| `result` 或 `details[].result` | 叶子 step | 包含 `rootCause` + `system` |

### 3.2 分支(`next[]`)评审

- **互斥性**:同一 step 下多个非 `else` 分支应**业务互斥**(只命中一条)。`rule_validator` 会做语法校验,但**业务互斥**靠人评审
- **兜底**:最后一条 `condition: "else"` 是兜底分支;若无 `else` 且所有分支不命中,诊断中断(warning 级日志)
- **回路**:`target` 指回较早 step.id 形成回路,引擎用 `max_steps=50` 防死循环——如果业务允许循环 N 次,**用 `set` 注入计数器**(如 `set: {"attempts": 1}`)+ 在 `next.condition` 里检查
- **并行**:`target` 为数组(如 `[22, 23, 24]`)表示「依次执行子树并取首个有结论者」,**不是真并行**

### 3.3 action 评审

- `action` 名必须**已注册**(`rule_validator` 会校验);如果是新 action,先在 [`src/backend/app/engine/actions/`](../src/backend/app/engine/actions/) 里加 `@register("name")` 装饰器
- `params` 绑定规则:
  - 字面量:`"chuck_id": 1` → 直接传 1
  - 显式占位符:`"Tx": "{Tx_history}"` → 从 ctx 取 `Tx_history`
  - 空字符串/null:`"Tx": ""` → 从 ctx 取同名 key `Tx`
- `results` 是**契约声明**:声明的 key 应当真的被 action 写回 context(否则警告);action 输出多余 key 会全部进 ctx

### 3.4 叶子 step 文案

- `rootCause` 直接展示给前端,**用业务语言**(如「上片工艺适应性问题」「需要人工处理」),不要用代码术语
- `system` 是责任分系统,可为 `null`(引擎会自动赋「待确认」)

---

## 4. CONFIG_DRIVEN 完整性(避免「配置错却要改代码」)

每次评审问自己一遍:

- [ ] 这次改动是否**只修改了 JSON**,没动 Python?如果动了 Python,是不是「新 action」「修 bug」「新 source_kind」这种**正当**理由?
- [ ] 新增 metric 时,是否同步更新了 [`docs/intranet/databases/`](intranet/databases/) 对应表的「诊断引擎引用」段?
- [ ] 新增叶子 `rootCause` 时,是否在 [`docs/data_source.md`](data_source.md) 或对应业务文档里有迹可循?
- [ ] 是否考虑了**生产环境**:`duration` 是否合理(过长会扫整张表)?`linking.keys` 是否走索引?

---

## 5. 数据真实性(本地 mock vs 内网真实)

- [ ] 新指标如有 mock 需求,在 [`scripts/init_docker_db.sql`](../scripts/init_docker_db.sql) 或 [`scripts/init_clickhouse_local.sql`](../scripts/init_clickhouse_local.sql) 加 INSERT,**与锚点对齐**(见 [`docs/intranet/databases/README.md`](intranet/databases/README.md) §2.3)
- [ ] 内网真实表的列定义已更新到 [`docs/intranet/databases/{db}.md`](intranet/databases/) 对应小节
- [ ] 已知不一致(列名大小写、类型、可能不存在的列)在文档 ⚠ 段标注

---

## 6. 测试

- [ ] 跑 `python scripts/check_config.py` exit code = 0
- [ ] 跑 `python -m pytest src/backend/tests/test_rule_validator_metric.py src/backend/tests/test_rules_validator.py src/backend/tests/test_diagnosis_config_store.py -v` 全过
- [ ] 如果改了规则路径(scenes/steps),跑 `python -m pytest src/backend/tests/test_rules_engine_conditions.py -v` 验证决策树仍按预期走
- [ ] 如果是大改,本地起 docker 跑接口 3 详情页 1 次,看 `metrics_data` 是否符合预期

---

## 7. 文档同步

- [ ] [`config/CONFIG_GUIDE.md`](../config/CONFIG_GUIDE.md) 字段说明仍准确
- [ ] [`docs/stage3/rules_execution_spec.md`](stage3/rules_execution_spec.md) 执行契约仍准确
- [ ] 如果是 stage4 主线工作,[`docs/stage4/`](stage4/) 对应文档已同步
- [ ] PR 描述里写明「本次改了哪些 metric / scene / step,业务影响是什么」

---

## 8. 评审者:常见拒绝理由

直接打回 PR 的情况:

- `python scripts/check_config.py` 报 error(JSON 格式错、source_kind 非法、变量未声明等)
- 新增 action 名称在 `engine/actions/` 找不到注册
- 改了配置但**没说明业务背景**(评审者无法判断对错)
- 新增 metric 但**没改 docs/intranet/databases/** 对应表
- 删了 metric 但**有 step 在引用**(`check_config.py` 的硬校验会抓)
- 改了 PRD3 接口字段但**前端 [`src/frontend/src/pages/FaultRecords.jsx`](../src/frontend/src/pages/FaultRecords.jsx) 没同步**

可以条件 approve(留 follow-up):

- `check_config.py` 有 warning 但 error 为 0(orphan metric / 缺 fallback.policy 等)
- 文档同步有遗漏(让作者补上即可)
- 新指标已建表但内网 DDL 还在确认中(标注 `_note` 即可)
