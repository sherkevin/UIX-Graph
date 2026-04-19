# Config Guide

本文档面向第一次接手配置的协作者。读完之后，你应该能回答 5 个问题：

1. 运行时到底读哪些文件
2. 一个 pipeline 从空文件到跑通的最小闭环是什么
3. 每个字段应该怎么写，为什么要这样写
4. `details.params` 参数绑定到底有几种规则，边界 case 怎么处理
5. 哪些字段是**当前权威**、哪些是**保留兼容**、哪些已**废弃**

适用对象：

- 需要新增一个诊断 pipeline 的开发者
- 需要修改当前 `reject_errors` 配置的开发者
- 需要排查“配置写了但引擎不按预期执行”的维护者

配套阅读：

- `docs/stage4/diagnosis-path-template.md`：面向专家访谈和开发补全的模板表，每一列都对应本文件中的 JSON 字段
- `src/backend/app/engine/rule_validator.py`：静态校验的权威实现
- `src/backend/app/engine/actions/__init__.py`：`_resolve_params` 和 `call_action` 的权威实现

---

## 1. 先建立心智模型

### 1.1 运行时真正读取哪些文件

当前后端运行时真正会读取的诊断配置只有两层：

1. `config/diagnosis.json`
2. `config/<pipeline>.diagnosis.json`

当前索引文件是：

```json
{
  "version": "3.0.0",
  "pipelines": {
    "reject_errors": {
      "mode": "structured",
      "config_file": "reject_errors.diagnosis.json"
    },
    "ontology_api": {
      "mode": "structured",
      "config_file": "ontology_api.diagnosis.json"
    }
  }
}
```

含义：

- `diagnosis.json` 只负责登记有哪些 pipeline
- 每个 pipeline 的真实规则在对应的 `*.diagnosis.json`

### 1.2 一条诊断是怎么跑起来的

把一个 pipeline 想成 3 块：

- `metrics`：定义“变量从哪里来”
- `diagnosis_scenes`：定义“什么情况下进入这条诊断”
- `steps`：定义“进入后怎么一步一步走到结论”

运行链路大致如下：

1. `DiagnosisConfigStore` 读取 `diagnosis.json`
2. 根据 pipeline id 找到对应的 `<pipeline>.diagnosis.json`
3. 加载 `metrics / diagnosis_scenes / steps`
4. 启动期执行 `rule_validator.validate_rules_config` 静态校验
5. 运行时由 `DiagnosisEngine` 先匹配 scene，再取 metric，再按 `steps` 决策树往下走
6. 到叶子节点后返回 `rootCause / system / metrics`

一句话记忆：

> `metrics` 决定“拿什么数据”，`diagnosis_scenes` 决定“从哪棵树开始”，`steps` 决定“怎么走到结论”。

### 1.3 当前 `config/` 目录中文件的角色

| 文件 | 角色 | 运行时是否读取 |
| --- | --- | --- |
| `diagnosis.json` | pipeline 索引 | 是（权威） |
| `<pipeline>.diagnosis.json` | 单个 pipeline 的完整规则 | 是（权威） |
| `connections.json` | 数据库连接 | 是 |
| `metrics_meta.yaml` | 指标备注补充 | 若存在则 merge 到 metrics 元数据；只放说明，不放核心逻辑 |
| `CONFIG_GUIDE.md` | 本文档 | 否 |
| `trash/*` | 历史参考 | 否 |

> 注意：当前项目运行时的权威配置是 `diagnosis.json + <pipeline>.diagnosis.json`。  
> 历史上的 `metrics.json`、`rejection_rules.json`、`trash/*`，若存在，也只是参考，不会被当前 structured pipeline 执行。

---

## 2. 最小可运行配置闭环 checklist

这一节是给“第一次新增 pipeline”的人准备的。按顺序做，从空文件到能跑出一个根因只需 5 步：

### 步骤 1：新建 pipeline 文件

在 `config/` 下新建 `my_pipeline.diagnosis.json`，最小骨架：

```json
{
  "version": "3.0.0",
  "metrics": {},
  "diagnosis_scenes": [],
  "steps": []
}
```

硬要求：

- `version` major 必须为 `3`
- 三个顶层 key 都要有（可为空对象/空数组，但不能省略）

### 步骤 2：在 `diagnosis.json` 登记这个 pipeline

```json
"pipelines": {
  "my_pipeline": {
    "mode": "structured",
    "config_file": "my_pipeline.diagnosis.json"
  }
}
```

硬要求：`mode` 只能是 `structured`，非此值会抛错。

### 步骤 3：声明一条可以直接触发的场景

> 对于第一次跑通，**先用 `default=true` 最省事**，不需要写 `trigger_condition`。

```json
"diagnosis_scenes": [
  {
    "id": "default-scene",
    "module": "demo",
    "phenomenon": "最小可运行示例",
    "description": "用于验证 pipeline 能跑通",
    "default": true,
    "start_node": "1"
  }
]
```

硬要求：

- `start_node` 必须等于某个 `steps[].id` 的字符串形式
- 若用 `trigger_condition`，则只能引用本 scene 中 `metric_id` 数组里列出的变量

