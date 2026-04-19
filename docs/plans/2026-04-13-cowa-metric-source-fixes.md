# COWA Metric Source Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align the `reject_errors` COWA metric sources, table mappings, linking filters, and extraction logic with the latest business issue list.

**Architecture:** Keep the current structured pipeline (`config/reject_errors.diagnosis.json`) as the source of truth for metric metadata, but extend `MetricFetcher` only where the business requirements cannot be represented by the current filter/extraction model. Prefer config-only fixes first; add code support only for missing filter semantics (`contains` / `IN` / context-derived filters / nested JSON extraction) that the business list explicitly requires.

**Tech Stack:** FastAPI, structured diagnosis config JSON, `MetricFetcher`, MySQL, ClickHouse, pytest, local seeded DB fixtures.

---

## Current Reading Summary

The business issue list maps to these existing areas:

- Runtime config: `config/reject_errors.diagnosis.json`
- Metric source plumbing: `src/backend/app/engine/metric_fetcher.py`
- COWA model inputs and aliases: `src/backend/app/engine/actions/builtin.py`
- Existing tests:
  - `src/backend/tests/test_diagnosis_config_store.py`
  - `src/backend/tests/test_metric_fetcher_window.py`
  - `src/backend/tests/test_rules_actions_implementation.py`
  - `src/backend/tests/test_docker_seed_alignment.py`

Important current limitations discovered:

- `MetricFetcher` filter operators only support `=`, `!=`, `>`, `>=`, `<`, `<=`
- Config can express fixed filters, but cannot express SQL `LIKE` / `contains`
- Config cannot currently express `IN (...)`
- Linking/filter resolution is based on source record + params; it does **not** currently support “use the result of a previously fetched metric as a later filter value”
- `Sx` / `Sy` current `json:Sx` extraction is too shallow for the business JSON path requirement
- `D_x` / `D_y` are currently `intermediate`, not DB-backed metrics
- `Tx` / `Ty` / `Rw` are currently direct `failure_record_field`, not DB lookups

## Business Items by Implementation Type

### Pure Config Changes

- `WS_pos_x`
- `WS_pos_y`

Likely config-only if business confirms current key set remains valid:

- table name -> `src.RPT_WAA_SET_UNION_VIEW`
- add fixed filter -> `phase = '1ST_COWA'`

### Config + Fetcher Capability Changes

- `mark_pos_x`
- `mark_pos_y`
- `Sx`
- `Sy`
- `D_x`
- `D_y`
- `Tx`
- `Ty`
- `Rw`

### Business Confirmation Required Before Safe Implementation

- `mark_id` derivation path and final multiplicity (the issue list says “mark_id 应该有 4 个值”)
- Missing disambiguation condition for `Msx` / `Msy` / `e_ws_x` / `e_ws_y`
- `LO_wafer_result` physical table naming rule by machine / suffix
- `datacenter.lo_batch_equipment_performance_temp` suffix strategy and whether time column is `lot_start_time` or `lot_end_time`
- Whether `Sx` / `Sy` should be renamed to `S_x` / `S_y` at config/API/UI level, or only tolerated as aliases in model code

## Recommended Delivery Order

1. Land all safe config-only fixes first
2. Add missing fetcher capabilities with tight tests
3. Implement DB-backed replacements for currently stubbed/intermediate metrics
4. Re-run seeded alignment tests and browser verification on a real reject case
5. Only then reconcile any naming changes (`Sx` -> `S_x`) if the business explicitly wants API/display changes

### Task 1: Lock Business Contract and Collect Sample Rows

**Files:**
- Modify: `docs/plans/2026-04-13-cowa-metric-source-fixes.md`
- Inspect: `config/reject_errors.diagnosis.json`
- Inspect: `src/backend/app/engine/metric_fetcher.py`
- Inspect: `src/backend/app/engine/actions/builtin.py`

**Step 1: Build a metric-by-metric decision table**

Document, for each metric in the issue list:

- target source table
- target column
- required key filters
- required fixed filters
- required time window rule
- extraction shape
- whether current config can already express it

**Step 2: Query one real sample row for each unresolved source**

Run targeted DB queries for:

- `src.RPT_WAA_SET_UNION_VIEW`
- `las.RTP_WAA_LOT_MARK_INFO_UNION_VIEW`
- `src.RPT_WAA_SA_RESULT_OFL` (or actual source used now)
- `datacenter.mc_config_commits_history`
- `LO_wafer_result*`
- `datacenter.lo_batch_equipment_performance_temp*`

Expected outcome:

- confirm actual column names
- confirm duplicate row shape
- confirm whether suffix tables exist

**Step 3: Freeze blockers**

Before implementation, stop and confirm all open business questions listed in the “Open Questions” section below.

### Task 2: Update Safe Config-Only Metrics

**Files:**
- Modify: `config/reject_errors.diagnosis.json`
- Test: `src/backend/tests/test_diagnosis_config_store.py`

**Step 1: Update `WS_pos_x`**

- change `table_name` to `src.RPT_WAA_SET_UNION_VIEW`
- preserve current key filters unless business says `chuck_id` / `equipment` should be removed
- add fixed filter for `phase = '1ST_COWA'`

