# 故障诊断路径统一台账与分角色表单模板

本文档给出一套团队落地使用的模板表，目标同时满足：

- `统一`：最终保留一份全量主台账，填写完成后其中每一列都能**直接**翻译为 `config/<pipeline>.diagnosis.json` 中的 JSON 字段（是一份“可直接落 JSON 的中间层”），避免二次翻译
- `分离`：再给两张分角色视图，访谈专家时只看专家访谈表，线下补齐技术细节只看开发补全表
- `对齐`：模板中只出现 `DiagnosisConfigStore / rule_validator / DiagnosisEngine` 真实识别的概念，不再引入引擎并不存在的抽象（如 `loop_gate`、`父节点`）

配套阅读：`config/CONFIG_GUIDE.md`（字段权威说明）、`src/backend/app/engine/rule_validator.py`（静态校验实现）。

## 1. 为什么要这样收敛

### 1.1 运行时权威只有一份

当前引擎运行时只读两层：

1. `config/diagnosis.json`（pipeline 索引）
2. `config/<pipeline>.diagnosis.json`（pipeline 内的 `metrics / diagnosis_scenes / steps`）

所以模板存在的唯一意义，是把「专家口中的故障排查路径」结构化地转成上面这两个文件里 `metrics / diagnosis_scenes / steps` 的条目。模板任意一列若无法对齐到这两个文件里的一个字段，就不应该出现在开发视图里，只能作为专家视图里的“业务辅助信息”。

### 1.2 现在的主要问题

之前模板混入了几个和引擎不对齐的概念，这次一并清理：

- `节点类型 trigger / loop_gate` 等不在引擎里存在，引擎里的 `step` 只有三种形态：`含 details 的计算步`、`只做分支的判断步`、`带 result 的叶子步`
- `父节点ID列表`、`连线表` 不是 JSON 字段，属于反查辅助，不参与落 JSON
- `分支类型 loop_back / parallel` 在 JSON 里不是独立字段，而是通过 `target` 为数组或 `target` 指回较早的 `step.id` 自然表达
- 场景入口信息不完整，之前只问了「现象 / 模块 / 适用机型」，没有问 `trigger_condition`、`start_node`、`metric_id 列表`、`default` 这些 JSON 必需项

## 2. 最终的文件结构

三张“小表”构成一张“全量主台账”，分别对应 JSON 的三大块：

| 台账表 | 一行 = | 对应 JSON 块 |
| --- | --- | --- |
| `SCENES 台账` | 一条场景 | `diagnosis_scenes[]` 中一项 |
| `STEPS 台账`  | 一个节点 | `steps[]` 中一项（含 `details` 与 `next`，用子行表达分支） |
| `METRICS 台账` | 一个指标 id | `metrics` 字典中一个 key |

再给两张“分角色子表”，它们只是上面三表的列投影，字段由双方约定好：

| 角色视图 | 由哪些表投影而来 |
| --- | --- |
| `专家访谈表` | `SCENES 台账` + `STEPS 台账` 的专家可回答列 |
| `开发补全表` | `METRICS 台账` 全部列 + `SCENES / STEPS 台账` 的技术补全列 |

三表统一主键：

- `scene_id`：场景编号，直接写入 `diagnosis_scenes[].id`
- `step_id`：节点 id，直接写入 `steps[].id`
- `metric_id`：指标 id，直接写入 `metrics` 字典的 key

## 3. 粒度与分支表达

### 3.1 粒度

- `SCENES 台账` 粒度：一条场景一行
- `STEPS 台账` 粒度：一个节点一行；如果该节点有多个 `next` 分支，用多行子分支补充，父子行共享 `step_id`
- `METRICS 台账` 粒度：一个 `metric_id` 一行

### 3.2 分支如何表达

引擎里的 `step.next` 每一项就是一个分支，字段是 `target / condition / set / results`。所以分支表达直接落在 `STEPS 台账` 的“分支子行”上，不再自造 `分支类型` 枚举：