### 步骤 4：写 2 个 step：一个判断 + 一个叶子

```json
"steps": [
  {
    "id": "1",
    "description": "最小判断",
    "next": [
      {"target": "99", "condition": "else"}
    ]
  },
  {
    "id": "99",
    "description": "兜底叶子",
    "result": {"rootCause": "未知原因", "system": "待分析"}
  }
]
```

硬要求：

- 叶子节点必须有 `result` 或 `results`，不写 `next`
- 非叶子节点至少要有一条可命中的 `next` 分支（强烈建议最后一条是 `condition="else"`）

### 步骤 5：自检

```bash
cd src/backend
python -m pytest tests/test_rules_validator.py
```

通过即视为“最小闭环完成”。此时调用 `DiagnosisEngine(pipeline_id="my_pipeline")` 对任意一条输入都会走到 `id=99` 叶子，返回根因 `未知原因`。

### 闭环完成后再扩展

按这个顺序扩展最不容易出错：

1. 先加 `metrics`：明确“哪些变量需要自动取数”，用最少的 metric 能让诊断启动即可
2. 再扩 `diagnosis_scenes`：从 `default=true` 改成 `trigger_condition`，引入真正的场景识别
3. 再扩 `steps`：为每个需要判断的业务节点新增 step，条件从 `else` 兜底逐步精细化
4. 每次扩张都先跑 `test_rules_validator.py`，再跑 `test_rules_engine_conditions.py`

---

## 3. `reject_errors.diagnosis.json` 文件结构

当前结构化 pipeline 顶层固定包含 3 块：

```json
{
  "version": "3.0.0",
  "metrics": {},
  "diagnosis_scenes": [],
  "steps": []
}
```

含义：

- `version`
  - 当前只支持 major version = `3`
- `metrics`
  - 定义所有指标的数据来源、单位、窗口、链接方式等
- `diagnosis_scenes`
  - 定义场景触发入口
- `steps`
  - 定义执行路径、action 和分支跳转

### 3.1 写配置时的思考顺序

建议不要一上来就写 JSON，先想清楚 3 件事：

1. 我要诊断的入口是什么（某个 reject reason / 某组请求参数 / 某个异常组合）
2. 我要用到哪些原始变量（source record / request 参数 / MySQL / ClickHouse / 上一步中间结果）
3. 我如何一步步收敛到结论（先判场景 -> 再算 -> 再分支 -> 再落叶子）

如果这 3 点没想清楚，直接写 JSON 通常会出现：

- metric 定义了一堆，但 scene 根本触发不了
- scene 触发了，但 step 里引用了不存在的变量
- 分支条件互相重叠，运行时冲突
- 本来应该在 action 做的聚合，错误地写成了 metric

---

## 4. `metrics` 怎么写

### 4.1 一个 metric 的典型结构

```json
"Mwx_0": {
  "description": "倍率实测值",
  "data_type": null,
  "unit": "ppm",
  "source_kind": "clickhouse_window",
  "linking": {
    "mode": "time_window_only",
    "keys": [],
    "filters": []
  },
  "fallback": {
    "policy": "nearest_in_window"
  },
  "table_name": "las.LOG_EH_UNION_VIEW",
  "column_name": "detail",
  "time_column": "file_time",
  "extraction_rule": "regex:Mwx\\s*\\(\\s*([\\d\\.]+)\\s*\\)",
  "duration": "7"
}
```

### 4.2 字段分三类

为了避免“保留字段、兼容格式、现行格式混在一起误导”，下面把字段拆成 3 类，每次写配置时请自觉对照：

#### 4.2.1 现行权威字段（应当使用）

| 字段 | 适用 `source_kind` | 说明 |
| --- | --- | --- |
| `description` | 所有 | 中文业务说明 |
| `unit` | 所有 | 展示单位，如 `um / ppm / urad` |
| `data_type` | 所有 | 运行时做类型转换；允许 `int / integer / float / double / number / bool / boolean / str / string / text` |
| `source_kind` | 所有 | 仅允许 `failure_record_field / request_param / mysql_nearest_row / clickhouse_window / intermediate` |
| `role` | 所有 | `diagnostic`（默认） / `trigger_only` / `internal` |
| `field` | `failure_record_field / request_param` | 源记录或请求参数里的键名 |
| `transform` | `failure_record_field / request_param` | 对取到的原始值做变换，详见 4.4 |
| `table_name` | `mysql_nearest_row / clickhouse_window` | 完整库表名；ClickHouse 请写 `db.table` |
| `column_name` | `mysql_nearest_row / clickhouse_window` | 取数列名 |
| `time_column` | `mysql_nearest_row / clickhouse_window` | 时间列名 |
| `equipment_column` | `mysql_nearest_row / clickhouse_window` | 设备列名 |
| `linking` | 所有 DB 类 | 结构见 4.5 |
| `fallback` | 所有 DB 类 | 结构 `{"policy": "nearest_in_window" \| "none"}`，未显式写等价于 `none` |
| `extraction_rule` | 所有 DB 类 | 仅支持 `regex:<pattern>` 与 `jsonpath:<path>` |
| `duration` | 所有 DB 类 | 窗口时间，字符串或数字，单位**天** |
| `enabled` | 所有 | `false` 表示保留字段但取数阶段直接跳过，返回 `None` |
| `approximate` | `intermediate` | 仅用于提示前端这是“建模产物”，不进行任何运行时计算 |
| `alias_of` | `intermediate` | 该 metric 是另一个 metric 的别名，阈值反查时用 `alias_of` 指向的 metric_id 找规则;静态校验:目标必须存在、不能自指、不能成环。典型 `output_Tx → Tx` |
| `mock_value` | 所有 | 任意 JSON 字面量(数字/布尔/字符串/null);取数失败或 intermediate 兜底时直接返回此值 |
| `mock_range` | 数值类 metric | 数组 `[low, high]`,low ≤ high;取数失败或 intermediate 兜底时,返回 `[low, high]` 之间的随机数 |