**Step 2: Update `WS_pos_y`**

- same changes as `WS_pos_x`

**Step 3: Update `_note` comments**

- keep config comments aligned with the new business source table names

**Step 4: Add config assertions**

Extend `test_diagnosis_config_store.py` to assert:

- new table names
- presence of `phase` filter

### Task 3: Extend MetricFetcher Filter Semantics

**Files:**
- Modify: `src/backend/app/engine/metric_fetcher.py`
- Test: `src/backend/tests/test_metric_fetcher_window.py`
- Test: `src/backend/tests/test_diagnosis_config_store.py`

**Step 1: Add support for fixed literal filters already expressible in config**

No behavior change needed if `value` filters already work; verify with tests.

**Step 2: Add `contains` / `LIKE` style filter support**

Needed for:

- `env_id` contains equipment name

Recommended implementation:

- extend `linking.operator` support to include `contains`
- translate to SQL `LIKE '%value%'` for MySQL
- translate to ClickHouse equivalent only if required by actual metrics

**Step 3: Add `IN` filter support**

Needed if `mark_id` truly maps to multiple candidate values.

Recommended implementation:

- support `operator: "in"` with list-valued `value`
- emit parameterized `IN (...)`

**Step 4: Add context-derived filter support**

Needed if `mark_id` must come from a previous metric or earlier derived context.

Recommended implementation:

- allow `linking.filters[*].source` to resolve from already available metric context, not only source record / request params
- plumb current resolved metric values into `_build_metric_filters(...)`

**Step 5: Add tests**

Add focused tests for:

- exact literal filter
- `contains`
- `in`
- context-derived filter resolution

### Task 4: Rewire `mark_pos_x` / `mark_pos_y`

**Files:**
- Modify: `config/reject_errors.diagnosis.json`
- Modify: `src/backend/app/engine/metric_fetcher.py`
- Test: `src/backend/tests/test_docker_seed_alignment.py`
- Test: new `src/backend/tests/test_metric_fetcher_mark_filters.py` (if needed)

**Step 1: Update source table**

- switch to `las.RTP_WAA_LOT_MARK_INFO_UNION_VIEW`
- update `_note`

**Step 2: Replace current exact-key model**

Current config uses:

- equipment
- lot_id
- chuck_id
- wafer_id

Business wants:

- `lot_id = ?`
- `mark_id = ?` (possibly multiple values)

**Step 3: Implement only after mark_id contract is confirmed**

Possible implementation options:

- if `mark_id` is a fixed 4-value set -> config + `IN`
- if `mark_id` depends on `WS_pos_x` / `WS_pos_y` query results -> code support for context-derived filter or a dedicated action/metric stage

**Step 4: Re-run model alignment test**

`mark_pos_x` / `mark_pos_y` feed directly into `_build_model(...)`, so validate downstream output values, not only raw fetch.

### Task 5: Fix `Msx` / `Msy` / `e_ws_x` / `e_ws_y`

**Files:**
- Modify: `config/reject_errors.diagnosis.json`
- Possibly modify: `src/backend/app/engine/metric_fetcher.py`
- Test: `src/backend/tests/test_docker_seed_alignment.py`

**Step 1: Keep current table unless business changes it**

The issue list says table name does not need to change.

**Step 2: Review duplicate-row disambiguation**

Business explicitly says current filters return two rows and “缺条件”.

Current config already filters by:

- equipment
- lot_id
- chuck_id
- wafer_id

So one more distinguishing condition is missing.

**Step 3: Do not implement until the missing discriminator is identified**

Likely candidates:

- phase / recipe / model type / result type / commit state

### Task 6: Implement `Sx` / `Sy` New Extraction Rule

**Files:**
- Modify: `config/reject_errors.diagnosis.json`
- Modify: `src/backend/app/engine/metric_fetcher.py`
- Possibly modify: `src/backend/app/engine/actions/builtin.py`
- Test: `src/backend/tests/test_metric_fetcher_window.py`
- Test: `src/backend/tests/test_docker_seed_alignment.py`

**Step 1: Add source filters**

Business rule:

- `table_name` column = `COMC`
- `env_id` contains equipment name

Current config can represent the first as a fixed filter, but not the second without `contains` support.

**Step 2: Add nested JSON extraction**

Business path:

- `data.static_wafer_load_offset.chuck_message[n].static_load_offset.x`
- `data.static_wafer_load_offset.chuck_message[n].static_load_offset.y`

Need extraction keyed by `chuck_id`:

- `chuck_id=1` -> `chuck_message[0]`
- `chuck_id=2` -> `chuck_message[1]`

**Step 3: Keep current public names first**

Do not rename to `S_x` / `S_y` in the first implementation pass.

Reason:

- current actions already tolerate aliases via:
  - `ctx.get("Sx")`
  - `ctx.get("S_x")`
  - `ctx.get("Sy")`
  - `ctx.get("S_y")`

Safe path:

- first make fetch correct under `Sx` / `Sy`
- only rename if business explicitly needs external naming to change

