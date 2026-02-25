import os
from dotenv import load_dotenv
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

load_dotenv()

# 엔진·세션은 실제 요청 시점에 생성 (테스트 시 get_db가 override되므로 불필요)
_engine = None
_AsyncSessionLocal = None


def _build_url() -> URL:
    """환경변수로부터 SQLAlchemy URL 객체를 생성합니다.

    SID / Service Name 중 설정된 값을 자동으로 사용합니다.
    URL.create를 사용하므로 비밀번호 특수문자를 그대로 써도 됩니다.
    """
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    host = os.getenv("DB_HOST")
    port = int(os.getenv("DB_PORT", "1521"))
    sid = os.getenv("DB_SID")
    service = os.getenv("DB_SERVICE")

    if not all([user, password, host]):
        raise RuntimeError(
            "DB_USER, DB_PASSWORD, DB_HOST 환경변수가 설정되지 않았습니다."
        )
    if not sid and not service:
        raise RuntimeError(
            "DB_SID 또는 DB_SERVICE 환경변수 중 하나는 반드시 설정해야 합니다."
        )

    # SID 우선, 없으면 Service Name 사용
    query = {"sid": sid} if sid else {}
    database = None if sid else service

    if sid:
        dsn = f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={host})(PORT={port}))(CONNECT_DATA=(SID={sid})))"
    else:
        dsn = f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={host})(PORT={port}))(CONNECT_DATA=(SERVICE_NAME={service})))"
    print(dsn)
    return URL.create(
        drivername="oracle+oracledb_async",
        username=user,
        password=password,
        host=host,
        port=port,
        database=sid
        # query=query,
        # database=dsn,
        # query=query
        # query={}
    )


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _build_url(),
            echo=os.getenv("DB_ECHO", "false").lower() == "true",
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _engine


def _get_session_factory():
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        _AsyncSessionLocal = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _AsyncSessionLocal


async def get_db() -> AsyncSession:
    async with _get_session_factory()() as session:
        yield session