#### 4.2.2 保留兼容字段（谨慎使用）

下面这些字段**会被引擎识别**，但属于为了兼容既有业务或源表形态而留的“特例开关”，建议只在业务明确需要时使用：

| 字段 | 用途 | 使用建议 |
| --- | --- | --- |
| `mysql_omit_equipment_filter` | 针对 `mysql_nearest_row` 跳过默认 equipment 硬过滤 | 只有目标表没有 equipment 列、或业务确认需要跨 equipment 取数时才加；不要默认加 |
| `source_kind = "mysql"` / `"clickhouse"` 字符串别名 | 旧写法；引擎内部会 normalize 到 `mysql_nearest_row` / `clickhouse_window` | 新配置不要使用，必定写完整 snake_case |
| `_note` / `_comment` 等下划线开头字段 | 单纯注释，引擎不读 | 允许，用于记录“为什么这么改”；但不要用于记录运行逻辑 |
| 中文 metric id（如 `动态上片偏差`） | 历史遗留 | 新增必须使用 snake_case ASCII；存量不强拆 |

#### 4.2.3 已废弃字段（禁止使用）

下面这些写法会在**静态校验阶段直接报错**：

| 字段 | 出现位置 | 报错提示 |
| --- | --- | --- |
| `operator` | `steps[].next[]` 分支 | “已废弃 operator 字段，请在 condition 中写比较或区间表达式” |
| `limit` | `steps[].next[]` 分支 | “已废弃 limit 字段，请在 condition 中写比较或区间表达式” |
| `version` major ≠ 3 | 文件顶层 | “version=... 不受支持” |
| `mode` ≠ `structured` | `diagnosis.json` 的 pipeline 定义 | “mode=... 不再受支持” |

### 4.3 `source_kind` 规范

当前仅允许这 5 个值（小写，snake_case）：

| 值 | 含义 | 常见例子 |
| --- | --- | --- |
| `failure_record_field` | 直接从故障主记录取字段 | `Tx`、`Ty`、`Rw` |
| `request_param` | 直接从接口请求参数取字段 | `ontology_api` 中的 `rotation_mean` |
| `clickhouse_window` | 从 ClickHouse 按时间窗口查询 | `Mwx_0`、`ws_pos_x` |
| `mysql_nearest_row` | 从 MySQL 按时间窗口查询 | `Sx`、`Tx_history` |
| `intermediate` | 中间变量，不取数；值来自 action 输出 | `output_Mw`、`mean_Tx`、`n_88um` |

关键区别：

- **DB 类**（`clickhouse_window / mysql_nearest_row`）返回“窗口值列表”，不是单个聚合值
- 如果需要均值、计数、最近值，请在 action 里显式完成，**不要塞进 metric**

#### 4.3.1 按 `source_kind` 的必填 / 常用字段速查

写 `metrics` 时先定 `source_kind`，再按表补齐字段；缺关键字段时运行时会取不到数或报错。`description` / `unit` / `role` 建议始终填。

| `source_kind` | 运行取数**硬依赖** | 强烈建议（与现有配置一致） |
| --- | --- | --- |
| `failure_record_field` | `field` | `transform`（若需把原始值变成布尔/枚举） |
| `request_param` | `field` | — |
| `mysql_nearest_row` | `table_name`、`column_name`、`time_column`、`duration` | `linking`（至少 `mode`；`exact_keys` 时填 `keys`）、`extraction_rule`、`fallback` |
| `clickhouse_window` | 同上 | 同上 |
| `intermediate` | 无 DB 字段；由 action 写入 context | 若仅作提示，可设 `approximate` |

说明：

- `linking` 省略时引擎会按 `time_window_only` 理解，但**仍需要**表名、列名、时间列与窗口
- `equipment_column` 在 `mysql_nearest_row` 上常用于设备过滤；若表无设备列，见 4.2.2 的 `mysql_omit_equipment_filter` 特例
- `extraction_rule` 对 DB 类指标通常**需要**，除非列值已是可直接比较的标量

### 4.4 `transform` 规范（仅直接取值类型使用）

只在 `failure_record_field / request_param` 的单值上生效；`clickhouse_window / mysql_nearest_row` 不走此分支。

