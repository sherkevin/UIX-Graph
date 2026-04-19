# `config/reject_errors.diagnosis.json` 字段说明

本文档只说明该 JSON 里**每个字段的含义、取值约定与运行时行为**，便于开发与评审对照配置。更完整的编写流程与示例见 `config/CONFIG_GUIDE.md`。

---

## 1. 根对象

| 字段 | 类型 | 含义 |
|------|------|------|
| `version` | 字符串 | 配置格式主版本。当前工程约定为 `3.x.x`；加载与校验以 major=3 为准。 |
| `metrics` | 对象 | 指标字典：**键**为指标 ID（如 `Mwx_0`、`output_Mw`），**值**为该指标的元数据与取数配置。键名在全文（含 `diagnosis_scenes`、`steps`、条件表达式 `{变量名}`）中必须一致。 |
| `diagnosis_scenes` | 数组 | 诊断场景列表：何时命中场景、需要预取哪些触发用指标、从哪个 step 开始。 |
| `steps` | 数组 | 决策树节点列表：每个元素一步，含可选 action、分支 `next`、或叶子结论。 |

---

## 2. `metrics` 中单个指标对象

指标 ID（外层键）由你命名，建议稳定、可读、与业务含义一致（如蛇形与现有配置一致）。

### 2.1 通用字段

| 字段 | 类型 | 含义与行为 |
|------|------|------------|
| `description` | 字符串 | 人类可读说明，不参与执行逻辑。 |
| `data_type` | 字符串或 null | 可选语义类型提示（如 `int`）。取数与计算仍以运行时实际值为准。 |
| `unit` | 字符串或 null | 展示用单位；进入接口返回的 `metrics[].unit`。 |
| `source_kind` | 字符串 | **决定取数路径**：`failure_record_field`（故障记录字段）、`clickhouse_window`（ClickHouse 时间窗）、`mysql_nearest_row`（MySQL 时间窗）、`intermediate`（不由 MetricFetcher 查库，由 action 或上下文填充）。未知类型会记录告警并难以取到值。 |
| `role` | 字符串 | **展示与汇总**：`config_store` 默认会设为 `diagnostic`。`trigger_only`、`internal` 在构建详情 `metrics` 列表时会被**排除**（不展示给前端）。 |
| `approximate` | 布尔 | 可选。为 true 时原样透出到接口 `metrics[].approximate`，表示该值近似/仅供参考（如建模输出的 `output_Tx` 等）。 |
| `enabled` | 布尔 | 若为 `false`，MetricFetcher 对该指标**跳过取数**（用于占位或未启用指标，如「动态上片偏差」）。 |
| `_note` | 字符串 | 仅作文档/迁移备注，运行时忽略。 |

### 2.2 `source_kind: failure_record_field`

| 字段 | 类型 | 含义 |
|------|------|------|
| `field` | 字符串 | 从故障主记录（`source_record`）读取的字段名，如 `reject_reason`、`wafer_translation_x`。 |
| `transform` | 对象 | 可选。对读出的原始值做变换后再作为指标值（见下文 **transform**）。 |

### 2.3 `source_kind: clickhouse_window` / `mysql_nearest_row`

二者均按**时间窗口**查库；窗口长度见 `duration`。查询结果在多数情况下为**窗口内多行对应值的列表**（或经提取规则处理后的列表）；是否再聚合成标量由后续 **action** 或 **select_window_metric** 等逻辑决定。

| 字段 | 类型 | 含义与行为 |
|------|------|------------|
| `table_name` | 字符串 | 库表名。ClickHouse 常写 `库.表`（如 `las.LOG_EH_UNION_VIEW`）；MySQL 常写 `库.表`（如 `datacenter.mc_config_commits_history`）。 |
| `column_name` | 字符串 | 要读取的列名（如日志 `detail`、配置 JSON `data`）。 |
| `time_column` | 字符串 | 时间列，用于与基准时间 `T`（一般为 `wafer_product_start_time`）构造 `[T - duration, T]` 窗口。 |
| `equipment_column` | 字符串 | 设备列名，默认行为里常用于设备过滤；具体是否加入 WHERE 与 `mysql_omit_equipment_filter` 等有关。 |
| `duration` | 字符串或数字 | **窗口长度，单位为天**（不是分钟）。未配置时可能回退到 fetcher 的默认天数。 |
| `extraction_rule` | 字符串 | 对单元格原始内容做提取；见下文 **extraction_rule**。空字符串表示不做规则提取，按标量规范化处理。 |
| `linking` | 对象 | 精确键与额外过滤，见下文 **linking**。 |
| `fallback` | 对象 | 约定形如 `{ "policy": "nearest_in_window" }`。配置与测试中会保留该字段；当前 `MetricFetcher` 取数路径**未读取** `fallback.policy`（窗口内如何排序/选行由 ODS 层 `query_metric_in_window` 等与 `linking` 共同决定）。保留该字段便于与业务口径对齐及后续扩展。 |
| `mysql_omit_equipment_filter` | 布尔 | 仅 MySQL 路径：为 true 时**省略**基于 `equipment_column` 的自动设备过滤（适用于用 `linking.filters` 里 `env_id contains equipment` 等替代的场景）。 |
| `filter_condition` | 任意 | 可选。MySQL 侧额外过滤片段（若使用）；当前 `reject_errors.diagnosis.json` 未使用，保留为扩展。 |

