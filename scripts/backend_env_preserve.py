# -*- coding: utf-8 -*-
"""
与 switch_env、start 共用：覆写 .env 前合入需保留的键，避免内网等手动项被冲掉。

当前保留：REJECTED_DETAILED_CACHE（内网无 rejected_detailed_records 表时设为 0）
"""
import re
from pathlib import Path

# 新模板不会写入这些键；若旧 .env 里已有，则写回新文件末尾
PRESERVE_BACKEND_ENV_KEYS = frozenset(
    {
        "REJECTED_DETAILED_CACHE",
    }
)


def parse_simple_dotenv(path: Path) -> dict:
    """仅解析简单 KEY=VALUE 行;忽略空行与 # 注释;值首尾去空白。"""
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        if "=" in t:
            k, _, v = t.partition("=")
            k, v = k.strip(), v.strip()
            if k:
                out[k] = v
    return out


def merge_preserved_from_prev(new_content: str, prev: dict) -> str:
    """
    把上一版 .env 中需保留的键附到 new_content 后(若新文中尚无同键行)。
    prev 为 parse_simple_dotenv 的结果。
    """
    lines = []
    for key in PRESERVE_BACKEND_ENV_KEYS:
        if key not in prev:
            continue
        val = (prev.get(key) or "").strip()
        if not val:
            continue
        if re.search(rf"^{re.escape(key)}\\s*=", new_content, re.MULTILINE):
            continue
        lines.append(f"{key}={val}")
    if not lines:
        return new_content
    sep = "" if new_content.endswith("\n") else "\n"
    return (
        new_content
        + f"{sep}# 以上为主配置;下列键自原 .env 保留(启动/切换环境不会删除)\n"
        + "\n".join(lines)
        + "\n"
    )