当前 `_apply_transform` 支持的 `type`：

| type | 行为 |
| --- | --- |
| `equals` | `value == transform.value` |
| `not_equals` | `value != transform.value` |
| `float` / `int` / `bool` | 强转 |
| `upper_equals` / `lower_equals` | 忽略大小写相等 |
| `contains` | `transform.value in str(value)` |
| `map` | 按 `transform.mapping[value]` 查表，查不到返回原值 |

未识别的 `type` 会 `logger.warning` 并保留原值。

### 4.5 `linking` 规范

结构：

```json
"linking": {
  "mode": "exact_keys",
  "keys": [
    {"target": "equipment", "source": "equipment"},
    {"target": "lot_id", "source": "lot_id"},
    {"target": "chuck_id", "source": "chuck_id"},
    {"target": "wafer_id", "source": "wafer_id"}
  ],
  "filters": [
    {"target": "phase", "value": "1ST_COWA"}
  ]
}
```

字段含义：

- `mode`
  - `time_window_only`：只按时间窗口查
  - `exact_keys`：除时间窗口外，还加 keys 精确过滤
- `keys[]` / `filters[]` 中每项支持的 key：
  - `target`：SQL 列名（强制做标识符校验：`[A-Za-z_][A-Za-z0-9_\.]*`）
  - `source`：从 context 取值的键名
  - `value`：字面常量（与 `source` 二选一）
  - `operator`：可选；允许 `= / == / != / > / >= / < / <= / contains / in`；未填为 `=`
- 当 `source` 在运行时取不到值时，会记为 `missing_required`，取数直接返回空
- ClickHouse 上 `=/!=` 会自动转 `toString(col) op toString(val)` 以绕开 String/Int 混用

硬约束：

- 只有源表真实存在、且运行时上下文能提供取值的字段，才能写进 `keys`
- 目标原则是尽量用满 `equipment + chuck + lot + wafer + time`
- 业务方最新口径如果变了，必须同步改 `table_name / column_name / linking`

### 4.6 `duration` 规范

- 单位固定为**天**
- 常规指标默认 `7`
- 月均值相关的历史窗口指标通常为 `30`
- 写 `"7"`（字符串）或 `7`（数字）都可以，但**不要写成**分钟、秒、毫秒

```json
"Tx_history": {
  "duration": "30",
  "role": "internal"
}
```

### 4.7 `extraction_rule` 规范

当前支持三种形式:

- `regex:<pattern>`(正则第 1 组捕获,若无捕获组则布尔化:匹配=true / 不匹配=false)
- `jsonpath:<segments/using/slashes>`(支持 `/` 分段、纯数字段=数组下标、`name[N]` 复合 segment 等价于 `name/N`,支持 `{var}` 模板替换)
- `json:<top_level_key>`(简化版:`json.loads(raw).get(top_level_key)`,只取顶层 key,不支持嵌套;新配置优先用 `jsonpath:` 表达力更强)

提取阶段发生在**取数阶段**而不是 action 里;对窗口型指标会先对每条原始值做提取,再汇成列表。

> `jsonpath:` 的 `name[N]` 形式由 `_NAME_INDEX_RE` 处理:先 `current = current[name]`(必须是 dict 取出 list),再 `current = current[N]`。对应 metric_fetcher 实现 `_extract_json_path_value`。

### 4.8 新增一个 metric 时先做这 4 个判断

1. 这个值是不是已经在故障主记录里 -> 用 `failure_record_field`
2. 这个值是不是由调用方通过接口参数传入 -> 用 `request_param`
3. 这个值是不是需要按时间窗从 DB 查 -> 用 `mysql_nearest_row` / `clickhouse_window`
4. 这个值是不是前一步 action 的中间产物 -> 用 `intermediate`

常见错误：

- 实际需要“查窗口 + 算均值”的指标，被误写成单值 metric
- 实际是 action 产物的变量，被误写成直接查库

口诀：

> 原始值进 `metric`，聚合值进 `action`，最终结论落在叶子节点。

### 4.9 `role` 决策树（`trigger_only` / `internal` / `diagnostic`）

先问：**这个指标要不要在详情页里单独展示给用户看？**

1. **只用于场景门闸**（判断进不进这条诊断，且不希望详情里多一行）→ `role: "trigger_only"`  
   - 典型：`reject_reason` 映射、`trigger_log_*` 布尔命中  
   - 仍要出现在本 scene 的 `metric_id` 里供 `trigger_condition` 使用

2. **只给后续 action 当输入**（例如窗口原始列表 `Tx_history`，页面上不展示原始列表）→ `role: "internal"`  
   - 典型：先 `select_window_metric` 再算均值

3. **其它**（需要在路径上向用户展示、或默认展示行为即可）→ 省略或 `role: "diagnostic"`（默认）

与 **纯默认场景** 的连带提醒（详见 5.2 与 5.4）：若某条 `diagnosis_scenes` 为 `default=true` 且**既没有** `metric_id` **也没有** `trigger_condition`，引擎**遍历到该条就立刻选中**并停止；要把它当全 pipeline 兜底时，**必须放在 `diagnosis_scenes` 数组的最后一项**。

