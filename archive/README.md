# archive/

> 这是仓库的「冷藏柜」——存放**仍有参考价值但不再在主线维护**的代码与文档。
>
> **archive/ 不在任何运行路径上**:不会被后端 import、不会被前端构建、不会被启动器扫描、不会被 docker 打包。
> 任何以 `archive/` 为前缀的目录都视为**只读的历史快照**。

---

## 当前归档项

### `frontend-legacy/`(原仓库根目录 `frontend/`)

| 项 | 值 |
|---|---|
| 来源 | 原 [`UIX-Graph/frontend/`](../) (仓库根目录,自 2026-04-19 归档) |
| 最后实际修改时间 | 2026-03-16 前后(`git log` 可查) |
| 包含 | 6 个老页面的多页面 UI,与 [`src/frontend/`](../src/frontend/) 是**不同**的 React 应用 |
| 老页面清单 | `KnowledgeEntry`、`OntologyManager`、`OntologyView`、`KnowledgeGraph`、`EntityDashboard`、`FullGraphView` |
| 后端依赖 | 这 6 个页面调用的是 `/api/{ontology,knowledge,diagnosis,propagation,full_graph,entity,visualization}` 7 组老路由——这些路由本身仍在 [`src/backend/app/handler/`](../src/backend/app/handler/),但已用 `LEGACY_ROUTES_ENABLED` flag 包裹 |

**为什么归档**:

- [`src/frontend/`](../src/frontend/) 是当前主线 UI(精简版,只有「拒片故障管理」一个页面)
- 根 `frontend/` 跟它是**两份独立代码**,长期并存导致「有人改 A,有人跑 B」的分叉风险([`docs/HANDOVER.md`](../docs/HANDOVER.md) §9.5 已警告)
- 业务上 6 个老页面 6 个月内无人提需求,但**仍可能作为「老 UI 设计参考」复用**,所以归档而非物理删除

---

## 怎么用归档

### 复活某个老页面到主线

例如想把 `OntologyManager` 拉回 [`src/frontend/`](../src/frontend/):

```bash
# 1. 复制(不是 mv,保留 archive 副本)
git mv archive/frontend-legacy/src/pages/OntologyManager.jsx src/frontend/src/pages/

# 2. 同时拉对应组件 / 样式
git mv archive/frontend-legacy/src/components/OntologyXxx.jsx src/frontend/src/components/

# 3. src/frontend/src/App.jsx 加路由

# 4. 确认对应的老路由 LEGACY_ROUTES_ENABLED 开启(默认就是 true)
```

### 完全删除某项归档

确认 30+ 天无人提需求后:

```bash
git rm -r archive/frontend-legacy/
git commit -m "chore(archive): remove frontend-legacy after observation period"
```

### 临时查看老代码

不必恢复,直接读:

```bash
# 看老的某个页面
cat archive/frontend-legacy/src/pages/OntologyManager.jsx

# 或在仓库历史中看(归档前的提交)
git log --all -- frontend/src/pages/OntologyManager.jsx
git show pre-cleanup-20260419:frontend/src/pages/OntologyManager.jsx
```

---

## 维护规则

1. **archive/ 下任何子目录,默认认为是「冻结」状态**——不要去改里面的内容,如果要继续维护就该把它移回主线
2. 新增归档项时,在本 README 的「当前归档项」段落补一节,写明:来源、归档原因、是否还有依赖、如何复活
3. 归档项被物理删除时,在本 README 的「当前归档项」段落删掉对应小节,并在 commit message 里说明
4. **永远不要把 archive/ 加入 backend / frontend / scripts 的运行路径**——一旦运行依赖归档代码,它就不再是归档,应当复活到主线
