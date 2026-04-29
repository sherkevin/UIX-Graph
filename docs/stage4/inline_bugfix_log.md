# Stage4 内网诊断报错排查与修复记录

> 记录日期：2026-04-22  
> 场景：`/api/v1/reject-errors/{id}/metrics` 在内网对部分故障返回 `rootCause=\"上片工艺适应性问题\", system=待确认`，`trace` 收敛到 `99` 叶子；ClickHouse 日志出现 `Missing columns: 'phase', 'mark_pos_x', ...`。

## 1. 症状快照（来自内网运行日志）

- 接口 3 整体成功：`status=200`，`failure_id=67655971`，耗时约 48 秒。
- 诊断引擎匹配场景 `1001`（COWA 倍率超限），正常进入决策树。
- ClickHouse 查询报错抽样：`Missing columns: 'phase', 'mark_pos_x', 'mark_pos_y', 'ws_pos_x'`，均指向 `src.RPT_WAA_SET_OFL`。
- 部分指标取值为空，引擎最终输出 `rootCause=\"上片工艺适应性问题\" / system=待确认`，`trace` 末尾为 `99`（人工综合判定）。

## 2. 根因定位：配置与 stage4/prd.md 存在偏差

> 见 [`docs/stage4/prd.md`](./prd.md) 原文。

| 指标 | **PRD 要求** | **修复前配置** | 结论 |
|------|--------------|----------------|------|
| `ws_pos_x` / `ws_pos_y` | `src.RPT_WAA_V2_SET_OFL`（列名仍为 `WS_pos_x/y`） | `src.RPT_WAA_SET_UNION_VIEW` + `phase='1ST_COWA'` | 表名错（非 V2）；`phase` 过滤不在 PRD WS 流里 |
| `mark_pos_x` / `mark_pos_y` | 先查 `las.RPT_WAA_RESULT_OFL` 的 `mark_id`（`lot + wafer + chuck + phase='1ST_COWA'`，`row_id asc` 取前 4）→ 再查 `las.RTP_WAA_LOT_MARK_INFO_UNION_VIEW` 的 `mark_pos_x/y` | 直接查 `src.RPT_WAA_SET_OFL.mark_pos_x/y` | 表错，缺两步；`SET_OFL` 本身没有 `mark_pos_*` 和 `phase` 列，必然报 Missing columns |
| `Msx / Msy / e_ws_x / e_ws_y` | `lot + wafer + chuck` | `equipment + lot + chuck + wafer` | 多附加 `equipment`；不会报错，但可能过滤过紧，遗留为 follow-up |
| `D_x / D_y` | `datacenter.LO_wafer_result.wafer_load_offset_x/y`，`lot + wafer + chuck` | `source_kind=intermediate` 占位，**尚未接入** | 建模里按 0 处理，误差未显性暴露 |
| `Sx / Sy` | `env_id contains equipment` + `table_name='COMC'`，`data.static_wafer_load_offset.chuck_message[i].static_load_offset.x/y` | 与 PRD 一致 | OK |

代码本身并没有在一条 SQL 里同时要 5 列 —— `ClickHouseODS.query_metric_in_window` 每次只 `SELECT <column_name>`，外加 `WHERE` 里可能引用 `phase` 列；看起来像是“一个 OFL 表冒出五个缺列”，其实是 **4 个 metric 共享这张错误的表**。

### 2.1 Node 99 是怎么走到的？

`_build_model` 在 `ws_pos_*` / `mark_pos_*` 取不到数据时会回退 `[0.0, 0.0]`，`Msx/Msy` 取不到时回退 `1.0`，`e_ws_*`、`Sx/Sy`、`D_x/D_y` 回退 `0.0`。在这种全零输入下，`pinv` 解算的 `Mw` 在首个扰动就满足 `-20 < output_Mw < 20`，`n_88um = 1`，随后 Step 21 进入并行 Step 22/23/24，根据 `Tx / Ty / Rw` 源表值决定是否进入 Step 30/31/32，进而落到 `40 / 42 / 44`（“上片工艺适应性问题”）。