| 业务常见说法 | 用引擎真实字段的落法 |
| --- | --- |
| “条件满足时去 N023” | `target=N023`，`condition=expr` |
| “同时启动多条路径” | `target=[N023,N024,N025]`，`condition=expr` |
| “走其他情况 / 兜底” | `condition=else`（此时 `target` 必填单一节点） |
| “回到某个前面的节点” | `target` 填指向较早的 `step.id`，`condition=expr` 自然形成回路 |
| “进入下一节点前写入中间变量” | 在该分支行的 `set` 列里写 `{"model_type":"88um"}` |
| “用 action 输出作为下一步变量” | 在该节点主行的 `results` 列里声明 `{"mean_Tx":""}` |

### 3.3 不再使用的字段

以下字段在本次模板中**不再出现**，它们不是 JSON 字段，也不是引擎概念：

- `节点类型: trigger / loop_gate`
- `分支类型: single / parallel / fallback / loop_back`
- `父节点ID列表`
- `是否叶子节点`（由是否有 `result` 决定，冗余）

判断一个节点是不是叶子，只看 `STEPS 台账` 的 `result` 列是否非空即可。

### 3.4 Excel / 飞书：STEPS 主行与子分支如何落表

表格工具没有“树形子行”类型时，用下面任一方式，**不要**把主行和分支混在同一行里写自然语言（否则无法 1:1 落 JSON）：

| 方式 | 做法 | 适用 |
| --- | --- | --- |
| **A. 同一张表，重复 `step_id`** | 主行：`step_id=1`，`branch_*` 全空；子行：`step_id=1`，`branch_index=1,2,3...`，只填 `branch_*` 列 | 分支数量少，一眼能看完 |
| **B. 独立 sheet「STEPS_BRANCHES」** | 主表只保留节点主行；分支表列：`step_id, branch_index, branch_condition, branch_target, branch_set, branch_intent` | 分支多、需要筛选/排序 |
| **C. 复合键列（可选）** | 增加一列 `step_branch_key`，形如 `1`（主行） / `1.1` `1.2`（子分支），方便 VLOOKUP | 团队习惯用键关联时 |

合并回 JSON 时：同一 `step_id` 的所有子行按 `branch_index` 排序，依次填入该 step 的 `next[]` 数组。

## 4. SCENES 台账（一行一条场景）

| 列名 | 落到 JSON 的字段 | 填写人 | 备注 |
| --- | --- | --- | --- |
| `scene_id` | `diagnosis_scenes[].id` | 开发 | 整数或字符串均可，全局唯一 |
| `module` | `diagnosis_scenes[].module` | 专家 | 业务模块名，如 `COWA` |
| `phenomenon` | `diagnosis_scenes[].phenomenon` | 专家 | 故障现象的业务短语，如“倍率超限” |
| `description` | `diagnosis_scenes[].description` | 专家+开发 | 对本场景的 1-2 句描述，可含处置方向 |
| `trigger_metric_ids` | `diagnosis_scenes[].metric_id`（数组） | 双方 | 仅列出「判断是否进入本场景」所需的 metric_id，不放展示用指标 |
| `trigger_condition` | `diagnosis_scenes[].trigger_condition`（数组，可单条） | 双方 | 表达式字符串，只能引用 `trigger_metric_ids` 里的变量，如 `"{a}==true AND {b}==true"` |
| `start_node` | `diagnosis_scenes[].start_node` | 开发 | 必须等于 `STEPS 台账` 里的某个 `step_id` |
| `is_default` | `diagnosis_scenes[].default`（布尔，可省略） | 开发 | `true` 表示该场景作为兜底；**只有将该场景放在 `diagnosis_scenes` 数组最后一项**时才等价于“所有其它场景都不命中时才走这里”，否则会把后续场景的机会吃掉 |
| `适用机台/机型` | 不落 JSON，仅备注 | 专家 | 引擎本身没有按机型选场景，机型限制通过 `trigger_metric_ids` 的字段条件间接实现 |
| `专家故障现象原话` | 不落 JSON，仅备注 | 专家 | 原始话术，供后续回溯 |
| `专家判断方式` | 不落 JSON，仅备注 | 专家 | 页面/脚本/日志/人工观察 |
| `当前状态` | 不落 JSON，仅备注 | 双方 | `待访谈 / 已访谈 / 待映射 / 已映射 / 已验证` |
| `资料来源` | 不落 JSON，仅备注 | 双方 | 会议纪要 / 截图 / 文档链接 |

### 4.1 一个 SCENES 台账的示例行

