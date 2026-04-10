# reject_errors.diagnosis.json 执行规范（后端实现契约）

文档版本: 1.2  
适用范围: `config/reject_errors.diagnosis.json` + `src/backend/app/engine/diagnosis_engine.py`

**v1.1**：`next` 分支仅支持 **condition 表达式**（与 Python 式比较、区间写法一致）；**不再**使用 JSON 上的 `operator` / `limit` 字段（启动期校验会报错）。

**v1.2**：布尔连接词 **`AND` / `OR` 大小写不敏感**（仍须 **两侧空格**，如 ` and `）；加载 pipeline 时对 `next.condition` 做 **变量名可达性（Phase A）** 校验（见 §5.1）。

---

## 1. 目标

本规范定义 `reject_errors.diagnosis.json` 中 `diagnosis_scenes` / `steps` 的运行语义，确保规则配置与后端执行一致，避免“配置写得出、引擎跑不通”。

---

## 2. Step 结构定义

以示例节点为例（区间条件写在 **一条 `condition` 字符串** 中，中间变量用 `{name}`）：

```json
{
  "id": 32,
  "description": "计算Rw的mean值",
  "metric_id": "Rw",
  "details": [
    {
      "action": "calculate_monthly_mean_Rw",
      "params": { "Rw": "" },
      "results": { "mean_Rw": "" }
    }
  ],
  "next": [
    {
      "target": "45",
      "condition": "-300 < {mean_Rw} < 300"
    },
    {
      "target": "44",
      "condition": "else"
    }
  ]
}
```

---

## 3. 执行语义（强约束）

1. **`details` 串行执行**  
   `details` 数组中的动作按定义顺序执行，后一个动作可使用前一个动作写入的上下文变量。

2. **`action` 是函数名**  
   后端通过 action registry 按名称调用函数（见 `engine/actions/`）。

3. **`params` 是函数入参声明**  
   `params` 的 key 表示函数参数名，值按以下规则解析：  
   - `""` 或 `null`：从上下文读取同名变量  
   - `"{var_name}"`：从上下文读取指定变量  
   - 其他值：按常量字面量传入（如 `1`、`"normal_count"`）

4. **`results` 是函数出参声明**  
   动作函数返回 `dict`，其 key 应与 `results` 中声明字段一致；返回值会写回执行上下文，供后续 `details` 或 `next.condition` 使用。

5. **`next` 分支互相独立**  
   `next` 中各分支是并列条件，不依赖数组顺序，不允许通过“先写先匹配”表达优先级。

6. **每个 Step 只能选 1 条 `next`**  
   对同一个 step：  
   - 命中 1 条条件分支 -> 跳转该 `target`  
   - 命中 0 条 -> 走 `condition: else`（若存在）  
   - 命中 >1 条 -> 视为规则冲突（配置错误）

7. **`target` 是下一跳 step id**  
   引擎将 `target` 作为下一个要执行的 step。

8. **`condition` 表达式（唯一约定）**  
   - **变量**必须写在花括号内：`{mean_Rw}`、`{model_type}`（名称中可含空格、逗号等，与指标 id 一致）。  
   - **单比较**：`{Mwx_0} > 1.0001`、`{n_88um} <= 8`、`{model_type} == '88um'`。  
     支持的比较运算符与校验器一致：**`>` `<` `>=` `<=` `==` `!=`**（不使用单独一个 `=` 作为等于号）。  
   - **开区间（两常数夹变量）**：`-300 < {mean_Rw} < 300`；语义为左界 **严格小于** 变量 **严格小于** 右界（与引擎 `condition_evaluator` 一致）。  
   - **布尔组合**（场景触发等）：子句用 **` AND ` / ` OR `（两侧须有空格）** 连接；**大小写不敏感**（`and`/`or`/`And` 等与 `AND`/`OR` 等价），如 `{A} == true and {B} == true`。  
   - **结构化条件**（可选）：仍支持 JSON 对象形式的 `compare` / `all_of` / `any_of` / `not`（见 `condition_evaluator.validate_condition_definition`），用于复杂组合；`next` 上以字符串条件为主。  
   - **`next` 上禁止**再写 **`operator`**、**`limit`** 字段；区间、比较一律只写在 `condition` 中。

9. **`next` 为空即叶子**  
   当 `next: []` 或缺省且无后继时，节点视为终止节点；若同时具备 `result`/`results`（含 `rootCause`），则作为归因输出。

---

## 4. 后端实现映射

- 规则加载: `src/backend/app/engine/rule_loader.py`
- 决策执行: `src/backend/app/engine/diagnosis_engine.py`
- 条件解析/求值: `src/backend/app/engine/condition_evaluator.py`
- 启动期校验: `src/backend/app/engine/rule_validator.py`
- action 注册/调用: `src/backend/app/engine/actions/__init__.py`
- 内置动作: `src/backend/app/engine/actions/builtin.py`

函数扩展约定：

- 新 action 统一放在 `src/backend/app/engine/actions/` 目录
- 使用 `@register("函数名")` 注册
- `actions` 包会自动加载目录下模块，新增函数文件无需再改注册入口
- 函数返回 `dict`，由引擎按 `details.results` 声明字段写回上下文（未声明则全量回写）

---

## 5.1 启动期静态校验

`DiagnosisConfigStore` 加载 pipeline 时会执行静态校验（失败则服务无法启动）：

- step id 唯一性
- scene 的 `start_node` 必须存在
- `next.target` 必须指向存在的 step
- `action` 必须已注册
- `next` 上 **不得** 出现非空的 **`operator`** 或任意 **`limit`** 键（已废弃）
- `condition` 必须可被解析（字符串布尔式、单比较、区间、或结构化字典）
- 场景 `trigger_condition` 中引用的变量必须出现在对应 `metric_id` 中
- **Phase A（变量名）**：加载时传入 `metrics` 映射后，`next.condition` 中出现的 **`{var}` 名称** 须属于 **`metrics` 键 ∪ 任意 step 的 `metric_id` ∪ 任意 scene 的 `metric_id` ∪ 任意分支 `set` 的键 ∪ 任意 `details[].results` 声明的键**（仍无法保证与 action 实际返回值完全一致，属保守校验）

校验失败时会阻止服务启动，避免错误规则在运行时触发不可控行为。

---

## 5. 配置要求与校验建议

- 同一 step 的多个 `next` 条件应设计为互斥，避免多命中冲突。
- 每个非叶子 step 建议提供 `else`，保证异常输入可回退。
- `details.results` 与 action 返回字段需保持一致，避免下游条件引用不到变量。
- 条件中使用的变量名必须在上下文可解析（原始指标、action 输出、分支 `set` 注入）。
- **新增/修改规则时只改 `condition` 字符串**，保持与 `condition_evaluator` 支持的语法一致；勿再添加 `operator`/`limit`。

---

## 6. 对示例节点的执行结果说明

以 `id=32` 为例：

1) 执行 `calculate_monthly_mean_Rw(Rw)`  
2) 函数返回 `{"mean_Rw": ...}`，写入上下文  
3) 独立评估 `next`：  
- 若 `mean_Rw` 满足 `-300 < mean_Rw < 300` -> 跳到 `45`  
- 否则 -> 跳到 `44`  
4) 仅会进入一个目标节点
