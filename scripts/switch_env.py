"""
环境切换脚本
用法：
  python scripts/switch_env.py local    # 切换到本地开发环境（本机 Docker MySQL）
  python scripts/switch_env.py test     # 切换到内网 test 环境
  python scripts/switch_env.py prod     # 切换到内网 prod 环境

脚本会：
  1. 检查 prod 密码安全性（禁止使用占位符密码）
  2. 生成后端 .env 文件（APP_ENV + CORS_ORIGINS + METRIC_SOURCE_MODE）
  3. 生成前端 .env 文件（VITE_API_BASE_URL）
  4. 验证数据库连通性（MySQL + ClickHouse）
  5. 自动建缓存表 rejected_detailed_records（如不存在）

前端 API 地址：
  local → 留空（依赖 Vite 代理，开发模式无需配置）
  test / prod → 读取 config/connections.json 中对应环境的 frontend_api_url 字段；
                若未配置则回退到 http://<mysql.host>:8000
"""

import sys
import json
from pathlib import Path

from backend_env_preserve import merge_preserved_from_prev, parse_simple_dotenv

# ── 项目根目录 ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
CONNECTIONS_FILE = ROOT / "config" / "connections.json"
BACKEND_ENV_FILE = ROOT / "src" / "backend" / ".env"
FRONTEND_ENV_FILE = ROOT / "src" / "frontend" / ".env"

# 前端 API 地址现在从 config/connections.json 的 frontend_api_url 字段读取。
# local 环境默认留空（Vite 代理模式），不再硬编码 IP 或域名。
FRONTEND_API_URLS_FALLBACK = {
    "local": "",           # 本地开发：留空，前端 Vite 代理 /api → localhost:8000
    "test":  "",           # test：请在 config/connections.json 的 test.frontend_api_url 中填写
    "prod":  "",           # prod：请在 config/connections.json 的 prod.frontend_api_url 中填写
}

# ── 颜色输出 ──────────────────────────────────────────────────────────────────
# 仅当 stdout 是 TTY 时启用 ANSI 颜色；被启动器捕获或重定向到文件时自动剥离，
# 避免日志里混入 \033[...m 噪音。
_USE_COLOR = sys.stdout.isatty()
GREEN  = "\033[92m" if _USE_COLOR else ""
YELLOW = "\033[93m" if _USE_COLOR else ""
RED    = "\033[91m" if _USE_COLOR else ""
CYAN   = "\033[96m" if _USE_COLOR else ""
RESET  = "\033[0m"  if _USE_COLOR else ""

def ok(msg):   print(f"{GREEN}  [OK] {msg}{RESET}")
def warn(msg): print(f"{YELLOW}  [!!] {msg}{RESET}")
def err(msg):  print(f"{RED}  [ERR] {msg}{RESET}")
def info(msg): print(f"{CYAN}  --> {msg}{RESET}")

# ─────────────────────────────────────────────────────────────────────────────