```text
scene_id            : 1001
module              : COWA
phenomenon          : 倍率超限
description         : COWA 倍率超限，补偿建模
trigger_metric_ids  : trigger_reject_reason_cowa_6, trigger_log_mwx_cgg6_range
trigger_condition   : "{trigger_reject_reason_cowa_6} == true AND {trigger_log_mwx_cgg6_range} == true"
start_node          : 1
is_default          : (空)
```

落成 JSON：

```json
"diagnosis_scenes": [
  {
    "id": 1001,
    "module": "COWA",
    "phenomenon": "倍率超限",
    "description": "COWA倍率超限，补偿建模",
    "metric_id": [
      "trigger_reject_reason_cowa_6",
      "trigger_log_mwx_cgg6_range"
    ],
    "trigger_condition": [
      "{trigger_reject_reason_cowa_6} == true AND {trigger_log_mwx_cgg6_range} == true"
    ],
    "start_node": "1"
  }
]
```

## 5. STEPS 台账（一行一个节点，多 next 分支拆子行）

### 5.1 主行列（节点本身）

| 列名 | 落到 JSON 的字段 | 填写人 | 备注 |
| --- | --- | --- | --- |
| `scene_id` | — | 双方 | 仅作归属索引 |
| `step_id` | `steps[].id` | 开发 | 整数或字符串均可，全局唯一；被 `start_node` 或 `next.target` 引用时必须存在 |
| `description` | `steps[].description` | 专家+开发 | 对这一节点在排查什么的一句话说明 |
| `step_metric_id` | `steps[].metric_id`（可选） | 开发 | 主输入指标；通常是窗口列表 id（如 `Tx_history`）或单值 |
| `details_actions` | `steps[].details[].action` 的集合 | 开发 | 每行一个 action；action 必须在 `src/backend/app/engine/actions/` 注册 |
| `details_params` | `steps[].details[].params` | 开发 | 参数绑定规则见 `CONFIG_GUIDE.md` 第 6 节 |
| `details_results` | `steps[].details[].results` | 开发 | 该 action 声明会写回 context 的字段名（右值通常留空字符串） |
| `leaf_result` | `steps[].result`（叶子节点专用） | 专家+开发 | 单结论：`{"rootCause": "...", "system": "..."}` |
| `leaf_results` | `steps[].results`（叶子节点多结论） | 专家+开发 | 允许多条子结论，结构与单结论相同，引擎会合并展示 |
| `所属模块或分系统` | 不落 JSON，仅备注 | 专家 | **每个节点**（中间节点与叶子）都填；用于责任归属与评审，不限于叶子（叶子结论里的 `system` 仍由开发从本列与业务口径定稿写入 JSON） |
| `专家判断口径` | 不落 JSON，仅备注 | 专家 | 在此节点业务上如何判断（阈值、是否异常） |
| `在哪看` | 不落 JSON，仅备注 | 专家 | **仅能**三选一：`las` / `sedc` / `其他`（见 §7.4.1）；选「其他」时在同一行备注里用一句话写清具体系统或入口 |
| `看什么` | 不落 JSON，仅备注 | 专家 | 具体看哪些界面区域、字段、日志关键字；**尽量附截图或截图链接**（见 §7.4.1） |
| `当前状态` | 不落 JSON，仅备注 | 双方 | `待访谈 / 已访谈 / 待映射 / 已映射 / 已验证` |

### 5.2 子分支行列（父行 `step_id` 对应 `next[]`）

| 列名 | 落到 JSON 的字段 | 填写人 | 备注 |
| --- | --- | --- | --- |
| `step_id` | 与父行保持一致 | — | 标识属于哪个节点 |
| `branch_index` | — | 开发 | 本节点内分支序号，只是阅读用 |
| `branch_condition` | `steps[].next[].condition` | 专家+开发 | 允许 `"{var} > 0"`、`"-20 < {x} < 20"`、`"{a} AND {b}"`、`"else"`；同一节点的多个分支应互斥 |
| `branch_target` | `steps[].next[].target` | 开发 | 单个节点 id 或节点 id 数组（表示并行） |
| `branch_set` | `steps[].next[].set`（可选） | 开发 | 进入下一节点前写入 context 的键值对，例如 `{"model_type": "88um"}` |
| `branch_results` | `steps[].next[].results`（可选） | 开发 | 若该分支会补充新的 context 字段，声明在此 |
| `branch_intent` | 不落 JSON，仅备注 | 专家 | 专家对该分支业务含义的原话 |
| `是否回到前面` | 不落 JSON，仅备注 | 专家 | 该分支业务上是否「回到更早的排查步骤」（与 `branch_target` 指回较早 `step_id` 对应）；无回路填「否」或留空 |
| `重复次数` | 不落 JSON，仅备注 | 专家 | 若存在回路：业务上允许重复几轮、或上限口径（如「最多 3 次」「直到某现象消失」）；无回路留空（见 §7.4.1） |

