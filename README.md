# Graph 项目

## 环境要求

- Python: 3.12
- 包管理器: uv
- Web 框架: FastAPI
- 数据验证: Pydantic

## 快速开始

### 安装 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

### 创建虚拟环境

```bash
uv venv --python 3.12
source .venv/bin/activate
```

### 安装依赖

配置国内镜像源（清华大学镜像）：

```bash
# 使用国内镜像源安装依赖
uv pip install -r requirements.txt --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

或者设置全局配置：

```bash
# 设置全局镜像源
uv pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

## 已配置工具

### Claude Code MCP 服务器

- **Chrome DevTools MCP**: 用于浏览器自动化和调试
  - 配置文件: `~/.claude.json`
  - 功能: 性能分析、网络监控、DOM 操作、截图等

### Claude Code Skills

已安装以下社区 skills：

1. **claude-code-infrastructure** ([GitHub](https://github.com/diet103/claude-code-infrastructure-showcase))
   - 生产级 Claude Code 基础架构参考
   - 包含 hooks 系统、模块化 skill 模式、10+ 专业 agents
   - Skills: backend-dev-guidelines, frontend-dev-guidelines, skill-developer 等

2. **superpowers** ([GitHub](https://github.com/obra/superpowers))
   - 核心 skills 库，包含 20+ 经过实战验证的 skills
   - TDD、调试、协作模式等
   - 功能: `/brainstorm`, `/write-plan`, `/execute-plan` 命令

3. **awesome-claude-skills** ([GitHub](https://github.com/travisvn/awesome-claude-skills))
   - 精选 Claude Skills 资源列表
   - 官方 skills: docx, pdf, pptx, xlsx, frontend-design 等
   - 社区 skills 集合和工具

## 开发规范

- 使用 FastAPI 构建 Web 服务
- 使用 Pydantic 进行数据验证
- 遵循 Python 代码规范（PEP 8）
