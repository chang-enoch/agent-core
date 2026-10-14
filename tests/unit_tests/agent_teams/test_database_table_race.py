# coding: utf-8
# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""并发建表回归：create_cur_session_tables 必须并发安全。

背景：成员惰性拉起时多个协程并发初始化同会话动态表，旧的
``table.create(checkfirst=True)`` 是"先查再建"两步、中间有窗口，
并发下炸 ``OperationalError: table ... already exists``。
修复后走原子 DDL ``CREATE TABLE IF NOT EXISTS``。

DDL 改在 ``DbSessions.write()`` 进程级写锁内执行
此前裸 ``engine.begin()`` 绕过写锁，
多团队并发 bind 时 DDL 占满 2 槽写池（QueuePool size 2 overflow 0）
崩成员。并发安全现在由"写锁串行 + 原子 DDL"双层保证。
"""

import asyncio

import pytest
import pytest_asyncio

from openjiuwen.agent_teams.context import reset_session_id, set_session_id
from openjiuwen.agent_teams.tools.database import (
    DatabaseConfig,
    DatabaseType,
    TeamDatabase,
)


@pytest_asyncio.fixture
async def team_db():
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
async def test_create_cur_session_tables_concurrent_is_race_free(team_db):
    """同一实例上并发建同会话动态表：写锁串行化，全部成功，无 already exists。"""
    token = set_session_id("race-session")
    try:
        results = await asyncio.gather(
            *[team_db.create_cur_session_tables() for _ in range(8)],
            return_exceptions=True,
        )
        errors = [r for r in results if isinstance(r, BaseException)]
        assert errors == []
    finally:
        reset_session_id(token)


@pytest.mark.asyncio
async def test_create_cur_session_tables_idempotent_sequential(team_db):
    """顺序重复建表同样幂等（IF NOT EXISTS 语义 + 已存在表走迁移分支）。"""
    token = set_session_id("race-session-seq")
    try:
        await team_db.create_cur_session_tables()
        await team_db.create_cur_session_tables()
    finally:
        reset_session_id(token)