### 5.3 一个 STEPS 台账的示例（主行 + 两条子分支）

主行：

```text
scene_id         : 1001
step_id          : 1
description      : 判断 Mwx_0 并输出 model_type
step_metric_id   : Mwx_0
details_actions  : select_window_metric, determine_model_type
details_params   : [{"metric_name":"Mwx_0","values":"{Mwx_0}"}, null]
details_results  : [{"Mwx_0":""}, {"model_type":""}]
leaf_result      : (空)
leaf_results     : (空)
```

子分支（两行）：

```text
step_id=1 | branch_condition="{Mwx_0} > 1.0001"           | branch_target=10 | branch_set={"model_type":"88um"}
step_id=1 | branch_condition="else"                        | branch_target=99 | branch_set=(空)
```

对应 JSON：

```json
{
  "id": 1,
  "description": "判断 Mwx_0 并输出 model_type",
  "metric_id": "Mwx_0",
  "details": [
    {
      "action": "select_window_metric",
      "params": {"metric_name": "Mwx_0", "values": "{Mwx_0}"},
      "results": {"Mwx_0": ""}
    },
    {
      "action": "determine_model_type",
      "params": null,
      "results": {"model_type": ""}
    }
  ],
  "next": [
    {"target": "10", "condition": "{Mwx_0} > 1.0001", "set": {"model_type": "88um"}},
    {"target": "99", "condition": "else"}
  ]
}
```

### 5.4 叶子节点写法

叶子节点没有 `next`，只有 `result` 或 `results`：

```json
{
  "id": 101,
  "description": "上片旋转机械超限（推断根因）",
  "result": {"rootCause": "上片旋转机械超限", "system": "机械精度"}
}
```

对应台账：`step_id=101`、`leaf_result={"rootCause":"...","system":"..."}`、`next` 子分支行一行都不写。

## 6. METRICS 台账（一行一个指标 id）

| 列名 | 落到 JSON 的字段 | 填写人 | 备注 |
| --- | --- | --- | --- |
| `metric_id` | `metrics` 的 key | 开发 | snake_case，全局唯一 |
| `description` | `metrics[x].description` | 专家+开发 | 业务说明 |
| `unit` | `metrics[x].unit` | 专家 | 单位，如 `um / ppm / urad` |
| `data_type` | `metrics[x].data_type` | 开发 | `int / float / bool / str`，可留 null |
| `source_kind` | `metrics[x].source_kind` | 开发 | 只能是：`failure_record_field / request_param / mysql_nearest_row / clickhouse_window / intermediate` |
| `role` | `metrics[x].role` | 开发 | 只能是：`diagnostic / trigger_only / internal`；未填按 `diagnostic` |
| `field` | `metrics[x].field` | 开发 | 仅 `failure_record_field / request_param` 用，源记录/请求参数里的键名 |
| `transform` | `metrics[x].transform` | 开发 | 仅直接取值类型需要，形如 `{"type":"equals","value":6}` |
| `table_name` | `metrics[x].table_name` | 开发 | 仅 DB 类型使用，ClickHouse 写完整库表名 |
| `column_name` | `metrics[x].column_name` | 开发 | 仅 DB 类型使用 |
| `time_column` | `metrics[x].time_column` | 开发 | 时间列名 |
| `equipment_column` | `metrics[x].equipment_column` | 开发 | 设备列名（DB 类通常要填） |
| `duration_days` | `metrics[x].duration` | 开发 | 窗口天数，字符串或数字皆可，单位**天**，常用 `7` 或 `30` |
| `linking_mode` | `metrics[x].linking.mode` | 开发 | `time_window_only` 或 `exact_keys` |
| `linking_keys` | `metrics[x].linking.keys` | 开发 | 数组，每项 `{target, source, operator?}`；仅当 `linking_mode=exact_keys` |
| `linking_filters` | `metrics[x].linking.filters` | 开发 | 固定 filter，例如 `{"target":"phase","value":"1ST_COWA"}` |
| `extraction_rule` | `metrics[x].extraction_rule` | 开发 | `regex:...` 或 `jsonpath:...` |
| `fallback_policy` | `metrics[x].fallback.policy` | 开发 | 当前常用 `nearest_in_window`；未填等价于 `none` |
| `enabled` | `metrics[x].enabled` | 开发 | `false` 表示保留字段但不参与取数；默认 true，不需要填 |
| `approximate` | `metrics[x].approximate` | 开发 | 建模产物类指标可用，提示前端该值为近似 |
| `mysql_omit_equipment_filter` | `metrics[x].mysql_omit_equipment_filter` | 开发 | 专门给 `mysql_nearest_row` 绕过 equipment 硬过滤；仅业务确认可用时才开 |
| `在哪看` | 不落 JSON，仅备注 | 专家 | 与 STEPS 主行相同枚举：`las` / `sedc` / `其他`（见 §7.4.1） |
| `看什么` | 不落 JSON，仅备注 | 专家 | 该指标对应界面/导出/脚本的查看位置；**尽量附截图**（见 §7.4.1） |
| `业务字段原名` | 不落 JSON，仅备注 | 专家 | 专家习惯叫法，便于后续沟通 |
| `mock 方案` | 不落 JSON，仅备注 | 开发 | 本地如何模拟该指标，例如 mock 表行、mock 函数 |
| `当前状态` | 不落 JSON，仅备注 | 双方 | `待访谈 / 已访谈 / 待映射 / 已映射 / 已验证` |

