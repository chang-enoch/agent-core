# coding: utf-8
# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""回归：bind 期会话建表 DDL 必须走写锁 + 瞬态重试 + 耗尽降级。

``create_cur_session_tables`` 旧实现裸
``engine.begin()`` 绕过 ``DbSessions`` 进程级写锁，多团队并发 bind 时
DDL 占满写池（QueuePool size 2 overflow 0 timeout 10s），检出超时直接
崩溃成员（sqlalchemy.exc.TimeoutError）。修复策略：
  1. DDL 在 ``sessions.write()`` 内执行，与全部 DAO 写串行；
  2. 瞬态错误（OperationalError / SATimeoutError / 看门狗 TimeoutError）
     指数退避重试，预算耗尽降级为 ERROR 日志而非崩溃；
  3. 迁移扫描收窄到当前会话候选表，新建表整体跳过（零 get_indexes PRAGMA）。
"""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SATimeoutError

from openjiuwen.agent_teams.context import reset_session_id, set_session_id
from openjiuwen.agent_teams.tools.database import (
    DatabaseConfig,
    DatabaseType,
    TeamDatabase,
)
from openjiuwen.agent_teams.tools.database import engine as engine_module


@pytest_asyncio.fixture
async def memory_db():
    # 不在夹具里 set_session_id：pytest-asyncio 下夹具与用例跑在不同
    # Context，夹具里 set 的值用例体看不到、teardown reset 还会抛
    # "created in a different Context"。会话绑定放到各用例体内。
    database = TeamDatabase(
        DatabaseConfig(db_type=DatabaseType.SQLITE, connection_string=":memory:")
    )
    try:
        await database.initialize()
        yield database
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_bind_ddl_runs_under_write_lock(memory_db, monkeypatch):
    """_ensure_session_tables 执行期间进程级写锁必须处于持有状态。"""
    token = set_session_id("lock")
    try:
        observed = []
        real = engine_module._ensure_session_tables

        async def spy(session):
            observed.append(memory_db._sessions._write_lock.locked())
            await real(session)

        monkeypatch.setattr(engine_module, "_ensure_session_tables", spy)
        await memory_db.create_cur_session_tables()
        assert observed == [True]
    finally:
        reset_session_id(token)


@pytest.mark.asyncio
async def test_bind_ddl_retries_transient_operational_error(memory_db, monkeypatch):
    """首次尝试撞 database is locked，退避后重试成功，整体不抛异常。"""
    token = set_session_id("retry-op")
    try:
        calls = {"n": 0}
        real = engine_module._ensure_session_tables

        async def flaky(session):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OperationalError("CREATE TABLE", {}, Exception("database is locked"))
            await real(session)

        monkeypatch.setattr(engine_module, "_ensure_session_tables", flaky)
        monkeypatch.setattr(engine_module, "_DB_RETRY_BASE_DELAY", 0)
        await memory_db.create_cur_session_tables()
        assert calls["n"] == 2
    finally:
        reset_session_id(token)


@pytest.mark.asyncio
async def test_bind_ddl_retries_pool_timeout(memory_db, monkeypatch):
    """检出超时（SATimeoutError）同样走重试且可恢复。"""
    token = set_session_id("retry-pool")
    try:
        calls = {"n": 0}
        real = engine_module._ensure_session_tables

        async def flaky(session):
            calls["n"] += 1
            if calls["n"] == 1:
                raise SATimeoutError("SELECT 1", {}, Exception("pool checkout timeout"))
            await real(session)

        monkeypatch.setattr(engine_module, "_ensure_session_tables", flaky)
        monkeypatch.setattr(engine_module, "_DB_RETRY_BASE_DELAY", 0)
        await memory_db.create_cur_session_tables()
        assert calls["n"] == 2
    finally:
        reset_session_id(token)


@pytest.mark.asyncio
async def test_bind_ddl_budget_exhausted_degrades_without_raising(memory_db, monkeypatch):
    """重试预算耗尽：返回 None 不抛异常（成员不崩），且恰好尝试预算次数。"""
    token = set_session_id("exhausted")
    try:
        calls = {"n": 0}

        async def always_locked(session):
            calls["n"] += 1
            raise OperationalError("CREATE TABLE", {}, Exception("database is locked"))

        monkeypatch.setattr(engine_module, "_ensure_session_tables", always_locked)
        monkeypatch.setattr(engine_module, "_DB_RETRY_BASE_DELAY", 0)
        # 关键断言就是"不抛"——旧实现此处会把 TimeoutError 穿透成成员崩溃。
        await memory_db.create_cur_session_tables()
        assert calls["n"] == engine_module._DB_RETRY_ATTEMPTS
    finally:
        reset_session_id(token)


@pytest.mark.asyncio
async def test_fresh_tables_skip_migration_scan(memory_db, monkeypatch):
    """新建表不进迁移扫描（existing_before_create 为空）；重复 bind 才扫。"""
    token = set_session_id("snapshot")
    try:
        snapshots = []
        real = engine_module._ensure_dynamic_table_indexes

        def spy(sync_conn, candidates, existing_before_create):
            snapshots.append((list(candidates), set(existing_before_create)))
            return real(sync_conn, candidates, existing_before_create)

        monkeypatch.setattr(engine_module, "_ensure_dynamic_table_indexes", spy)

        await memory_db.create_cur_session_tables()
        assert len(snapshots) == 1
        candidates, existing = snapshots[0]
        assert len(candidates) == 3  # task / task_dependency / message
        assert existing == set()  # 全部新建 → 迁移整体跳过

        await memory_db.create_cur_session_tables()
        assert len(snapshots) == 2
        _, existing_second = snapshots[1]
        assert existing_second == set(candidates)  # 二次 bind 三表均已存在 → 走迁移
    finally:
        reset_session_id(token)


@pytest.mark.asyncio
async def test_concurrent_binds_and_dao_writes_all_succeed(tmp_path):
    """文件后端（写池 2 槽）下并发 bind DDL 与 DAO 写交错：写锁串行化，零异常。

    旧实现（裸 engine.begin()）在此形态下并发 DDL 直接争抢 2 槽写池，
    是成员崩溃的触发形态。
    """
    db_path = tmp_path / "pm47_concurrent.db"
    database = TeamDatabase(
        DatabaseConfig(db_type=DatabaseType.SQLITE, connection_string=str(db_path))
    )
    token = set_session_id("concurrent")
    try:
        await database.initialize()
        await database.team.create_team("team_pm47", "PM47 Team", "leader1")

        async def bind():
            await database.create_cur_session_tables()

        async def dao_write(i):
            await database.member.create_member(
                member_name=f"member{i}",
                team_name="team_pm47",
                display_name=f"Member {i}",
                agent_card="",
                status="ready",
            )

        results = await asyncio.gather(
            *[bind() for _ in range(6)],
            *[dao_write(i) for i in range(6)],
            return_exceptions=True,
        )
        errors = [r for r in results if isinstance(r, BaseException)]
        assert errors == []
    finally:
        await database.close()
        reset_session_id(token)
