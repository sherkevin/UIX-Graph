# 配置驱动达成度

> **项目目标**(用户原话):「光刻机故障根因分析系统,输入故障现象 → 走故障树 → 输出根因 + 排查路径上的所有指标。
> **只通过修改配置文档,就能实现整个项目的功能,不用改动代码**。」
>
> 本文档对照逐项评估当前达成度。**最后更新:2026-04-19,K1–K7 全部 apply 后**。

---

## 1. 已达成(只改配置就能扩展)

| 能力 | 配置入口 | 落地 commit |
|------|---------|------------|
| **加新故障场景** | `config/reject_errors.diagnosis.json` `diagnosis_scenes[]` | 历史 |
| **改决策树分支 / 阈值** | `steps[].next[].condition` 表达式 | 历史 |
| **加新指标 / 改 metric 元数据** | `metrics{}` 字典(自动 fail-fast 校验)| H, K3, K5 |
| **指标取数源切换** | `source_kind` + `table_name` + `column_name` + `linking` | 历史 |
| **加新机台** | `config/equipments.json` `equipments[]`,`reload_equipments()` 热更新 | K2 |
| **加新建模输出别名** | metric `alias_of` 字段 | K3 |
| **加新 mock 数据(无真库时)** | metric `mock_value` / `mock_range` | K5 |
| **写一段计算公式作为中间量** | `safe_eval` action + `params.expr` 表达式 | J |
| **关闭老路由** | 环境变量 `LEGACY_ROUTES_ENABLED=false` | D |
| **触发缓存按版本失效** | bump `reject_errors.diagnosis.json` 顶部 `version` 字段 | K4 |
| **改 jsonpath 提取(含 `name[N]` 形式)** | metric `extraction_rule = jsonpath:...`(标准 array 写法即可)| K1 |

### 配套工具(让"只改配置"在工程上 sustainable)

| 工具 | 何时用 |
|------|------|
| `python scripts/check_config.py` | 改完配置立刻自检(rule_validator + orphan / unreachable / missing fallback / duplicate start_node 软警告)|
| `pytest tests/test_rule_validator_metric.py` | 28+ 个 fail-fast case,任何 metric 元数据写错都会被抓 |
| `pytest tests/test_safe_eval_action.py` | 32 个 case 覆盖 safe_eval 所有合法/拒绝路径 |
| `docs/CONFIG_REVIEW_CHECKLIST.md` | 评审者按 8 节 checklist 决定 approve / block |
| `docs/intranet/databases/{mysql_datacenter,clickhouse_las,clickhouse_src}.md` | 每张表的字段权威参考(供外网 mock + 联调对齐)|
| `docs/STRUCTURE.md` §7「我想做 X 件事」 | 改哪儿对照表 |
| `docs/STRUCTURE.md` §10 mermaid 架构图 | 数据流 + 模块依赖一目了然 |
| `docs/STRUCTURE.md` §11 内网表 ↔ 本地资源对照表 | 每张表精确到行号 |

---

## 2. 仍需改代码的事(根本限制 + 演进方向)

| 场景 | 必须改代码的位置 | 备注 |
|------|----------------|------|
| **加全新 `source_kind`(如 Redis / HTTP API 取数)** | `engine/metric_fetcher.py` 加新 `_fetch_from_<kind>` 方法 + `rule_validator.VALID_SOURCE_KINDS` 加常量 | plugin 化是长期演进方向 |
| **加全新 `transform.type`(如 `regex_extract` 复合变换)** | `engine/metric_fetcher._apply_transform` + `rule_validator.VALID_TRANSFORM_TYPES` | 同上,长期 plugin 化 |
| **加全新 `linking.operator`(如 `regexp` SQL 操作符)** | `engine/metric_fetcher._build_linking_clauses` 加分支 + `rule_validator.VALID_LINKING_OPERATORS` | 同上 |
| **加复杂数学(如矩阵求逆、SVD 等 numpy 操作)** | `engine/actions/` 新建 .py 文件用 `@register` 注册 | `safe_eval` 只覆盖标量算术;矩阵/复杂建模仍要 Python action(如已有的 `_solve_b_wa_4param_pinv`)|
| **改前端 UI 行为** | `src/frontend/src/pages/FaultRecords.jsx` | 前端是另一个独立项目,不在配置驱动范围 |
| **改部署 / 启动逻辑** | `scripts/start.py` 等 | 部署属于工程基础设施,跟规则配置不同维度 |

> **重要**:这些都是**根本限制** —— Python action 必然要用 Python 写,这是事实而不是缺陷。`safe_eval` 已经把"加一个简单计算"从 Python 降级到配置;后续如果要把"加新 source_kind"也变成配置驱动,得做一套完整的 **plugin 注册机制**(`config/plugins/<kind>.py` + 动态加载)。