### 2.4 `source_kind: intermediate`

| 字段 | 类型 | 含义 |
|------|------|------|
| （无查库字段） | — | 指标值来自 **action 写入的 context** 或与 `metrics` 同名的占位；Fetcher 对 `intermediate` **不查库**。需在 `steps` 的 `details` 里通过 `results` 或等价逻辑产出，否则值为空。 |

### 2.5 `transform`（多用于 `failure_record_field`）

在 `metric_fetcher._apply_transform` 中支持：

| `type` | 含义 |
|--------|------|
| `equals` | 返回值是否等于 `value`（常用于得到布尔触发量）。 |
| `not_equals` | 不等于 `value`。 |
| `float` / `int` / `bool` | 类型转换（按实现转换后返回）。 |
| `upper_equals` / `lower_equals` | 字符串大小写不敏感比较。 |
| `contains` | `value` 是否为字符串值的子串。 |
| `map` | 用 `mapping` 字典做枚举映射。 |

未知 `type` 会打日志并**保留原值**。

### 2.6 `linking`

| 字段 | 类型 | 含义 |
|------|------|------|
| `mode` | 字符串 | `time_window_only`：仅时间窗 + `filters`（以及库侧设备条件等），**不**把 `keys` 当作必填等值条件拼进 SQL；`exact_keys`：除时间窗外，还必须为 `keys` 中每一项生成等值条件；若某条 `source` 在上下文中解析为 `null`，则视为**缺少必填键**，该次查询可能直接返回空/不查。 |
| `keys` | 数组 | 元素为 `{ "target": "列名", "source": "上下文字段名" }`，语义为 `WHERE target = 解析后的 source 值`。`source` 从故障记录、`equipment`/`chuck_id`、请求 `params` 等合并后的上下文中取值（见 `MetricFetcher._resolve_context_value`）。**注意**：业务字段名需与源表一致（如源表为 `wafer_id` 而记录里是 `wafer_index`，须在数据层或字段命名上对齐）。 |
| `filters` | 数组 | 固定或引用型过滤条件，与 `keys` 一样经 `_build_linking_clauses` 转成 SQL 片段。 |

**`filters` / `keys` 单项写法（`operator` 缺省为 `=` 或 `==`，二者在生成 SQL 时按实现统一）**：

| 用法 | 示例 | 生成语义（简述） |
|------|------|------------------|
| 常量等值 | `{ "target": "phase", "value": "1ST_COWA" }` | `phase = '1ST_COWA'` |
| 引用上下文 | `{ "target": "env_id", "operator": "contains", "source": "equipment" }` | MySQL：`INSTR(CAST(env_id AS CHAR), CAST(? AS CHAR)) > 0`；ClickHouse：`positionUTF8(toString(env_id), toString(?)) > 0` |
| 列表包含 | `{ "target": "col", "operator": "in", "value": ["a","b"] }` 或 `source` 解析为列表 | `col IN (...)`（ClickHouse 侧可能对元素做 `toString`） |

**ClickHouse 注意**：对 `=` / `!=`，实现里可能对列与参数统一 `toString(...)` 比较，以缓解本地/内网 String 与数值类型不一致问题。

### 2.6.1 `extraction_rule` 中 `jsonpath:` 的占位符

路径模板里可写 `{名称}`，名称在取数时由 `_resolve_context_value` 解析。除故障记录、`params` 中的字段外，内置/派生包括：`equipment`、`chuck_id`、`time_filter`、`reference_time`；若 `chuck_id` 可转为数字，还会提供 **`chuck_index0` = `int(chuck_id) - 1`**（用于 `chuck_message` 下标等场景）。

### 2.7 `extraction_rule`

字符串前缀决定解析方式（`metric_fetcher._apply_extraction_rule`）：

