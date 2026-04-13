# Config Guide

本文档面向第一次接手配置的协作者，目标不是罗列所有历史背景，而是让你能在较短时间内回答下面 4 个问题：

1. 运行时到底读哪些文件
2. 一个 pipeline 是怎么被加载和执行的
3. 每个字段应该怎么写，为什么要这样写
4. 改完之后怎么自检，哪些点最容易出错

适用对象：

- 需要新增一个诊断 pipeline 的开发者
- 需要修改当前 `reject_errors` 配置的开发者
- 需要排查“配置写了但引擎不按预期执行”的维护者

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

- `metrics`
  - 定义“变量从哪里来”
- `diagnosis_scenes`
  - 定义“什么情况下进入这条诊断”
- `steps`
  - 定义“进入后怎么一步一步走到结论”

运行链路大致如下：

1. `DiagnosisConfigStore` 读取 `diagnosis.json`
2. 根据 pipeline id 找到对应的 `<pipeline>.diagnosis.json`
3. 加载 `metrics / diagnosis_scenes / steps`
4. 启动期执行 `rule_validator` 静态校验
5. 运行时由 `DiagnosisEngine` 先匹配 scene，再取 metric，再按 `steps` 决策树往下走
6. 到叶子节点后返回 `rootCause / system / metrics`

如果只记一句话，可以记成：

> `metrics` 决定“拿什么数据”，`diagnosis_scenes` 决定“从哪棵树开始”，`steps` 决定“怎么走到结论”。

### 1.3 当前 `config/` 目录中文件的角色

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
  - 可选的指标备注补充文件
  - 若放在 `config/` 根目录，会被 `DiagnosisConfigStore` 读取并 merge 到 metrics 元数据
  - 适合放备注、状态、说明，不适合放核心执行逻辑
- `CONFIG_GUIDE.md`
  - 维护文档
  - 不参与运行时执行
- `trash/` 或业务侧临时文件
  - 仅作参考，不是运行时权威

> 注意：当前项目运行时的权威配置是 `diagnosis.json + <pipeline>.diagnosis.json`。  
> 历史上的 `metrics.json`、`rejection_rules.json`、`trash/*` 之类文件，若存在，也只是参考，不会被当前 structured pipeline 直接执行。

## 2. 修改配置时的总原则

### 2.1 权威顺序

如果多份文件之间内容不一致，按下面顺序处理：

1. 业务方最新口径
   - 例如最新规则表
   - 例如最新指标来源表、字段说明、DDL、样例数据
2. 当前运行权威文件
   - `diagnosis.json`
   - `reject_errors.diagnosis.json`
   - `ontology_api.diagnosis.json`
3. 执行契约与代码实现
   - `docs/stage3/rules_execution_spec.md`
   - `src/backend/app/diagnosis/config_store.py`
   - `src/backend/app/engine/rule_validator.py`
   - `src/backend/app/engine/metric_fetcher.py`
4. 历史参考文件
   - 历史导出的规则
   - `trash/` 目录下文件

### 2.2 当前项目中的硬规则

- 新增或修改 `reject_errors` 逻辑，必须改 `reject_errors.diagnosis.json`
- 新增或修改其他 pipeline，必须先在 `diagnosis.json` 中登记
- 不要只改业务原始规则文件，因为运行时不会直接执行它们
- `version` 当前只支持 major version = `3`
- `duration` 的单位是天，不是分钟，不是秒
- 对 MySQL / ClickHouse 的窗口型指标，运行时拿到的通常是“窗口值列表”，不是单个聚合值
- 是否取最近值、取均值、做计数，必须在 action 中显式完成
- `next` 分支里只写 `condition`，不要再写废弃的 `operator` / `limit`
- `trigger_condition` 只能引用本 scene 已声明的 `metric_id`
- `next.condition` 中出现的变量名，必须能被静态校验识别到

### 2.3 第一次接手时建议的阅读顺序

如果你刚接手某个 pipeline，建议按下面顺序阅读：

1. `config/diagnosis.json`
2. 目标 pipeline 文件，例如 `config/reject_errors.diagnosis.json`
3. `docs/stage3/rules_execution_spec.md`
4. `src/backend/app/diagnosis/config_store.py`
5. `src/backend/app/engine/rule_validator.py`
6. `src/backend/app/engine/metric_fetcher.py`

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

建议不要一上来就写 JSON，先在脑子里把下面 3 个问题想清楚：

1. 我要诊断的“入口”是什么
   - 某个 reject reason
   - 某组请求参数
   - 某个异常组合
2. 我要用到哪些原始变量
   - 来自 source record
   - 来自请求参数
   - 来自 MySQL / ClickHouse
   - 来自上一步 action 的中间结果
3. 我如何一步步收敛到结论
   - 先判断是否进入某场景
   - 再做必要的计算
   - 再按条件分支
   - 最后落到叶子节点输出结论