### Task 7: Convert `D_x` / `D_y` from Placeholder Intermediate to Real DB Metrics

**Files:**
- Modify: `config/reject_errors.diagnosis.json`
- Possibly modify: `src/backend/app/engine/metric_fetcher.py`
- Test: `src/backend/tests/test_rules_actions_implementation.py`
- Test: `src/backend/tests/test_docker_seed_alignment.py`

**Step 1: Replace `source_kind: intermediate`**

Business wants:

- description: 动态上片偏差 x/y
- MySQL source
- table: `LO_wafer_result` or `LO_wafer_result_<machine?>`
- columns:
  - `wafer_load_offset_x`
  - `wafer_load_offset_y`
- filters:
  - `lot_id`
  - `wafer_id`
  - `chuck_id`

**Step 2: Confirm physical table naming**

Blocked until business confirms:

- exact table name
- whether table suffix is fixed or equipment-dependent

**Step 3: Validate downstream model math**

`D_x` / `D_y` are direct model inputs, so rerun action-level alignment tests after the source switch.

### Task 8: Rewire `Tx` / `Ty` / `Rw` to Performance Temp Table

**Files:**
- Modify: `config/reject_errors.diagnosis.json`
- Possibly modify: `src/backend/app/engine/metric_fetcher.py`
- Test: `src/backend/tests/test_diagnosis_config_store.py`
- Test: `src/backend/tests/test_docker_seed_alignment.py`
- Test: `src/backend/tests/test_reject_error_detail.py`

**Step 1: Replace `failure_record_field` source**

Current state:

- `Tx` / `Ty` / `Rw` come directly from source record columns

Business wants:

- source table `datacenter.lo_batch_equipment_performance_temp`
- maybe suffix tables such as `_20230530`
- filter by equipment
- use reject time as anchor
- search backward one month

**Step 2: Decide whether these are nearest-row or window-list metrics**

Open design decision:

- If they should be single values -> `mysql_nearest_row`
- If they should be historical arrays -> separate current-value metric plus `_history`

Recommended approach:

- keep `Tx_history` / `Ty_history` / `Rw_history` as history
- make `Tx` / `Ty` / `Rw` the “current/nearest row” values from the temp table

**Step 3: Add table resolver if suffix tables are real**

If temp tables are partitioned by suffix, config alone is not enough. Add a small resolver in fetcher/ODS instead of hardcoding one table name per date.

### Task 9: Regression, Real-Data Verification, and Docs

**Files:**
- Modify: `config/CONFIG_GUIDE.md`
- Test: `src/backend/tests/test_docker_seed_alignment.py`
- Test: `src/backend/tests/test_reject_error_detail.py`
- Test: browser flow on `FaultRecords.jsx`

**Step 1: Add regression cases for each rewritten metric family**

- WS positions
- mark positions
- SA result metrics
- Sx/Sy
- D_x/D_y
- Tx/Ty/Rw

**Step 2: Re-run real browser verification**

Verify on at least one real `COARSE_ALIGN_FAILED` record:

- metric count
- metric values
- COWA model outputs
- detail page display

**Step 3: Update config guide**

Document any newly supported linking/filter operators or extraction rule syntax.

## Open Questions for Business Alignment

These should be answered before coding the blocked tasks:

1. For `WS_pos_x` / `WS_pos_y`, should current `equipment` and `chuck_id` linking remain, or should the authoritative filter set be only `lot_id + wafer_id + phase='1ST_COWA'`?
2. For `mark_pos_x` / `mark_pos_y`, how exactly is `mark_id` derived from the earlier WS query result? Please provide either:
   - one SQL/sample-row example, or
   - the 4 exact `mark_id` values for a known case.
3. For `Msx` / `Msy` / `e_ws_x` / `e_ws_y`, what is the missing condition that disambiguates the two returned rows?
4. For `Sx` / `Sy`, is the JSON path exactly:
   - `static_wafer_load_offset.chuck_message[n].static_load_offset.x/y`
   and is `n = chuck_id - 1` always valid?
5. For `D_x` / `D_y`, what is the exact physical table name pattern:
   - `LO_wafer_result`
   - or `LO_wafer_result_<machine>`
   - or another suffix rule?
6. For `Tx` / `Ty` / `Rw`, should the source table be:
   - the unsuffixed `datacenter.lo_batch_equipment_performance_temp`
   - or a dated suffix table?
7. For `Tx` / `Ty` / `Rw`, which time column is authoritative for the one-month backtracking:
   - `lot_start_time`
   - `lot_end_time`
   - or another timestamp column?
8. Do `Sx` / `Sy` need to be externally renamed to `S_x` / `S_y`, or is internal alias compatibility sufficient?

## Recommendation

Do **not** implement this as one batch.

Recommended execution split:

1. Business alignment on the 8 questions above
2. Config-only fixes (`WS_pos_x`, `WS_pos_y`)
3. Fetcher capability upgrade (`contains`, `in`, nested JSON path, context-derived filters)
4. Metric rewiring by family:
   - mark positions
   - SA result metrics
   - Sx/Sy
   - D_x/D_y
   - Tx/Ty/Rw
5. Real browser + seeded-data verification