def load_connections():
    if not CONNECTIONS_FILE.exists():
        err(f"找不到 {CONNECTIONS_FILE}")
        sys.exit(1)
    with open(CONNECTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def write_backend_env(env: str, env_config: dict = None):
    """写后端 .env 文件

    Args:
        env: 环境名 (local/test/prod)
        env_config: connections.json 中该环境的完整配置块（含 mysql/clickhouse/frontend_api_url）
    """
    if env == "local":
        cors_origins = "http://localhost:3000,http://localhost:8000"
    else:
        frontend_url = (env_config or {}).get("frontend_api_url", "")
        cors_origins = frontend_url if frontend_url else ""

    metric_mode = "mock_allowed" if env == "local" else "real"
    prev = parse_simple_dotenv(BACKEND_ENV_FILE)
    content = f"""# 由 scripts/switch_env.py 生成主配置;内网可保留 REJECTED_DETAILED_CACHE(见文件末尾合并行)
APP_ENV={env}
CORS_ORIGINS={cors_origins}
METRIC_SOURCE_MODE={metric_mode}
LOG_LEVEL=INFO
# 拒片详情接口排障日志（前缀 [详情排障]）；设为 0/false/off 可关闭
UIX_DETAIL_TRACE=1
"""
    content = merge_preserved_from_prev(content, prev)
    BACKEND_ENV_FILE.write_text(content, encoding="utf-8")
    ok(f"后端 .env → APP_ENV={env}  ({BACKEND_ENV_FILE})")


def write_frontend_env(env: str, connections: dict = None):
    """写前端 .env 文件"""
    # 优先从 connections.json 读取 frontend_api_url
    env_cfg = (connections or {}).get(env, {})
    api_url = env_cfg.get("frontend_api_url", FRONTEND_API_URLS_FALLBACK.get(env, ""))
    content = f"""# 自动生成，勿手动修改。使用 scripts/switch_env.py 切换环境。
# local 环境留空时前端通过 Vite 代理访问后端（开发用）
# 外网/内网同源反代部署时同样留空，或填写反代根域名
VITE_API_BASE_URL={api_url}
VITE_ENABLE_DEBUG=false
"""
    FRONTEND_ENV_FILE.write_text(content, encoding="utf-8")
    ok(f"前端 .env → VITE_API_BASE_URL={api_url or '(空，走代理)'}  ({FRONTEND_ENV_FILE})")


def check_mysql(config: dict) -> bool:
    """测试 MySQL 连通性"""
    try:
        import pymysql
        conn = pymysql.connect(
            host=config["host"],
            port=int(config["port"]),
            user=config["username"],
            password=config["password"],
            database=config["dbname"],
            connect_timeout=5,
        )
        conn.close()
        return True
    except ImportError:
        warn("pymysql 未安装，跳过 MySQL 连通性检查")
        return True
    except Exception as e:
        return False


def check_clickhouse(config: dict) -> bool:
    """测试 ClickHouse 连通性。

    clickhouse_connect 在连不上时会向 stderr 打印 "Unexpected Http Driver Exception"
    干扰启动器日志，这里显式捕获并静默(连不上会走 mock，本来就是可接受路径)。
    """
    try:
        import clickhouse_connect
        import logging as _logging
        # 把 clickhouse_connect 的 logger 级别临时调高，抑制连接失败时的堆栈打印
        _ch_logger = _logging.getLogger("clickhouse_connect")
        _old_level = _ch_logger.level
        _ch_logger.setLevel(_logging.CRITICAL)
        try:
            client = clickhouse_connect.get_client(
                host=config["host"],
                port=int(config["port"]),
                username=config.get("username", ""),
                password=config.get("password", ""),
                database=config.get("dbname", "default"),
                connect_timeout=5,
            )
            client.ping()
            client.close()
            return True
        finally:
            _ch_logger.setLevel(_old_level)
    except ImportError:
        warn("clickhouse_connect 未安装，跳过 ClickHouse 连通性检查")
        return True
    except Exception:
        return False


def init_cache_table(mysql_config: dict):
    """在目标 MySQL 中创建 rejected_detailed_records 缓存表（如不存在）"""
    try:
        import pymysql
        conn = pymysql.connect(
            host=mysql_config["host"],
            port=int(mysql_config["port"]),
            user=mysql_config["username"],
            password=mysql_config["password"],
            database=mysql_config["dbname"],
            connect_timeout=5,
        )
        sql = """
        CREATE TABLE IF NOT EXISTS `rejected_detailed_records` (
          `id`               BIGINT AUTO_INCREMENT PRIMARY KEY,
          `failure_id`       BIGINT NOT NULL,
          `equipment`        VARCHAR(50) NOT NULL,
          `chuck_id`         VARCHAR(100) NOT NULL COMMENT 'Chuck ID（兼容整数与字符串）',
          `lot_id`           VARCHAR(100) NOT NULL COMMENT 'Lot ID（兼容整数与字符串）',
          `wafer_id`         VARCHAR(100) NOT NULL COMMENT 'Wafer ID（兼容整数与字符串）',
          `occurred_at`      DATETIME(6) NOT NULL,
          `reject_reason`    VARCHAR(50) NOT NULL,
          `reject_reason_id` BIGINT NOT NULL,
          `root_cause`       VARCHAR(255) DEFAULT NULL,
          `system`           VARCHAR(50) DEFAULT NULL,
          `error_field`      VARCHAR(255) DEFAULT NULL,
          `metrics_data`     JSON DEFAULT NULL,
          `config_version`   VARCHAR(50) DEFAULT NULL COMMENT '写入时的 pipeline.version，用于按配置版本失效缓存',
          `created_at`       DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
          `updated_at`       DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
          UNIQUE KEY `UK_failure_id` (`failure_id`),
          INDEX `IDX_equipment` (`equipment`),
          INDEX `IDX_occurred_at` (`occurred_at`),
          INDEX `IDX_chuck_lot_wafer` (`chuck_id`, `lot_id`, `wafer_id`),
          INDEX `IDX_reject_reason` (`reject_reason`),
          INDEX `IDX_config_version` (`config_version`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        conn.close()
        ok("缓存表 rejected_detailed_records 已就绪")
    except ImportError:
        warn("pymysql 未安装，跳过缓存表初始化")
    except Exception as e:
        warn(f"缓存表初始化失败（可能已存在或权限不足）: {e}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("local", "test", "prod"):
        print(f"用法: python scripts/switch_env.py [local|test|prod]")
        print()
        print("  local  — 本地开发（外网 / 本机 Docker MySQL，端口 3307）")
        print("  test   — 内网 test 环境（172.16.70.171）")
        print("  prod   — 内网 prod 环境（mysql.datacenter.smee.com.cn）")
        sys.exit(1)

    env = sys.argv[1]
    connections = load_connections()

    if env not in connections:
        err(f"connections.json 中没有 [{env}] 配置")
        sys.exit(1)

    mysql_cfg = connections[env].get("mysql", {})
    ch_cfg    = connections[env].get("clickhouse", {})

    print()
    print(f"{CYAN}{'='*60}")
    print(f"  切换到环境: {env.upper()}")
    print(f"{'='*60}{RESET}")
    print()

    env_cfg = connections[env]

    # 安全检查：检测 prod 环境是否忘记修改默认密码
    mysql_pw = mysql_cfg.get("password", "")
    if env == "prod" and mysql_pw == "CHANGE_ME_BEFORE_DEPLOY":
        err("connections.json prod.mysql.password 仍为占位符 CHANGE_ME_BEFORE_DEPLOY")
        err("请修改为真实密码后重新运行！")
        sys.exit(1)

    # 1. 写 .env 文件
    print("【1/5】写入环境配置文件...")
    write_backend_env(env, env_cfg)
    write_frontend_env(env, connections)

    # 2. 检查 MySQL 连通性
    print()
    print("【2/5】检查 MySQL 连通性...")
    info(f"MySQL: {mysql_cfg.get('host')}:{mysql_cfg.get('port')} / {mysql_cfg.get('dbname')}")
    if check_mysql(mysql_cfg):
        ok("MySQL 连接成功")
    else:
        warn(f"MySQL 连接检查失败（{mysql_cfg.get('host')}:{mysql_cfg.get('port')}）")
        warn("服务仍将启动，请确认数据库地址与凭据正确（见 config/connections.json）")

    # 3. 检查 ClickHouse 连通性
    print()
    print("【3/5】检查 ClickHouse 连通性...")
    if ch_cfg:
        info(f"ClickHouse: {ch_cfg.get('host')}:{ch_cfg.get('port')} / {ch_cfg.get('dbname')}")
        if check_clickhouse(ch_cfg):
            ok("ClickHouse 连接成功")
        else:
            warn("ClickHouse 连接失败（指标数据将使用 mock 值，不影响主流程）")
    else:
        warn(f"connections.json 中 [{env}].clickhouse 未配置，跳过")

    # 4. 初始化缓存表
    print()
    print("【4/5】初始化缓存表...")
    init_cache_table(mysql_cfg)

    # 5. 完成
    print()
    print(f"【5/5】环境 [{env.upper()}] 配置完成")
    info(f"后端 .env: {BACKEND_ENV_FILE}")
    info(f"前端 .env: {FRONTEND_ENV_FILE}")
    ok("可通过 start_UIX.bat 或 python scripts/start.py 启动项目")


if __name__ == "__main__":
    main()
