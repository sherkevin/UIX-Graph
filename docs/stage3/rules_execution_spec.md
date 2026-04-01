# rules.json 执行规范（后端实现契约）

文档版本: 1.0  
适用范围: `config/rules.json` + `src/backend/app/engine/diagnosis_engine.py`

---

## 1. 目标

本规范定义 `rules.json` 的运行语义，确保规则配置与后端执行一致，避免“配置写得出、引擎跑不通”。

---

## 2. Step 结构定义

以示例节点为例：

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
      "condition": "-300<{mean_Rw}<300",
      "operator": "between",
      "limit": [-300, 300]
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

8. **`condition` 中 `{}` 是变量引用**  
   例如 `-300<{mean_Rw}<300` 中 `{mean_Rw}` 表示从当前上下文取变量 `mean_Rw`。
   - 支持两种写法：  
     - 结构化写法：`operator + limit`（推荐）  
     - 表达式写法：仅 `condition`（如 `{model_type} == '88um'`、`{normal_count}==3`）

9. **`next` 为空即叶子**  
   当 `next: []` 或缺省且无后继时，节点视为终止节点；若同时具备 `result`/`results`（含 `rootCause`），则作为归因输出。

---

## 4. 后端实现映射

- 规则加载: `src/backend/app/engine/rule_loader.py`
- 决策执行: `src/backend/app/engine/diagnosis_engine.py`
- action 注册/调用: `src/backend/app/engine/actions/__init__.py`
- 内置动作: `src/backend/app/engine/actions/builtin.py`

函数扩展约定：

- 新 action 统一放在 `src/backend/app/engine/actions/` 目录
- 使用 `@register("函数名")` 注册
- `actions` 包会自动加载目录下模块，新增函数文件无需再改注册入口
- 函数返回 `dict`，由引擎按 `details.results` 声明字段写回上下文（未声明则全量回写）

---

## 5.1 启动期静态校验

`RuleLoader` 在加载 `rules.json` 时会执行静态校验（默认严格模式）：

- step id 唯一性
- scene 的 `start_node` 必须存在
- `next.target` 必须指向存在的 step
- `action` 必须已注册
- `condition` 表达式必须可解析
- `operator` 必须在支持列表中且配置完整

校验失败时会阻止服务启动，避免错误规则在运行时触发不可控行为。

---

## 5. 配置要求与校验建议

- 同一 step 的多个 `next` 条件应设计为互斥，避免多命中冲突。
- 每个非叶子 step 建议提供 `else`，保证异常输入可回退。
- `details.results` 与 action 返回字段需保持一致，避免下游条件引用不到变量。
- 条件中使用的变量名必须在上下文可解析（原始指标、action 输出、分支 `set` 注入）。
- 新增规则时优先使用 `operator + limit`，便于静态校验；表达式写法用于兼容历史配置。

---

## 6. 对示例节点的执行结果说明

以 `id=32` 为例：

1) 执行 `calculate_monthly_mean_Rw(Rw)`  
2) 函数返回 `{"mean_Rw": ...}`，写入上下文  
3) 独立评估 `next`：  
- 若 `mean_Rw` 在 `(-300, 300)` -> 跳到 `45`  
- 否则 -> 跳到 `44`  
4) 仅会进入一个目标节点