| 前缀 | 含义 |
|------|------|
| `regex:` | 后接正则。若有捕获组，取**第一组**为指标值；若无捕获组且匹配成功，返回 **true**（布尔）；未匹配时返回 **false**。 |
| `json:` | `json:` 后为顶层键名；先将 `raw` 解析为 JSON，再 `data[key]`。 |
| `jsonpath:` | `jsonpath:` 后为路径模板，以 `/` 分段；支持 `{占位符}`，解析规则见 **2.6.1**。路径中纯数字段表示 JSON 数组下标。解析失败或占位符无法解析返回 null。 |
| （其它或空） | 空则对 `raw` 做标量规范化；非空且无前缀则按实现回退为标量提取。 |

---

## 3. `diagnosis_scenes[]` 场景对象

| 字段 | 类型 | 含义与约束 |
|------|------|------------|
| `id` | 数字或字符串 | 场景唯一标识；写入诊断结果的 `sceneId`。 |
| `module` | 字符串 | 模块名（如 `COWA`），用于展示/分类。 |
| `phenomenon` | 字符串 | 现象简述（如「倍率超限」）。 |
| `description` | 字符串 | 更长说明。 |
| `metric_id` | 字符串数组 | **场景级需要预取的指标 ID**。须**覆盖** `trigger_condition` 中出现的所有 `{变量}`，否则静态校验或运行时会缺少变量。 |
| `trigger_condition` | 字符串数组 | 见下 **3.1**。 |
| `start_node` | 字符串或数字 | 命中场景后进入的 **step id**（须存在于 `steps`）。 |
| `default` | 布尔 | 可选。若为真且**没有** `metric_id` 与 `trigger_condition`，则作为默认场景直接命中（与其它 pipeline 的通用入口一致；`reject_errors` 当前可不用）。 |

### 3.1 场景如何被命中（与 `trigger_condition` 数组的关系）

引擎按 `diagnosis_scenes` **数组顺序**依次尝试；**第一个**被判定命中的场景即采用，后续场景不再看。

对单个场景：

- 若 **`trigger_condition` 为空** 且配置了 `metric_id`：当**所有**预取指标值在 Python 意义下均为“真”（`all(trigger_values.get(mid) for mid in trigger_metric_ids)`）时命中。
- 若 **`trigger_condition` 非空**（可为多条字符串）：对数组 **从上到下** 逐条求值；**任意一条**表达式为真即**命中该场景并立即返回**（条目之间是 **OR** 关系）。
- **单条**表达式字符串内部仍可用 `AND` / `OR` 等，由 `condition_evaluator` 解析（条目内部可有复合条件）。

若未配置 `trigger_condition` 但配置了 `metric_id`，且你希望“条件 A 与条件 B 同时成立”，应写**一条**表达式，例如 `{a} == true AND {b} == true`，而不要拆成两条数组元素（否则会变成 A 或 B）。

---

## 4. `steps[]` 步骤对象

| 字段 | 类型 | 含义 |
|------|------|------|
| `id` | 字符串或数字 | 节点唯一 ID；`next.target` 指向此处。 |
| `description` | 字符串 | 步骤说明。 |
| `metric_id` | 字符串或数组 | 可选。本步主要关联的指标 ID；分支求值时若条件未写 `{var}`，引擎可能按此默认变量解析（见 `diagnosis_engine._evaluate_branches`）。 |
| `details` | 数组 | 可选。顺序执行的一组子动作（仅 `action` 非空项会调用 `call_action`）。 |
| `next` | 数组 | 分支列表；见下文 **next**。无元素或空且非叶子则路径结束。 |
| `params` | 对象 | **旧格式**兼容：建模参数可挂在 step 上；新格式优先放在 `details[0].params`（`rule_loader.get_step_params` 二者择一）。 |

### 4.1 叶子结论（根因 / 分系统）

引擎通过 `rule_loader.get_step_result` 取叶子结果，兼容：

1. **旧格式**：`step.result` 对象，含 `rootCause`、`system` 等。
2. **新格式**：`step.details[0].result` 对象；或 `step.details[0].results` 中含 **`rootCause` 键**（如节点 99），则整份 `results` 当作叶子结果。

叶子键常见含义：

| 键 | 含义 |
|----|------|
| `rootCause` | 根因文案；写入诊断结果 `rootCause`。 |
| `system` | 责任分系统；可为 `null`，引擎可能对部分根因默认「待确认」。 |
| `mean_Tx` / `mean_Ty` / `mean_Rw` 等 | 可与 `rootCause` 同传，用于展示；具体是否进入返回体由服务层与模板字段决定。 |

### 4.2 `details[]` 子项

