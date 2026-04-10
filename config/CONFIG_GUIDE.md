# Config Guide

本文档说明 `config/` 目录下各配置文件的职责、当前运行时如何加载配置，以及新增/修改一份诊断配置时应遵循的规范。

适用对象：

- 需要新增一个诊断 pipeline 的开发者
- 需要修改当前 `reject_errors` 配置的开发者
- 需要把业务侧最新规则同步到当前运行配置的维护者

## 1. 当前哪些配置真正生效

### 1.1 运行时权威文件

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

### 1.2 当前 `config/` 目录中文件的角色

- `diagnosis.json`
  - 诊断 pipeline 索引
  - 运行时读取
- `reject_errors.diagnosis.json`
  - `reject_errors` 的权威运行配置
  - 运行时读取
- `ontology_api.diagnosis.json`
  - `ontology_api` 的权威运行配置
  - 运行时读取
- `connections.json`
  - 数据库连接配置
  - 运行时读取
- `metrics_meta.yaml`
  - 指标补充说明/备注
  - 会被 `DiagnosisConfigStore` 读取并合并到 metrics 元数据
  - 建议主要放说明性内容，不要把核心执行逻辑只写在这里
- `metrics.json`
  - 业务/历史参考映射
  - 当前诊断引擎不直接以它为权威配置
  - 但当业务侧提供最新指标来源时，应同步维护，避免和运行配置打架
- `rejection_rules.json`
  - 业务侧原始规则参考
  - 当前诊断引擎不直接执行它
  - 用来和 `reject_errors.diagnosis.json` 做对齐

## 2. 修改配置时的总原则

### 2.1 权威顺序

如果多份文件之间内容不一致，按下面顺序处理：

1. 业务方最新文件
   - 例如 `rejection_rules.json`
   - 例如业务最新的 `metrics.json` / `metrics_meta.yaml`
2. 当前运行权威文件
   - `reject_errors.diagnosis.json`
3. 参考文档
   - `docs/intranet/schema_reference.md`
   - `docs/stage3/rules_execution_spec.md`

### 2.2 当前项目中的硬规则

- 新增或修改 `reject_errors` 逻辑，必须改 `reject_errors.diagnosis.json`
- 不要只改 `rejection_rules.json`，因为运行时不会直接执行它
- 如果业务来源表、列、时间列、链接键发生变化，应同步维护：
  - `reject_errors.diagnosis.json`
  - `metrics.json`
  - `metrics_meta.yaml`
- linking 里的键只能写 `reference_schema` 里明确存在的字段
- `duration` 的单位是天，不是分钟，不是秒
- 对 MySQL/ClickHouse 的窗口型指标，运行时保留的是窗口值列表
- 是否取最近值、取均值、做计数，必须在 action 中显式完成

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

### 4.2 常用字段说明

- `description`
  - 中文说明
- `data_type`
  - 可选
  - 常见值：`int`、`float`、`string`、`bool`
- `unit`
  - 展示单位
- `source_kind`
  - 数据来源类型
- `table_name`
  - 来源表，ClickHouse 需要写完整库表名
- `column_name`
  - 查询列名
- `time_column`
  - 时间列名
- `equipment_column`
  - 设备列名
- `extraction_rule`
  - 正则或 JSON 提取规则
- `duration`
  - 时间窗口，单位是天
- `role`
  - 指标角色

### 4.3 `source_kind` 规范

当前常用值：

- `failure_record_field`
  - 直接从故障主记录取值
  - 典型例子：`Tx`、`Ty`、`Rw`
- `clickhouse_window`
  - 从 ClickHouse 按时间窗口查询
  - 返回提取后的窗口值列表
- `mysql_nearest_row`
  - 从 MySQL 按时间窗口查询
  - 返回提取后的窗口值列表
- `intermediate`
  - 中间变量，不直接查库
  - 典型例子：`output_Mw`、`mean_Tx`、`n_88um`

### 4.4 `role` 规范

常用值：

- `diagnostic`
  - 诊断指标，默认值
- `trigger_only`
  - 仅用于触发场景，不在详情中展示
- `internal`
  - 内部指标，不在详情中展示
  - 例如窗口历史列表：`Tx_history`

### 4.5 `linking` 规范

结构：

```json
"linking": {
  "mode": "exact_keys",
  "keys": [
    { "target": "equipment", "source": "equipment" },
    { "target": "lot_id", "source": "lot_id" },
    { "target": "chuck_id", "source": "chuck_id" },
    { "target": "wafer_id", "source": "wafer_id" }
  ],
  "filters": []
}
```

说明：

- `mode`
  - `time_window_only`
    - 只按时间窗口查
  - `exact_keys`
    - 除时间窗口外，还必须带强键过滤
- `keys`
  - 精确锁定键
- `filters`
  - 额外过滤条件

硬约束：

- 只有 `reference_schema` 里确认存在的字段，才能写进 `keys`
- 目标原则是尽量用满 `equipment + chuck + lot + wafer + time`
- 如果业务侧最新口径变了，必须同步改这里

### 4.6 `duration` 规范

- 单位固定为天
- 常规指标默认 `7`
- 月均值相关的历史窗口指标通常为 `30`

例如：

```json
"Tx_history": {
  "duration": "30",
  "role": "internal"
}
```

### 4.7 `extraction_rule` 规范

当前支持两种主要形式：

- `regex:<pattern>`
- `json:<key>`

说明：

- 正则提取在取数阶段执行，不在 action 里执行
- 对窗口型指标，会先对窗口内每条原始值做提取，再形成列表

## 5. `diagnosis_scenes` 怎么写

示例：