---

## 5. `diagnosis_scenes` 怎么写

### 5.1 典型结构

```json
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
```

### 5.2 字段规则

| 字段 | 是否必填 | 规则 |
| --- | --- | --- |
| `id` | 是 | 全局唯一，可整数可字符串 |
| `module` / `phenomenon` / `description` | 建议填 | 面向业务展示，无运行时语义约束 |
| `metric_id` | 条件必填 | 若写 `trigger_condition`，则必须在此声明条件里用到的所有变量；允许数组或字符串 |
| `trigger_condition` | 条件必填 | 数组或单字符串；只能引用本场景 `metric_id` 中出现过的变量，否则静态校验直接报错 |
| `start_node` | 是 | 必须等于 `steps[].id` 中的某一个（字符串形式） |
| `default` | 否 | 若为 `true` 且该场景**不含** `metric_id` / `trigger_condition`：引擎在**遍历到该场景时立刻命中**并返回；因此若要把它当“兜底场景”使用，**必须放在 `diagnosis_scenes` 数组的最后一项**；若含 `trigger_condition`，则按普通条件匹配，不享有默认特权 |

### 5.3 `trigger_only` 的正确用法

对于只做“是否进入场景”的指标，建议：

- 在 `metrics[x]` 下声明 `role: "trigger_only"`
- 在 `diagnosis_scenes[].metric_id` 引用
- 不要把它放进 `steps[].metric_id`，也不要在 `steps[].next[].condition` 里再度使用（这样会在前端详情重复展示）

### 5.4 场景匹配的 3 条规则（按优先级）

引擎 `_select_scene` 按 `diagnosis_scenes` 数组顺序逐一尝试，对每一项的判定优先级如下：

1. **纯默认场景** （`default=true` 且既无 `metric_id` 也无 `trigger_condition`）：遍历到就立刻返回，**不会再看后续场景**
2. **有 `trigger_condition`**：按顺序求值所有条件，任一条为 true 即命中；引擎会打 `[详情排障] select_scene 子条件 | ok=...` 详细日志
3. **只有 `metric_id` 没有 `trigger_condition`**：隐式规则——当「数组非空且所有 metric 的取值都是 truthy」时命中；很少见，建议显式写 `trigger_condition` 以免歧义

### 5.5 常见错误

- 把 `default=true` 场景放到数组最前面，结果后面所有场景都匹配不到
- 在 `trigger_condition` 里引用了没写进本场景 `metric_id` 的变量（静态校验直接报错）
- 把展示用指标（`role` 留空或 `diagnostic`）也写进 `metric_id`，导致详情页前置出现与路径无关的指标

---

## 6. `steps` 怎么写

### 6.1 Step 基本结构

```json
{
  "id": 30,
  "description": "计算Tx的mean值",
  "metric_id": "Tx",
  "details": [
    {
      "action": "calculate_monthly_mean_Tx",
      "params": {
        "Tx": "{Tx_history}"
      },
      "results": {
        "mean_Tx": ""
      }
    }
  ],
  "next": [
    {"target": "41", "condition": "-2 < {mean_Tx} < 2"},
    {"target": "40", "condition": "else"}
  ]
}
```

一个 step 允许三种形态：

| 形态 | 特征 | 常见用法 |
| --- | --- | --- |
| 计算 + 分支 | 有 `details`，有 `next` | 先算再分流（建模 / 均值） |
| 仅分支 | 无 `details`，有 `next` | 纯判断节点 |
| 叶子 | 无 `next`，有 `result` 或 `results` | 输出结论 |

### 6.2 `details.params` 参数绑定规则（完整版）

这是每次新增 action 最容易出错的地方，完整规则如下。所有逻辑在 `src/backend/app/engine/actions/__init__.py::_resolve_params` 和 `call_action` 中实现。

#### 6.2.1 四种取值模式

| params 值写法 | 引擎行为 |
| --- | --- |
| `""`（空字符串） | `resolved[key] = context.get(key)`：按参数键名从 context 读同名变量 |
| `null` | 同上（等价于空字符串） |
| `"{var_name}"` | `resolved[key] = context.get(var_name)`：按花括号内的变量名从 context 读；两端空格允许；`{}` 内必须是单个标识符 |
| 其它字符串 / 数字 / 布尔 / 对象 / 数组 | 作为**字面量**原样传给 action（不会从 context 取值） |

#### 6.2.2 整个 params 的边界

| 写法 | 行为 |
| --- | --- |
| `"params": null` 或 `"params": {}` | 不做任何 params 解析；action 仍可从 context 里拿变量（见 6.2.3） |
| `"params": "some string"` | 非 dict 一律按“空”处理 |

#### 6.2.3 action 能拿到什么：`context + params`

`call_action` 合并规则是：

```python
kwargs = dict(context)
kwargs.update(_resolve_params(params, context))
fn(**kwargs)
```

所以 action 的可用入参：

- **context 中的所有键** 先作为 kwargs
- 再用 `params` 里解析出的键**覆盖**同名 context 键