### 6.1 METRICS 台账的示例行

```text
metric_id           : Mwx_0
description         : 倍率实测值
unit                : ppm
data_type           : (空)
source_kind         : clickhouse_window
role                : (空，默认 diagnostic)
table_name          : las.LOG_EH_UNION_VIEW
column_name         : detail
time_column         : file_time
duration_days       : 7
linking_mode        : time_window_only
linking_keys        : []
linking_filters     : []
extraction_rule     : regex:Mwx\s*\(\s*([\d\.]+)\s*\)
fallback_policy     : nearest_in_window
```

对应 JSON：

```json
"metrics": {
  "Mwx_0": {
    "description": "倍率实测值",
    "unit": "ppm",
    "source_kind": "clickhouse_window",
    "linking": {"mode": "time_window_only", "keys": [], "filters": []},
    "fallback": {"policy": "nearest_in_window"},
    "table_name": "las.LOG_EH_UNION_VIEW",
    "column_name": "detail",
    "time_column": "file_time",
    "extraction_rule": "regex:Mwx\\s*\\(\\s*([\\d\\.]+)\\s*\\)",
    "duration": "7"
  }
}
```

### 6.2 关于字段可见性

- `role = trigger_only`：只参与场景触发，不在详情页展示
- `role = internal`：窗口原始列表（如 `Tx_history`），仅作为 action 的输入，不单独展示
- `role = diagnostic`（默认）：会被引擎按节点推送到前端详情

## 7. 专家访谈与开发补全（分角色视图）

本节解决三件事：**专家与开发各填哪些列**、**业务话如何翻译成 config 字段**、**访谈时按什么顺序问**。

### 7.1 专家列与开发列：严禁混用同一单元格

| 视图 | 允许出现的内容 | 禁止出现的内容 |
| --- | --- | --- |
| **专家可见列** | 自然语言：现象、页面路径、菜单名、日志里出现的原文、阈值口语（“偏高”“在范围内”）、分支业务意图 | `source_kind`、`table_name`、`{var}` 表达式、`regex:`、`jsonpath:`、`action` 名、`target` step id、JSON 片段 |
| **开发补全列** | 引擎表达式、`metric_id`、表/列/时间窗、`details.params`、分支 `condition` 的技术形式 | 把专家原话直接粘进 `trigger_condition` 而不翻译 |

同一概念**拆两列**：例如 `branch_intent`（专家，中文）与 `branch_condition`（开发，引擎表达式），**不要**在专家列里写一半中文一半 `{Mwx_0}`。

### 7.2 业务语言 → 引擎字段（Gap 消除翻译表）

