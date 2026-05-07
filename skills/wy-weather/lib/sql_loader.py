"""SQL file loader — deploy/sql/ 하위 파일 로드 + .format(**params)

Usage:
    from sql_loader import load_sql
    sql = load_sql("mission/rpi_pool.sql", tm_cd="TM02", prev1="2026-04-20", prev2="2026-04-19", prev14="2026-04-07")
"""
from pathlib import Path


_SQL_ROOT = Path(__file__).resolve().parent / "sql"


def load_sql(name: str, **params) -> str:
    """deploy/sql/{name} 로드 후 .format(**params) 반환.

    Args:
        name: 'mission/rpi_pool.sql' 형태 상대 경로
        **params: SQL 템플릿 플레이스홀더 채울 값

    Returns:
        파라미터 치환된 SQL 문자열

    Raises:
        FileNotFoundError: SQL 파일 없음
        KeyError: 필요한 파라미터 누락 (format KeyError 그대로 노출)
    """
    path = (_SQL_ROOT / name).resolve()
    if not path.is_relative_to(_SQL_ROOT.resolve()):
        raise ValueError(f"SQL path traversal 차단: {name!r}")
    if not path.exists():
        raise FileNotFoundError(f"SQL not found: {path}")
    sql = path.read_text(encoding="utf-8")
    if params:
        sql = sql.format(**params)
    return sql