这就解释了为什么很多 action 函数签名写成 `def xxx(**ctx)`，因为 context 会被整包塞进来；`params` 只是“对某些键的精确指定”。

#### 6.2.4 取不到值时的默认行为

- `context.get("key")` 不存在时返回 `None`
- 绝大多数 action 自己会做兜底（例如 `_first_numeric(value, 0.0)`）
- 如果你希望“取不到就报错”，请在 action 内部主动 `raise`，引擎不会替你抛

#### 6.2.5 字面量类型

只要不是空字符串、`null`、或完全被 `{...}` 包住的字符串，就按字面量：

```json
"params": {
  "metric_name": "Mwx_0",    // 字符串字面量
  "values": "{Mwx_0}",       // 从 context 取 Mwx_0
  "upper_limit": 1.0001,     // 数字字面量
  "enable": true,            // 布尔字面量
  "tags": ["88um", "8um"],   // 数组字面量
  "mapping": {"a": 1}        // 对象字面量
}
```

#### 6.2.6 常见坑

- `"{Mwx_0} > 1"` 这种**写法不是占位符**（不是单纯 `{var}`），会被当字面字符串传给 action，不会取值
- `"{ Mwx_0 }"` 内部带空格是允许的，会 `strip` 后取值
- 如果 params 里写了 `"Tx": ""`，而 context 里**没有** `Tx`，action 会收到 `Tx=None`；不会收到 context 中同名以外的其它键

#### 6.2.7 `results` 声明的作用

`details[].results` 是**契约声明**，不是白名单过滤：

- `results` 里声明的键若 action 实际没返回，会打 warning，但不会阻塞
- action 返回的其他键**也会**全部写入 context（`results` 不会过滤 action 的输出）
- 作用：对维护者清晰表明“这一步会新增哪些变量”，供静态校验与 `context.update` 使用

#### 6.2.8 显式形参、`**ctx` 与 `params` 的关系

`call_action` 总是 `fn(**kwargs)`，其中 `kwargs = context ∪ _resolve_params(params, context)`（后者覆盖同名键）。因此：

| 写法 | 含义 |
| --- | --- |
| `def foo(**ctx)` | 依赖 `params` 与 context 把需要的键塞进 `kwargs`；适合入参多、或大量键来自 context |
| `def foo(Tx: Optional[float] = None, **ctx)` | 显式声明主参数，其余仍可从 `kwargs` 取；`params` 里若绑定 `Tx` 会覆盖 context 中的 `Tx` |
| `def foo(metric_name: str = "", values: Any = None, **ctx)` | 典型 `select_window_metric`：把 `params` 当“主参数”，其余上下文透传 |

与 `params` 的关系：

- **`params` 不是“函数签名白名单”**：未在 `params` 里写的键，只要还在 `context` 里，仍会进入 `kwargs`（除非 action 自己用 `**` 忽略）
- **`params` 用于精确绑定**：例如 `"Tx": "{Tx_history}"` 把窗口列表绑定到形参 `Tx`
- 若 `params` 为 `null` / `{}`，`kwargs` 就是完整 `context`，action 需自行从 `ctx` 里取所需变量

### 6.3 `next` 规范

- 每个分支必须有 `target`
- `target` 可以是单个 step id，也可以是数组（表示并行进入多个子节点）
- `condition` 使用表达式字符串或结构化对象
- `condition = "else"` 表示兜底分支
- `set`（可选）：进入目标节点前向 context 写入的键值对，常用于“分支即绑定”（如 `set: {"model_type": "88um"}`）
- `results`（可选）：在分支层也可以声明会新增哪些 context 键（静态校验会认这些键为已声明变量）

不允许的字段（会在静态校验直接报错）：

- `operator`
- `limit`

### 6.4 条件表达式怎么写

支持四种写法：

| 写法 | 示例 |
| --- | --- |
| 单比较 | `{n_88um} <= 8`、`{model_type} == '88um'` |
| 区间 | `-20 < {output_Mw} < 20` |
| 布尔组合 | `{A} == true AND {B} == true`(支持 AND/OR,括号分组;**AND/OR 大小写不敏感**:`and / Or / aNd` 都行,但两侧必须有空格) |
| 结构化对象 | `{"all_of": [{"compare": {"left": "A", "operator": ">", "right": 1}}]}` |

要求：

- 变量必须写成 `{变量名}`
- 同一 step 的多个条件应互斥
- 建议每个非叶子 step 都提供 `condition="else"` 兜底
- 所有变量名必须落在：`metrics 键 ∪ 场景/step.metric_id ∪ 分支 set/results 键`，否则静态校验会报错

### 6.5 三个完整 Case

#### Case 1：最小可运行 pipeline（适合新建 pipeline 时照着写）