专家不会说 `source_kind`，但会说“在哪个界面点哪里、看到什么”。开发按下表把话术落到 METRICS / SCENES / STEPS。  
（字段细则以 `config/CONFIG_GUIDE.md` 为准。）

| 专家常见说法 | 开发应落地的位置 | 典型 `source_kind` 或结构 |
| --- | --- | --- |
| “拒片列表里这一列是拒片原因，等于某数字就是某类故障” | `METRICS`：`field` + `transform`；`SCENES.metric_id` + `trigger_condition` | `failure_record_field` |
| “接口/诊断请求里会传一个参数给我们” | `METRICS`：`field`；`ontology_api` 等 pipeline | `request_param` |
| “在日志/历史记录里搜某段英文或中文，出现了就算命中” | `METRICS`：`table_name` + `column_name` + `extraction_rule: regex:子串` 或 `regex:...` 捕获数值 | `clickhouse_window` |
| “从配置/参数库里按机台、chuck 取最近一条 JSON，再读里面某路径” | `METRICS`：`table_name` + `extraction_rule: jsonpath:...` + `linking` | `mysql_nearest_row` |
| “这个数是建模/脚本算出来的，不是表里直接读的” | 先在 `STEPS.details` 里用 `action`，再在 `METRICS` 声明 `intermediate` 同名 id（若需展示） | `intermediate` |
| “只有判断进不进场景要看，详情里不用展示这条” | `METRICS.role` | `trigger_only` |
| “只要给后面算均值用，页面上不要单独一行展示原始列表” | `METRICS.role` | `internal` |
| “如果 A 且 B 同时成立才算进入这个故障场景” | `SCENES.trigger_condition` + `metric_id` 仅含 A、B 对应变量 | 条件表达式 `AND` |
| “正常走左支，否则走右支 / 其他情况兜底” | `STEPS` 子分支：`branch_condition` 与最后一条 `else` | `next[].condition` |

### 7.3 访谈话术脚本（建议打印或投屏）

台账列顺序是 **SCENES → STEPS → METRICS**；访谈时建议按 **场景 → 指标 → 路径**（下表 **A → B → C**）提问——路径会反复引用“要看哪些数”，先对齐场景与指标，再细化分支，避免一上来陷入“第几步”细节。

**A. 场景（对应 SCENES 台账）**

1. “这类故障**业务上**叫什么？和别类怎么区分？” → `phenomenon`、`description`、`专家故障现象原话`
2. “**哪些条件同时满足**时，你认为应该走这条诊断而不是别的？” → 专家用口语写几条；开发事后拆成 `trigger_metric_ids` + `trigger_condition`
3. “有没有**只适用于部分机台/工艺**？” → `适用机台/机型`（备注）
4. “你们平时**第一步**从哪里开始查？” → 帮助定 `start_node` 对应的业务节点（开发再映射 `step_id`）

**B. 指标（对应 METRICS 台账）**

对每个专家提到的“要看一个数/一句话/一条日志”：

1. “这个值**在你们界面里**叫什么名字？截图或原话？” → `业务字段原名`、`在哪看`、`看什么`
2. “是**整型拒片记录上的一列**，还是**日志大字段里抠出来的**，还是**配置 JSON 里某路径**？” → 决定 `failure_record_field` / `clickhouse_window` / `mysql_nearest_row`
3. “**时间**以什么为准？往前看多久？” → `time_column`、`duration_days`（开发填）
4. “**怎么算异常/正常**？” → 记在 `专家判断口径`；数值阈值进 `STEPS` 分支或 `trigger_condition`（开发写表达式）

**C. 路径（对应 STEPS 台账）**

对每个业务判断点：

1. “这一步**输入**依赖哪些上面的数或日志？” → 对应 `step_metric_id` 或前序 action 输出
2. “**分支**有几种情况？有没有要**同时**做的几条线？” → `branch_intent`；并行则 `branch_target` 为数组（开发填）
3. “这一步若成立，**责任上归哪个模块/分系统**？”（**中间节点与叶子都要问**）→ `所属模块或分系统`
4. “**终点**结论业务上怎么说？叶子上的根因与分系统文案？” → `leaf_result` 中文草稿，开发改成 `rootCause`/`system` 文案

### 7.4 专家访谈表（仅专家列投影）