如果这 3 个问题还没想清楚，直接写配置通常会出现：

- metric 定义了一堆，但 scene 根本触发不了
- scene 触发了，但 step 中引用了不存在的变量
- 分支条件互相重叠，运行时冲突
- 本来应该在 action 做的聚合，错误地写成了 metric 本身

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
- `request_param`
  - 直接从接口请求参数取值
  - 典型例子：`ontology_api` 中的 `rotation_mean`
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

- 只有源表真实存在、且运行时上下文能提供取值的字段，才能写进 `keys`
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

### 4.8 新增一个 metric 时，先做这 4 个判断

先别急着抄现有配置，先判断这个变量属于哪一类：

1. 这个值是不是已经在故障主记录里
   - 是：优先用 `failure_record_field`
2. 这个值是不是由调用方通过接口参数传入
   - 是：用 `request_param`
3. 这个值是不是要从 MySQL / ClickHouse 按时间窗查出来
   - 是：用 `mysql_nearest_row` 或 `clickhouse_window`
4. 这个值是不是前一步 action 算出来的中间量
   - 是：用 `intermediate`

一个非常常见的错误是：

- 实际上需要“查窗口 + 算均值”的指标，被误写成单值 metric
- 实际上是 action 产物的变量，被误写成直接查库

记忆口诀：

> 原始值进 `metric`，聚合值进 `action`，最终结论落在叶子节点。

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
- 结构化条件对象
  - 例如 `{"all_of": [{"compare": {"left": "A", "operator": ">", "right": 1}}]}`

要求：

- 变量必须写成 `{变量名}`
- 同一 step 的多个条件应互斥
- 建议每个非叶子 step 都提供 `else`

### 6.5 Case 1：最小可运行 pipeline（适合新建 pipeline 时照着写）