```json
{
  "version": "3.0.0",
  "metrics": {
    "rotation_mean": {
      "source_kind": "request_param",
      "field": "rotation_mean",
      "unit": "urad"
    }
  },
  "diagnosis_scenes": [
    {
      "id": "default-scene",
      "module": "ontology",
      "phenomenon": "通用故障诊断",
      "description": "用于接口入参的简单诊断",
      "default": true,
      "start_node": "1"
    }
  ],
  "steps": [
    {
      "id": "1",
      "description": "判断旋转是否超限",
      "next": [
        {"target": "101", "condition": "{rotation_mean} > 300"},
        {"target": "199", "condition": "else"}
      ]
    },
    {"id": "101", "result": {"rootCause": "上片旋转机械超限", "system": "机械精度"}},
    {"id": "199", "result": {"rootCause": "未知原因", "system": "待分析"}}
  ]
}
```

说明：

- `metric` 可直接绑定请求参数
- `scene` 可以用 `default=true` 当入口
- `step` 不一定要有 `details`，也可以只做条件跳转

#### Case 2：trigger-only 场景入口（适合 reject_errors）

```json
{
  "metrics": {
    "trigger_reject_reason_cowa_6": {
      "source_kind": "failure_record_field",
      "field": "reject_reason",
      "transform": {"type": "equals", "value": 6},
      "role": "trigger_only"
    },
    "trigger_log_mwx_cgg6_range": {
      "source_kind": "clickhouse_window",
      "table_name": "las.LOG_EH_UNION_VIEW",
      "column_name": "detail",
      "time_column": "file_time",
      "extraction_rule": "regex:Mwx out of range,CGG6_check_parameter_ranges",
      "duration": "7",
      "role": "trigger_only"
    }
  },
  "diagnosis_scenes": [
    {
      "id": 1001,
      "module": "COWA",
      "phenomenon": "倍率超限",
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
}
```

重点：

- `metric_id` 是“触发场景需要哪些变量”
- `trigger_condition` 只能引用 `metric_id` 里列出来的变量
- `trigger_only` 不进详情展示

#### Case 3：窗口值 -> 中间量 -> 分支

```json
{
  "id": 30,
  "description": "计算 Tx 月均值",
  "metric_id": "Tx_history",
  "details": [
    {
      "action": "calculate_monthly_mean_Tx",
      "params": {"Tx": "{Tx_history}"},
      "results": {"mean_Tx": ""}
    }
  ],
  "next": [
    {"target": "41", "condition": "-2 < {mean_Tx} < 2"},
    {"target": "40", "condition": "else"}
  ]
}
```

字段职责：

- `metric_id`：声明主输入变量
- `action`：调用哪个已注册函数
- `params`：把 context 变量绑定到 action 入参
- `results`：声明 action 会写回 context 的变量
- `next.condition`：使用 action 输出的变量继续分支

---

## 7. 当前 `reject_errors` 的特殊约定

### 7.1 不要回退这些增强

`reject_errors.diagnosis.json` 有几处是为了兼容当前实现而保留的，修改时不要轻易回退：

- `step 1` 的 `select_window_metric`
  - 因为 `Mwx_0` 是窗口列表，必须先选一个标量
- `Tx_history / Ty_history / Rw_history`
  - 因为月均值必须从窗口列表计算
- `continue_model` + `continue_model_dispatch`
  - 为避免建模路径死循环做的保护
- `n_88um`
  - 建模次数控制变量

### 7.2 `output_*` 规范

以下指标应视为 action 产物：

- `output_Mw`、`output_Tx`、`output_Ty`、`output_Rw`

不要把它们改成直接从故障主记录取值，除非业务明确要求变更计算口径。

---

## 8. 修改现有配置的推荐流程

### 场景 A：业务方只改了路径逻辑

（触发条件变、分支判断变、根因文案变）

1. 改 `reject_errors.diagnosis.json`
2. 跑规则校验
3. 跑路径相关测试

### 场景 B：业务方改了指标来源

（表名、列名、时间列、linking key）

1. 确认业务最新口径（表 / 列 / 时间列 / 过滤字段 / 真实样例 / linking 假设）
2. 对照 `src/backend/app/engine/metric_fetcher.py` 实现
3. 修改目标 `*.diagnosis.json`
4. 如启用 `metrics_meta.yaml`，同步维护说明性字段
5. 必要时补测试

### 场景 C：新增一个 pipeline

按第 2 节闭环 checklist 5 步走即可。

---

## 9. 修改后怎么验证

### 9.0 自助配置自检(推荐第一步)

```bash
python scripts/check_config.py            # 检查 diagnosis.json 索引下所有 pipeline
python scripts/check_config.py reject_errors  # 仅检查指定 pipeline
python scripts/check_config.py --strict   # warning 也当失败
```

退出码:`0` 全过 / `1` error / `2` warning + `--strict`。除了硬校验(rule_validator),还会输出 4 类**软警告**:

- **orphan intermediate metrics**:声明 `source_kind: intermediate` 但 `details.results` / `set` / `condition` / `details.params` 都没引用 → 占位垃圾或 stage 未接入的 TODO
- **unreachable steps**:既非 `start_node` 也非任何 `next.target` → 死代码
- **DB metric missing fallback.policy**:数据窗口空时直接 None,易让诊断走错路径(建议显式写 `nearest_in_window` 或 `none` 表态)
- **duplicate scene start_nodes**:多个 scene 共用同一起点,语义可能冗余