如果中间某一步 `n_88um`、`output_Mw` 因为空指标而条件求值都落到 `else`，就会推到 `99`（人工综合判定）。这也是为什么 `system` 是 `待确认`：`rootCause=\"上片工艺适应性问题\"` 的 `system` 在配置里本就为 `null`，然后被 `DiagnosisEngine` 的兜底逻辑改写成 `待确认`。

## 3. 本次修复范围（不等待业务确认，先做最小可复现 PRD 的修复）

### 3.1 配置层变更（`config/reject_errors.diagnosis.json`）

1. **`ws_pos_x` / `ws_pos_y`**：`table_name` → `src.RPT_WAA_V2_SET_OFL`；列名保持 `WS_pos_x / WS_pos_y`（大小写敏感）；**去掉** `phase='1ST_COWA'` 的 `linking.filters`（PRD 在 WS 段没有要求 phase，且 V2 视图是否有 `phase` 列未经内网确认）。
2. **新增 `mark_candidates`（`role: internal`）**：
   - 表：`las.RPT_WAA_RESULT_OFL`
   - 列：`mark_id`
   - `linking.keys` = `lot_id / wafer_id / chuck_id`
   - `linking.filters` = `phase='1ST_COWA'`
   - 作用：把当前 wafer 的 mark_id 列表（PRD 说“多了可能取 row_id asc 前 4”）暴露到上下文，供后续按 `in` 过滤。
3. **`mark_pos_x` / `mark_pos_y`**：`table_name` → `las.RTP_WAA_LOT_MARK_INFO_UNION_VIEW`；列保持小写 `mark_pos_x / mark_pos_y`；`linking.keys` = `lot_id`；`linking.filters` 追加 `{target: mark_id, operator: in, source: mark_candidates}`。
4. pipeline `version` 由 `3.0.0` 升至 `3.1.0`，让既有 `rejected_detailed_records` 缓存行（如仍在用）作废。

### 3.2 引擎层变更（`src/backend/app/engine/metric_fetcher.py`）

- 在 `fetch_all` 内新增 **拓扑排序**：扫描各 metric 的 `linking.keys / linking.filters` 中以 `source` 为名的引用；若引用的也是一个已知 metric_id，则把该 metric 排到引用方之前；环路降级为原序并打 warning。这样 `mark_pos_x` / `mark_pos_y` 的 `{mark_candidates}` 能在取数时已落到 `context`。
- 保留现有行为：未设依赖的 metric 保持原顺序。

### 3.3 本地 mock（`scripts/init_clickhouse_local.sql`）

- 追加 **`src.RPT_WAA_V2_SET_OFL`**、**`las.RPT_WAA_RESULT_OFL`**、**`las.RTP_WAA_LOT_MARK_INFO_UNION_VIEW`** 三张 mock 表；按现有锚点（`SSB8000 / lot=101 / chuck=1 / wafer=7 / phase='1ST_COWA'`）写入最小行数据，保证离线 e2e 不会因为“表不存在”挂掉。

### 3.4 环境开关

- 内网 **无 `rejected_detailed_records` 表**，继续由 `REJECTED_DETAILED_CACHE=0`（打包时默认注入）保证详情不读写该表；本次修复**不会**复活缓存依赖。

## 4. 暂不改、需业务侧确认的点

以下几项保留为 follow-up，一旦内网取得业务口径再落配：

1. `ws_pos_x / ws_pos_y` 是否需要 `phase` 过滤；如 V2 视图有 `phase` 列，可在 `linking.filters` 里再加一条。
2. `mark_candidates` 的“`row_id asc` 取前 4”是否必需——当前 `ClickHouseODS.query_metric_in_window` 只按时间近似度排序，没有强制取前 4。业务若需强约束，后续在 ODS 层增加 `order_by_asc + limit_rows` 支持。
3. `mark_pos_x / mark_pos_y` 的行对齐：修复后第一步按 `mark_id IN (m1..m4)` 拉回 4 行，不保证顺序与 `ws_pos_x/y` 对齐；当前 `_build_model` 只用前 2 点，暂不影响；若后续升到 4 点模型，需要显式按 `mark_id asc` 双边对齐。
4. `Msx / Msy / e_ws_x / e_ws_y` 是否去掉 `equipment` key。
5. `Sx / Sy` 的业务单位（`um` vs `m`）——`_build_model` 里与 `cwx/cwy`（米）直接相减后放大 1e6，若业务侧 `Sx` 实为 `um`，需要在 action 内做 1e-6 换算。当前未改，避免偏离线上行为。
6. `Mwx_0` 的 `[0.99998, 1.00002]` 区间是否是业务故意留的“盲区 → 人工处理”。
7. `D_x / D_y` 的 `LO_wafer_result` 表 schema 内网是否真已建成；可用时改为 `mysql_nearest_row`。

