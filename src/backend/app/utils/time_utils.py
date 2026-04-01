"""
时间工具函数
提供时间戳与 datetime 的转换
"""
from datetime import datetime
from typing import Optional


def datetime_to_timestamp(dt: Optional[datetime]) -> Optional[int]:
    """
    将 datetime 转换为 13 位 Unix 时间戳（毫秒）

    Args:
        dt: datetime 对象

    Returns:
        13 位 Unix 时间戳（毫秒），如果输入为 None 则返回 None
    """
    if dt is None:
        return None
    return int(dt.timestamp() * 1000)


def timestamp_to_datetime(ts: Optional[int]) -> Optional[datetime]:
    """
    将 13 位 Unix 时间戳转换为 datetime

    Args:
        ts: 13 位 Unix 时间戳（毫秒）

    Returns:
        datetime 对象，如果输入为 None 则返回 None
    """
    if ts is None:
        return None
    return datetime.fromtimestamp(ts / 1000)


def format_datetime(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M:%S.%f") -> Optional[str]:
    """
    格式化 datetime 为字符串

    Args:
        dt: datetime 对象
        fmt: 格式化字符串

    Returns:
        格式化后的时间字符串
    """
    if dt is None:
        return None
    return dt.strftime(fmt)