软警告默认不阻断 PR,但**评审时应当看一遍**(配套 [`docs/CONFIG_REVIEW_CHECKLIST.md`](../docs/CONFIG_REVIEW_CHECKLIST.md))。

### 9.1 静态校验

```bash
cd src/backend
python -m pytest tests/test_rules_validator.py tests/test_rule_validator_metric.py
```

### 9.2 路径条件校验

```bash
cd src/backend
python -m pytest tests/test_rules_engine_conditions.py
```

### 9.3 action 计算校验

```bash
cd src/backend
python -m pytest tests/test_rules_actions_implementation.py
```

### 9.4 指标取数回归

（若改了表名、列名、时间列、窗口逻辑）

```bash
cd src/backend
python -m pytest tests/test_metric_fetcher_window.py
```

---

## 10. 常见错误

- 只改了业务原始规则文件，没改运行时的 `*.diagnosis.json`
- 在 `next` 分支上继续写 `operator` / `limit`
- 在 `trigger_condition` 中引用了没写进 `metric_id` 的变量
- 把 `duration` 当成分钟或秒
- 把窗口列表指标当成单值直接用
- 在 `linking.keys` 中写了源表或上下文里根本不存在的字段
- 把 `output_Tx/Ty/Rw` 错误改成直接来自源表
- 在 `params` 里写 `"{Mwx_0} > 1"`，以为会取值（实际是字面量）
- `details.results` 里声明的键与 action 实际返回不一致（只告警，不阻塞）

---

## 11. 高风险点与后续修补计划

这一节不是“当前不能动”，而是提示后续维护时最容易出事故的地方。

### 11.1 文档口径与运行时实现的漂移管理

历史:旧文档曾描述早期文件或旧结构;`duration` 单位在不同文档曾表述不一致(分钟/秒/天)。
现状:已统一以 `diagnosis.json + <pipeline>.diagnosis.json` 为权威;`duration` 一律「**天**」(见 §4.6)。

后续保护:每次涉及 `metric_fetcher.py` / `rule_validator.py` / `condition_evaluator.py` 的代码修改,**必须**同步更新本文件 §4 的「现行权威字段」表与 [`docs/stage3/rules_execution_spec.md`](../docs/stage3/rules_execution_spec.md) §5.1 的校验项清单。

### 11.2 配置 DSL 已经很强，但模板化入口还不够友好

现象：新人分不清 `metric / action / result / trigger_only / internal` 的边界。  
修补：

1. 本文件第 2 节已加“最小可运行闭环 checklist”
2. 后续沉淀 `config/examples/` 若干典型模板

### 11.3 静态校验能挡住很多错误，但挡不住全部语义错误

现象：`rule_validator` 能校变量名、step id、target、action 注册；无法完全验证 action 返回值是否和 `results` 一致，也无法保证多分支语义互斥。  
修补：

1. 为关键 pipeline 增加“case 驱动”的契约测试
2. 对关键 step 增加示例输入 / 期望输出
3. 对高风险 action 增加单测

### 11.4 数据源字段和 linking 规则容易悄悄失真

现象：metric 依赖 `table_name / column_name / time_column / linking.keys`；一旦数据表口径变化，配置表面上仍合法 JSON，但运行时查不到或查错值。  
修补：

1. 每次涉及数据源字段变更强制复核样例数据
2. 优先补 `metric_fetcher` 层的回归测试
3. 对关键 metric 增加“示例记录 -> 预期取值”说明

### 11.5 `reject_errors` 配置已经偏复杂

现象：既有 trigger scene、窗口指标、建模 action、中间变量，且带历史兼容痕迹。  
修补：

1. 按场景分段整理注释
2. 历史兼容变量 / 中间变量 / 输出变量分组标注
3. 规则规模继续扩大时拆小

### 11.6 推荐的修补优先级

按投入产出比：

1. 文档口径（保证大家改对文件）
2. 配置模板和 case（降低新增成本）
3. 配置契约测试（防“能加载但结果错”）
4. 更深的结构整理（拆分大配置、引入模板目录、加强可视化校验）

---

## 12. 与 `docs/stage4/diagnosis-path-template.md` 的对齐

模板文档中的每一列都能在本指南中找到字段级说明，对照速查：

| 模板列 | 本文件对应小节 |
| --- | --- |
| `METRICS 台账` 的所有技术列 | 第 4 节 `metrics` 怎么写 |
| `SCENES 台账.trigger_metric_ids / trigger_condition / start_node / is_default` | 第 5 节 `diagnosis_scenes` 怎么写 |
| `STEPS 台账.details_* / branch_*` | 第 6 节 `steps` 怎么写 |
| `details_params` 四种取值 | 第 6.2 节 `details.params` 参数绑定规则 |
| 并行 / 回路 / 兜底的引擎表达 | 第 6.3 节 `next` 规范 |
| 何时禁用字段 / 何时使用保留字段 | 第 4.2 节字段分三类 |

如果模板和本文件出现差异，以**本文件 + `rule_validator.py` 实际校验结果**为准，模板需要被同步修订。