下面这些列**全部来自 SCENES / STEPS 台账**；访谈时隐藏所有 `*_metric_*`、`branch_condition`（技术列）、`details_*` 列。

| 来源台账 | 专家必填 / 强建议列 |
| --- | --- |
| SCENES | `module`、`phenomenon`、`description`、`专家故障现象原话`、`专家判断方式`、`适用机台/机型`；**不写** `trigger_condition`（改由 §7.3 口语转写） |
| METRICS | `description`、`unit`、`业务字段原名`、`在哪看`、`看什么`（枚举与截图约定见 §7.4.1） |
| STEPS 主行 | `description`、`所属模块或分系统`、`专家判断口径`、`在哪看`、`看什么`；终点另填 `leaf_result` / `leaf_results` 的**业务表述草稿**（开发可改文案但需评审） |
| STEPS 子分支 | `branch_intent`（业务语言：若…则…）；若存在「回到前面」的排查路径，填 `是否回到前面`、`重复次数` |

落地方式：在 Excel/飞书中对 `SCENES 台账`、`STEPS 台账` 建**视图**，只显示上表列名。

#### 7.4.1 专家访谈字段约定（评审补充）

以下约定来自评审，请与上表列 **配套使用**：

1. **所属模块 / 分系统**  
   **不是只有叶子节点才填。** 路径上每个 step（含只做判断、建模、中间结论的中间节点）都应填写「这一步归属哪个业务模块或责任分系统」，便于评审责任与前后一致。落 JSON 时，叶子节点上的 `system` 仍以 `leaf_result` / `leaf_results` 的定稿为准；中间节点的归属留在台账备注中，供开发与产品对照，不强行写入 `steps[].result`（因引擎非叶子无 `result`）。

2. **在哪看**  
   **只允许三种取值（枚举）**：`las`、`sedc`、`其他`。不要写长 URL 或自由描述作为本列主值；若实际入口在第四方系统，选 `其他`，并在同一行「备注」或 `看什么` 里用短语说明。

3. **看什么**  
   **尽量请专家提供截图**（或截图附件链接、飞书/文档锚点），再配文字说明。仅依赖口述「在某某页第几列」时，开发与评审难以对齐真实界面；截图是首选证据。

4. **是否回到前面**  
   若业务路径上存在「回到更早步骤」的回路（与 `branch_target` 指回较早 `step_id` 一致），除 `branch_intent` 描述外，须补充 **重复次数**：业务上允许循环几轮、或明确上限（如「最多 N 次」「直到某条件满足」）。**无回路则「是否回到前面」填否或留空，`重复次数` 留空。** 该字段用于评审与配置走查；引擎另有 `max_steps` 防死循环，与业务口径的「重复次数」需同时满足。

### 7.5 开发补全表（仅开发列投影）

| 来源台账 | 开发必填列 |
| --- | --- |
| METRICS | 第 6 节整张技术列（`metric_id` 起至 `mysql_omit_equipment_filter`） |
| SCENES | `scene_id`、`trigger_metric_ids`、`trigger_condition`（由 §7.2/7.3 翻译）、`start_node`、`is_default` |
| STEPS 主行 | `step_id`、`step_metric_id`、`details_actions`、`details_params`、`details_results`、`leaf_result / leaf_results`（定稿 JSON）、`当前状态` |
| STEPS 子分支 | `branch_condition`、`branch_target`、`branch_set`、`branch_results` |

开发阶段还需要额外记录（不落 JSON）：`mock 方案`、`数据库字段核对状态`、`待确认 gap`（见 **§9**）。

## 8. 落 JSON 前开发自检清单

在合并台账并写入 `config/<pipeline>.diagnosis.json` 之前，逐项确认：