下面这个例子接近 `ontology_api.diagnosis.json` 的风格，适合用来理解一个最小 structured pipeline 长什么样：

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
        { "target": "101", "condition": "{rotation_mean} > 300" },
        { "target": "199", "condition": "else" }
      ]
    },
    {
      "id": "101",
      "result": {
        "rootCause": "上片旋转机械超限",
        "system": "机械精度"
      }
    },
    {
      "id": "199",
      "result": {
        "rootCause": "未知原因",
        "system": "待分析"
      }
    }
  ]
}
```

这个 case 说明了 3 件事：

- `metric` 可以直接绑定请求参数
- `scene` 可以直接给一个默认入口
- `step` 不一定非要有 `details`，也可以只做条件跳转

### 6.6 Case 2：trigger-only 场景入口（适合 reject_errors）

下面是 `reject_errors` 里常见的写法：先用几个 `trigger_only` 指标判断“这条记录是否属于某个诊断场景”。

```json
{
  "metrics": {
    "Coarse Alignment Failed": {
      "source_kind": "failure_record_field",
      "field": "reject_reason",
      "transform": {
        "type": "equals",
        "value": 6
      },
      "role": "trigger_only"
    },
    "Mwx out of range,CGG6_check_parameter_ranges": {
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
        "Coarse Alignment Failed",
        "Mwx out of range,CGG6_check_parameter_ranges"
      ],
      "trigger_condition": [
        "{Coarse Alignment Failed} == true AND {Mwx out of range,CGG6_check_parameter_ranges} == true"
      ],
      "start_node": "1"
    }
  ]
}
```

这个 case 的重点是：

- `metric_id` 是“触发场景需要哪些变量”
- `trigger_condition` 只能引用 `metric_id` 里列出来的变量
- `trigger_only` 只负责“是否进入场景”，通常不参与详情展示

### 6.7 Case 3：带 action 的步骤（适合窗口值 -> 中间量 -> 分支）

下面这个例子展示了为什么“窗口 metric”和“聚合结果”要拆开写：

```json
{
  "id": 30,
  "description": "计算 Tx 月均值",
  "metric_id": "Tx_history",
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

这里每个字段的职责分别是：

- `metric_id`
  - 声明这个 step 主要依赖哪个输入指标
- `action`
  - 告诉引擎调用哪个已注册函数
- `params`
  - 把上下文变量绑定到 action 入参
- `results`
  - 声明 action 会往上下文里写回什么变量
- `next.condition`
  - 使用 action 输出的变量继续分支

如果你把这个例子理解透了，就能看懂大部分 `reject_errors` 中的建模链路。

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

1. 先确认业务最新口径
   - 表名 / 列名 / 时间列 / 过滤字段
   - 真实样例数据
   - 是否仍然满足当前 linking 假设
2. 再对照 `docs/stage3/rules_execution_spec.md` 与现有代码实现
3. 修改目标 `*.diagnosis.json`
4. 如果项目根目录启用了 `metrics_meta.yaml`，同步维护说明性字段
5. 必要时补测试

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

- 只改了业务原始规则文件，没改运行时的 `*.diagnosis.json`
- 在 `next` 分支上继续写 `operator` / `limit`
- 在 `trigger_condition` 中引用了没写进 `metric_id` 的变量
- 把 `duration` 当成分钟或秒
- 把窗口列表指标当成单值直接用
- 在 `linking.keys` 中写了源表或上下文里根本不存在的字段
- 把 `output_Tx/Ty/Rw` 错误改成直接来自源表
- 改了业务口径，但没同步运行时配置和测试

## 11. 当前维护建议

如果业务方后续继续提供最新规则，推荐按下面顺序维护：

1. 先确认业务方文件是最新版本
2. 先判断改动影响的是 `metrics`、`scene` 还是 `step`
3. 以目标 `*.diagnosis.json` 为运行时主文件进行修改
4. 若存在 `metrics_meta.yaml`，同步补备注或状态
5. 运行最小回归测试
6. 再交给内网或联调环境验证

这样可以避免出现“业务文件、参考文件、运行文件三份口径不一致”的问题。

## 12. 高风险点与后续修补计划

这一节不是“当前不能动”，而是提示后续维护时最容易出事故的地方，以及推荐的修补顺序。

### 12.1 高风险点一：文档口径与运行时实现存在漂移

现象：

- 某些旧文档仍在描述历史文件或旧结构
- 不同文档里对 `duration` 的单位可能出现不一致表述
- 有些说明仍把业务参考文件写成“好像会直接执行”

风险：

- 协作者会改错文件
- 联调时会以错误字段口径理解问题
- 会出现“明明按文档改了，系统却不生效”的错觉

修补计划：

1. 统一以 `diagnosis.json + <pipeline>.diagnosis.json` 作为权威口径
2. 统一文档中 `duration` 的单位表述为“天”
3. 在 README / HANDOVER / stage3 文档中明确区分“运行时权威文件”和“历史参考文件”

### 12.2 高风险点二：配置 DSL 已经很强，但缺少更友好的模板化入口

现象：

- 新人第一次写配置时，不容易分清 `metric`、`action`、`result` 的边界
- `intermediate` / `trigger_only` / `internal` 等角色容易混用

风险：

- 变量写到错误层级
- 本该在 action 做的计算，被写成 metric
- 场景能触发，但 step 跑不通

修补计划：

1. 后续补一份“最小 pipeline 模板”
2. 再补一份“窗口指标 + action 聚合模板”
3. 若继续演进，可把常用模板沉淀成 `config/examples/`

### 12.3 高风险点三：静态校验能挡住很多错误，但还挡不住全部语义错误

现象：

- `rule_validator` 能校验变量名、step id、target、action 注册情况
- 但它无法完全知道 action 的真实返回值是否和 `results` 一致
- 也无法完全保证多个分支在语义上真的互斥

风险：

- 配置能加载，但运行到某个 case 才暴露问题
- 分支冲突、变量为空、结果不落地等问题更偏运行时

修补计划：

1. 为关键 pipeline 增加“case 驱动”的契约测试
2. 对关键 step 增加示例输入 / 期望输出
3. 对高风险 action 增加单测，确保返回字段稳定

### 12.4 高风险点四：数据源字段和 linking 规则容易悄悄失真

现象：

- metric 很依赖 `table_name / column_name / time_column / linking.keys`
- 一旦数据表口径变化，配置表面上仍是合法 JSON
- 但运行时会出现查不到值、查错值、误命中窗口

风险：

- 诊断结果偏差但不一定直接报错
- 最难排查，因为看起来“配置没错、服务也没挂”

修补计划：

1. 每次涉及数据源字段变更时，强制复核样例数据
2. 优先补 `metric_fetcher` 层的回归测试
3. 对关键 metric 增加“示例记录 -> 预期取值”说明

### 12.5 高风险点五：`reject_errors` 配置已经偏复杂，继续堆规则会降低可维护性

现象：

- 既有 trigger scene，又有窗口指标，又有建模 action，又有中间变量
- 某些逻辑带明显历史兼容痕迹

风险：

- 改一个节点，可能影响下游多条路径
- 协作者不容易判断某变量是当前仍在使用，还是历史兼容残留

修补计划：

1. 对 `reject_errors.diagnosis.json` 做一次“按场景分段”的注释化整理
2. 把历史兼容变量、关键中间变量、输出变量分组标注
3. 后续如继续扩大规则规模，考虑拆分为更小的子场景或子模板

### 12.6 推荐的修补优先级

如果要按投入产出比来排优先级，建议顺序如下：

1. 先修文档口径
   - 保证所有人改的是对的文件
2. 再补配置模板和 case
   - 降低新增规则的学习成本
3. 再补配置契约测试
   - 防止“能加载但结果错”
4. 最后再做更深的结构整理
   - 例如拆分大配置、引入模板目录、加强可视化校验工具