| 字段 | 类型 | 含义 |
|------|------|------|
| `action` | 字符串或 null | 注册的 action 名（如 `build_88um_model`）。为 `null` 或省略时不执行调用。 |
| `description` | 字符串 | 子步骤说明。 |
| `params` | 对象或 null | 传入 `call_action` 的参数表。值可为字面量，或 `"{metric_id}"` 形式从 **context** 取值（与引擎解析一致）。 |
| `results` | 对象 | **契约声明**：action 应写回的键名；若声明了键但 action 输出缺少，会打警告。声明为空或不声明时，action 输出仍可能全部合并进 context（见 `_normalize_action_outputs`）。 |
| `result` | 对象 | 若本步为叶子且使用嵌套格式，此处放 `rootCause` / `system` 等（见 4.1）。 |

### 4.3 `next[]` 分支项

| 字段 | 类型 | 含义 |
|------|------|------|
| `target` | 字符串、数字或数组 | 下一 step id；**数组**表示多目标，见下 **4.4**。 |
| `condition` | 字符串或结构化对象 | 为真则走该分支。字符串支持比较、区间、`AND`/`OR`、与 `condition_evaluator` 一致的结构化条件对象等。`condition` 为 **`else`**、**空字符串**或 **null** 时视为兜底分支（与 `rule_validator` 约定一致，不再使用历史的 `operator`/`limit`）。 |
| `set` | 对象 | 可选。命中该分支时向 context **注入**键值（如 `model_type: "88um"`），**在选定 `target` 之后、进入下一步之前**写入。 |
| `results` | 对象 | **旧格式**分支输出声明；`get_all_scene_metric_ids` 仍会收集其中的键作为场景涉及指标。新配置多在 `details[].results` 声明。 |

### 4.4 `target` 为数组（多子树）

当 `target` 为列表时，引擎对**每个**子节点 id **依次**调用 `_walk_subtree`：

- **共享同一份 `context`**（前序步骤写入的变量、分支 `set` 注入等均保留）。
- 每个子树的 `trace` 会 **extend** 到总路径上（子树内部从空 trace 开始，再拼到父路径后）。
- **第一个**返回了非空 `rootCause` 或 `system` 的子树结果会被采纳；若全部子树都无结论，则整段返回无根因。

因此数组 **不是**多线程并行，而是**顺序执行、先产出结论者优先**。

### 4.5 分支冲突与兜底

`_evaluate_branches` 约定：非 `else` 的分支中，**应恰好命中一条**。若同一 step 下**多条**条件同时为真，则视为配置冲突：记错误日志；若存在 `else` 分支，则**走 `else` 的 `target`**；若无 `else`，则该步无法选路，诊断中断。

---

## 5. 与运行时的简短对应（便于理解字段落点）

- **变量从哪来**：`metrics` + Fetcher；**场景是否开始**：`diagnosis_scenes`；**怎么走树**：`steps` + `next`；**中间计算**：`details[].action`；**最终话术**：叶子上的 `result` / `details[0].result` / 含 `rootCause` 的 `results`。
- **防死循环**：单条路径在 `_walk_subtree` 内最多推进 **50** 步（`max_steps`），超限则停止，避免配置错误导致无限循环。

条件表达式中的指标/上下文变量须写成 **`{变量名}`**（与 `rule_validator`、静态校验对变量名的抽取规则一致）。

---

## 6. 与专家访谈台账的对应（字段不进 JSON）

专家侧台账（见 `docs/stage4/diagnosis-path-template.md` **§7.4、§7.4.1**）中部分列**不落** `reject_errors.diagnosis.json`，但与落 JSON 的列配套使用，评审约定如下：

- **所属模块或分系统**：按 **每个 step**（含中间节点与叶子）填写；JSON 里叶子结论的 `system` 仍以叶子 `result` / `results` 定稿为准（见 §4.1），中间节点的归属留在台账供对照。
- **在哪看**：专家枚举 **`las` / `sedc` / `其他`** 三选一；不写入 `metrics` / `steps` 的某个固定字段。
- **看什么**：建议以**截图或链接**为主证据，再配文字；开发将「看什么」翻译为 `table_name` / `column_name` / `extraction_rule` 等（见 `CONFIG_GUIDE`）。
- **是否回到前面**、**重复次数**：描述业务回路口径；配置侧用 `next[].target` 指回较早 `step.id`，引擎以 `max_steps` 防死循环（见 §5），**重复次数**用于评审与业务上限对齐。

修改本文件后建议按 `config/CONFIG_GUIDE.md` 运行规则校验与相关 pytest。