---

## 3. 7 个 post-stage4 bug 修复对照(K1–K7,2026-04-19)

| Bug | 之前(违反配置驱动)| 现在(配置驱动)|
|-----|-------------------|----------------|
| #1 jsonpath `chuck_message[N]` 静默失败 | 任何 `name[N]` jsonpath 跑不通,Sx/Sy fall back to mock | `_NAME_INDEX_RE` 分支识别,name[N] 与 name/N 双向兼容 |
| #2 `EQUIPMENT_WHITELIST` 硬编码 | 加机台必改 Python | `config/equipments.json` + 热更新 + 内置 fallback |
| #3 `_METRIC_ALIAS_MAP` 硬编码 | 加 alias 必改 Python | metric `alias_of` 字段 + 静态校验 + 循环检测 |
| #4 缓存永不失效 | 改配置后旧根因还返回 | `config_version` 列 + `_cache_version_matches` + 自动失效重算 |
| #5 `legacy_ranges` / `_mock_intermediate_value` 硬编码 | 加新指标 mock 必改 Python | `mock_value` / `mock_range` 字段 + 静态校验 + 通用 fallback |
| #6 `max_steps` 截断无专门日志 | 排障难,无法区分"分支没匹配"vs"配置循环" | `logger.warning` + `detail_trace.warning` + 排障建议 |
| #7 `_render_extraction_template` list 拼错 | window 类指标的 list 被 `str([...])` 拼到 jsonpath | 取首个非 None + warning;全空视为缺失 |

---

## 4. 工程飞轮(配置驱动 + 防御层)

```
专家(根据业务需求)
  ↓ 编辑 config/reject_errors.diagnosis.json / equipments.json
本地自检
  ├─ python scripts/check_config.py        ← rule_validator(9 维 fail-fast)
  │                                          + 软警告(orphan / unreachable / missing fallback)
  └─ pytest tests/test_rule_validator_metric.py   ← 36 个回归测试守护
PR 提交
  ↓
评审者按 docs/CONFIG_REVIEW_CHECKLIST.md 8 节 checklist 决策
  ↓
merge 进 main
  ↓
服务启动
  ├─ DiagnosisConfigStore 加载 → rule_validator 二次校验(fail-fast)
  └─ 缓存表 config_version 不一致 → 自动失效重算
  ↓
诊断引擎执行
  ├─ MetricFetcher 取数(jsonpath name[N] 兼容、mock 配置驱动)
  ├─ DiagnosisEngine 走决策树(_walk_subtree max_steps 安全网 + 截断专门日志)
  └─ alias_of 自动反查(配置驱动)
  ↓
落库 rejected_detailed_records(带 config_version)
  ↓
接口 3 返回前端
```

---

## 5. Commit 历史(完整 18 笔,在 tag `pre-cleanup-20260419` 之上)

```text
A 2107b69  chore(repo): clean up legacy artifacts                        基础卫生
B 3f4a7b1  docs(intranet): per-database schema reference                 数据契约
C 1e5c0c8  refactor(frontend): archive legacy multi-page UI              代码精简
D 428fb1d  feat(api): legacy routes feature flag                         可控降级
E e2003d8  docs(scripts): rewrite README                                 工具梳理
F 72dab01  fix(mock): close 3 init-script gaps                          本地可跑通
G 94a92e5  docs: polish root README/HANDOVER/STRUCTURE                   导航完整
H 2a5c772  feat(validator): strict metric metadata validation            fail-fast 校验
I b4c8c3f  feat(config): check_config.py + CONFIG_REVIEW_CHECKLIST.md    自助工具
J c773e87  feat(actions): safe_eval + equipments.json + post-plan        配置驱动深化
   ────────────────────────  Stage4 wip 包装  ────────────────────────
   13cf121  wip(stage4): in-progress snapshot                            33 files
   ────────────────────────  Post-stage4 bug fixes  ──────────────────
K1 5e9d274  fix(metric_fetcher): jsonpath name[N]
K2 56beaae  feat(service): equipment whitelist config-driven
K3 e6d97b5  refactor(engine): _METRIC_ALIAS_MAP → metric.alias_of
K4 94f5280  feat(cache): invalidate by config_version
K5 741702e  refactor(metric_fetcher): mock data config-driven
K6 44ef155  fix(engine): max_steps truncation logs
K7 f376c27  fix(metric_fetcher): list value in extraction template
```

回滚保险:`git tag pre-cleanup-20260419` 锚点指向 `70fb6a1`,任何时候可 `git reset --hard pre-cleanup-20260419`。