```json
{
  "id": 1001,
  "module": "COWA",
  "phenomenon": "倍率超限",
  "description": "COWA倍率超限，补偿建模",
  "metric_id": [
    "Coarse Alignment Failed",
    "Mwx out of range,CGG6_check_parameter_ranges"
  ],
  "trigger_condition": [
    "{Coarse Alignment Failed} == true AND {Mwx out of range,CGG6_check_parameter_ranges} == true"
  ],
  "start_node": "1"
}
```

规则：

- `metric_id`
  - 场景触发时需要的指标集合
- `trigger_condition`
  - 只能引用本场景 `metric_id` 中已声明的指标
- `start_node`
  - 必须指向存在的 step id

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
    {
      "target": "41",
      "condition": "-2 < {mean_Tx} < 2"
    },
    {
      "target": "40",
      "condition": "else"
    }
  ]
}
```

### 6.2 `details` 规范

- `action`
  - 对应 `src/backend/app/engine/actions/` 中已注册的函数名
- `params`
  - 参数绑定规则：
    - `""` 或 `null`：取同名上下文变量
    - `"{var_name}"`：取指定上下文变量
    - 其他：按字面量传入
- `results`
  - 声明 action 输出字段

### 6.3 `next` 规范

- 每个分支必须有 `target`
- `condition` 使用表达式字符串
- `else` 表示兜底分支

当前结构化规则里，`next` 上已经废弃：

- `operator`
- `limit`

不要再在 `reject_errors.diagnosis.json` 里新增这两个字段。

### 6.4 条件表达式怎么写

支持：

- 单比较
  - `{n_88um} <= 8`
  - `{model_type} == '88um'`
- 区间
  - `-20 < {output_Mw} < 20`
- 布尔组合
  - `{A} == true AND {B} == true`

要求：

- 变量必须写成 `{变量名}`
- 同一 step 的多个条件应互斥
- 建议每个非叶子 step 都提供 `else`

## 7. 当前 `reject_errors` 的特殊约定

### 7.1 不要回退这些增强

当前 `reject_errors.diagnosis.json` 有几处是为了兼容当前实现而保留的，修改时不要轻易回退：

- `step 1` 的 `select_window_metric`
  - 因为 `Mwx_0` 现在是窗口列表
- `Tx_history / Ty_history / Rw_history`
  - 因为月均值现在必须从窗口列表计算
- `continue_model` + `continue_model_dispatch`
  - 这是为避免建模路径死循环做的保护
- `n_88um`
  - 这是建模次数控制变量

### 7.2 `output_*` 的规范

以下指标应视为 action 产物：

- `output_Mw`
- `output_Tx`
- `output_Ty`
- `output_Rw`

不要把它们误改成直接从故障主记录取值，除非业务明确要求变更计算口径。

## 8. 修改现有配置的推荐流程

### 场景 A：业务方只改了路径逻辑

例如：

- 场景触发条件变了
- 分支判断变了
- 根因文案变了

修改步骤：

1. 改 `reject_errors.diagnosis.json`
2. 跑规则校验
3. 跑路径相关测试

### 场景 B：业务方改了指标来源

例如：

- 表名变了
- 列名变了
- 时间列变了
- linking key 变了

修改步骤：

1. 先确认业务最新文件
   - `rejection_rules.json`
   - `metrics.json`
   - `metrics_meta.yaml`
2. 再对照 `docs/intranet/schema_reference.md`
3. 修改 `reject_errors.diagnosis.json`
4. 同步维护 `metrics.json`
5. 同步维护 `metrics_meta.yaml`
6. 必要时补测试

### 场景 C：新增一个 pipeline

步骤：

1. 在 `config/` 下新增 `<pipeline>.diagnosis.json`
2. 在 `diagnosis.json` 的 `pipelines` 中登记：

```json
"my_pipeline": {
  "mode": "structured",
  "config_file": "my_pipeline.diagnosis.json"
}
```

3. 保证 `version` 为 `3.x`
4. 保证 `steps` / `scenes` 能通过静态校验

## 9. 修改后怎么验证

至少执行下面几类验证：

### 9.1 静态校验

推荐：

```bash
cd src/backend
python -m pytest tests/test_rules_validator.py
```

### 9.2 路径条件校验

推荐：

```bash
cd src/backend
python -m pytest tests/test_rules_engine_conditions.py
```

### 9.3 action 计算校验

推荐：

```bash
cd src/backend
python -m pytest tests/test_rules_actions_implementation.py
```

### 9.4 指标取数回归

如果改了表名、列名、时间列、窗口逻辑：

```bash
cd src/backend
python -m pytest tests/test_metric_fetcher_window.py
```

## 10. 常见错误

- 只改了 `rejection_rules.json`，没改 `reject_errors.diagnosis.json`
- 在 `next` 分支上继续写 `operator` / `limit`
- 在 `trigger_condition` 中引用了没写进 `metric_id` 的变量
- 把 `duration` 当成分钟或秒
- 把窗口列表指标当成单值直接用
- 在 `linking.keys` 中写了 `reference_schema` 里根本不存在的字段
- 把 `output_Tx/Ty/Rw` 错误改成直接来自源表
- 改了业务侧 `metrics.json`，但没同步运行时配置

## 11. 当前维护建议

如果业务方后续继续提供最新规则，推荐按下面顺序维护：

1. 先确认业务方文件是最新版本
2. 以 `reject_errors.diagnosis.json` 为运行时主文件进行修改
3. 同步 `metrics.json`
4. 同步 `metrics_meta.yaml`
5. 运行最小回归测试
6. 再打包给内网验证

这样可以避免出现“业务文件、参考文件、运行文件三份口径不一致”的问题。