| 类别 | 检查项 |
| --- | --- |
| **命名** | 新增 `metric_id` 为 `snake_case` ASCII；`scene_id` / `step_id` 在文件内唯一且与 JSON 引用一致 |
| **场景** | `trigger_condition` 中每个 `{var}` 都在本 scene 的 `metric_id`（或等价列表）中出现；纯默认场景（`default=true` 且无 `metric_id`/`trigger_condition`）若作兜底，**排在 `diagnosis_scenes` 最后一项** |
| **分支** | 同一 `step` 的 `next[]` 分支业务上互斥；最后一条为 `condition: "else"`（除非确为单分支叶子）；并行用 `target` 数组，勿与互斥分支混用 |
| **变量** | `steps[].next[].condition` 与 `details.params` 中的占位符，均能解析到已声明的 metric 或前序 `results` |
| **角色** | 仅场景门闸用的指标标 `trigger_only`；窗口原始列表仅供 action 用的标 `internal`；需在详情展示的保持默认 `diagnostic` |
| **METRICS** | DB 类已填 `table_name` / `column_name` / `time_column` / `duration` / `linking`（按 `source_kind` 对照 `CONFIG_GUIDE` 速查表）；`extraction_rule` 与真实字段格式一致 |
| **静态与测试** | 先跑 `pytest src/backend/tests/test_rules_validator.py`，再跑与路径、action 相关的引擎测试 |

## 9. 填写流程

1. 开发预填：给每个待覆盖的故障场景分配 `scene_id`，给该场景已经能规划的节点分配 `step_id`
2. 访谈专家：只给专家看“专家访谈表”视图，按 SCENES 主行 + STEPS 主行 + STEPS 子分支的顺序访谈
3. 回到线下：开发只看“开发补全表”视图，逐列补齐 METRICS 台账、SCENES 技术字段、STEPS 的 `details / next` 技术字段
4. 合并：双方把子视图信息按 `scene_id / step_id / metric_id` 合并回主台账
5. 自动化落 JSON：按第 4/5/6 节的“示例行 → 示例 JSON”方式，把每一行落到 `config/<pipeline>.diagnosis.json` 对应数组/字典
6. 跑静态校验：`pytest src/backend/tests/test_rules_validator.py`
7. 跑路径与 action 测试：`pytest src/backend/tests/test_rules_engine_conditions.py src/backend/tests/test_rules_actions_implementation.py`

**开发阶段额外记录（不落 JSON）**：`mock 方案`、`数据库字段核对状态`、`当前状态`、`待确认 gap`（与 §7.5 台账列一致）。

## 10. 与 `CONFIG_GUIDE.md` 的字段对齐

本模板所有“落 JSON”的列，其字段含义、允许取值与约束，全部以 `config/CONFIG_GUIDE.md` 为权威说明。若出现不一致，以 `CONFIG_GUIDE.md` 和 `rule_validator.py` 为准，本文档需要被同步修订。

对照速查：

| 模板列 | CONFIG_GUIDE 对应小节 |
| --- | --- |
| `METRICS 台账.source_kind / role / linking / extraction_rule / duration_days` | 第 4 节 `metrics` 怎么写；`source_kind` 必填见 **4.3.1**；`role` 见 **4.9** |
| `SCENES 台账.trigger_metric_ids / trigger_condition / start_node / is_default` | 第 5 节 `diagnosis_scenes` 怎么写 |
| `STEPS 台账.details_* / branch_*` | 第 6 节 `steps` 怎么写、第 6.2 节 `details` 规范、第 6.3 节 `next` 规范 |
| `details_params` 四种取值 | 第 6.2 节 `params 绑定规则` |
| 显式形参 / `**ctx` 与 `params` | 第 **6.2.8** 节 |
| 分支是否并行、回路、兜底 | 第 6.3 节 `next` 规范 |

## 11. 常见问题

- **一个 action 多行 vs 合并一行**：`STEPS 台账.details_actions / params / results` 推荐用 JSON 数组表达，和 JSON 1:1 对齐；不建议把多个 action 合并成自然语言
- **分支条件冲突**：同一节点的多个分支必须互斥，`else` 兜底写在最后一行；`rule_validator` 会静态校验变量名，但无法完全保证语义互斥，仍需评审
- **何时用 `leaf_result` vs `leaf_results`**：单一明确结论用 `leaf_result`，需要并列输出多条结论（如“建议排查”+“备选根因”）用 `leaf_results`
- **跨 pipeline 共用 metric**：目前引擎按 pipeline 独立加载 `metrics`；如需共用请在两个 pipeline 的 `metrics` 字典各声明一次
- **场景外的兜底**：引擎按 `diagnosis_scenes` 数组顺序逐个尝试匹配；一条「纯默认场景」（`default=true` 且既无 `metric_id` 也无 `trigger_condition`）一旦被遍历到就立刻命中。所以要当兜底用，**务必把它放到数组的最后一项**，否则会把它前面场景的匹配机会全部吃掉