## 5. `build_88um_model` / `build_8um_model` 的完整建模流程

### 5.1 输入 / 输出

| ctx key | 语义 | 期望单位 | 数据源（配置后） |
|---------|------|----------|------------------|
| `ws_pos_x / ws_pos_y` | mark_scan 坐标 | m（字符串，代码侧 `float(...)`） | `src.RPT_WAA_V2_SET_OFL.WS_pos_x/y` |
| `mark_pos_x / mark_pos_y` | mark_data 坐标 | m | 两步查：`las.RPT_WAA_RESULT_OFL` → `las.RTP_WAA_LOT_MARK_INFO_UNION_VIEW.mark_pos_x/y` |
| `Msx / Msy` | 台对准建模结果 | 无量纲 | `src.RPT_WAA_SA_RESULT_OFL.ms_x/y` |
| `e_ws_x / e_ws_y` | WS 残差 | m | `src.RPT_WAA_SA_RESULT_OFL.e_ws_x/y` |
| `Sx / Sy` | 静态上片偏差 | 详见 §4.5 | `datacenter.mc_config_commits_history.data`（jsonpath） |
| `D_x / D_y` | 动态上片偏差 | m（或 um 需再确认） | **计划**：`datacenter.LO_wafer_result.wafer_load_offset_x/y` |
| `amplitude_um` | 扰动幅值 | um（`build_88um_model=88`, `build_8um_model=8`） | 代码内传 |

输出：

```python
{
  "output_Tx": (cwx - Sx - Dx) * 1e6,   # 展示 nm
  "output_Ty": (cwy - Sy - Dy) * 1e6,
  "output_Mw": mw * 1e6,                 # 展示 ppm
  "output_Rw": rw * 1e6,                 # 展示 μrad
  "n_88um": attempts,                    # 本次内部扰动次数（1..8）
  "model_history": [...]
}
```

### 5.2 解算步骤

1. 取 `ws_pos_*` 与 `mark_pos_*` 的前两个点分别组成 `mark_scan = [(ws_x[0], ws_y[0]), (ws_x[1], ws_y[1])]` 与 `mark_data = [(mk_x[0], mk_y[0]), (mk_x[1], mk_y[1])]`；若不足 2 点，按首值复制。
2. 按固定顺序最多扰动 8 次（同一 mark 的 x/y 正负 4 组，第 0 / 第 1 号点各 4 组）：

   ```
   (mark_idx, axis, delta_um) in 顺序：
     (0, x, +A)  (0, x, -A)
     (0, y, +A)  (0, y, -A)
     (1, x, +A)  (1, x, -A)
     (1, y, +A)  (1, y, -A)
   ```

   每次对 `mark_scan[i][axis]` 加 `delta_um * 1e-6`，然后代入 `_run_model_once`。

3. `_solve_b_wa_4param_pinv`：构造 8×4 线性系统：

   ```
   [ 1 0  md_x -md_y ]   [BB_Cwx]
   [ 0 1  md_y  md_x ] · [BB_Cwy] = [ ms_x*Msx - e_wsx - md_x ]
                         [BB_Mw ]   [ ms_y*Msy - e_wsy - md_y ]
                         [BB_Rw ]
   ```

   两点贡献各两行；用 `numpy.linalg.pinv` 解得 `(cwx, cwy, mw, rw)`，单位米 / 弧度。

4. 一次扰动结束立刻算出 `output_Tx/Ty/Mw/Rw` 并记入 `history`；若 `-20 < output_Mw < 20`（ppm）提前停止；否则继续下一次扰动，总循环上限 8 次。

### 5.3 88um / 8um 的唯一差异

仅 `amplitude_um` 不同：

| action | amplitude | 典型适用场景 |
|--------|-----------|--------------|
| `build_88um_model` | **88 μm** | `Mwx_0 > 1.0001` 或 `Mwx_0 < 0.9999`（倍率偏离较大，需大幅扰动） |
| `build_8um_model` | **8 μm** | `1.00002 < Mwx_0 < 1.0001` 或 `0.9999 < Mwx_0 < 0.99998`（倍率偏离较小，细调） |

### 5.4 外层决策树回路

- Step 1 → 10（88um）或 11（8um）或 99（`Mwx_0` 落在 [0.99998, 1.00002] 盲区）。
- Step 10/11 → Step 20（检查 `n_88um`）。`n_88um <= 8` → Step 21；`> 8` → Step 99；`else` → 99。
- Step 21：`-20 < output_Mw < 20` → 并行 Step 22/23/24（Tx/Ty/Rw 各自走自家判断）；否则 → `continue_model`。
- `continue_model`：`n_88um >= 8` → 99；否则 → `continue_model_dispatch` 按 `model_type` 跳回 10 / 11 再来一轮。
- Step 22/23/24 → 若正常 → `normal_count + 1` → Step 50 → 99；若异常 → Step 30/31/32 计算 30 天均值，再分支到 `40/41/42/43/44/45` 中的叶子结论。

### 5.5 正常 / 异常阈值（决策树）

| 指标 | 正常区间 | 触发叶子（异常） |
|------|----------|------------------|
| `output_Mw` | `(-20, 20)` ppm | 超出 → `continue_model` 或 99 |
| `output_Tx` / `output_Ty` | `(-20, 20)` μm | 超出 → 30 / 31，再结合 `mean_Tx / mean_Ty` 决定 `40 / 41` 或 `42 / 43` |
| `output_Rw` | `(-300, 300)` μrad | 超出 → 32 → 结合 `mean_Rw` 决定 `44 / 45` |
| `n_88um` | `<= 8` | 超过 → 99 |

### 5.6 已知不一致点（待业务侧最终裁决）

- `continue_model` 分支还能让外层再触发 `build_*um_model`，而 `_build_model` 内部已经自己跑满 8 次扰动；这意味着决策树外层循环会叠加内部循环，容易让“8 次用尽”的业务语义歧义。**暂不改**；若业务明确“8 次指内部 ops 用尽”，建议删除 `continue_model → continue_model_dispatch → 10/11` 这条回路。
- PRD 描述 `4 点 mark_scan + 4 点 mark_data`，代码侧当前只拿前 2 点完成 `pinv`。**暂不改**；若业务确认需要 4 点，将 `_build_model` 的 `for i in range(2)` 扩到 4，同时确保 `ws_pos_*` / `mark_pos_*` 能返回 4 个值且顺序由 `mark_id` 对齐。

## 6. 内网验证步骤建议

1. 解压新 zip → `src/backend/.env` 保持 `REJECTED_DETAILED_CACHE=0`。
2. `start_UIX.bat` 起服务；触发 `/api/v1/reject-errors/{id}/metrics`（用出现过错误那条 `failure_id`）。
3. 观察 `logs/launcher-*.log` 与后端 `detail_trace` 日志：
   - 应看到 `[取数:clickhouse] metric=ws_pos_x table=src.RPT_WAA_V2_SET_OFL` 与 `[取数:clickhouse] metric=mark_candidates table=las.RPT_WAA_RESULT_OFL`，不再出现 `RPT_WAA_SET_OFL` + `mark_pos_x/y`。
   - `mark_pos_x / mark_pos_y` 应来自 `las.RTP_WAA_LOT_MARK_INFO_UNION_VIEW`，`linking` 里携带 `mark_id IN (...)`。
4. 若仍有 Missing columns，按报错表名/列名定位到本文档“暂不改、需业务侧确认的点”中的对应项，与业务方对齐后补回配置。
