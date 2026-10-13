# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Lazy creation must not freeze the loop or retry once per skill."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from openjiuwen.extensions.sys_operation.sandbox.providers import jiuwenbox as jb


class Probe(jb._JiuwenBoxProviderMixin):
    def __init__(self, client, scope="one"):
        self.endpoint = SimpleNamespace(base_url="http://localhost:8321", isolation_key=scope)
        self.config = None
        self._init_jiuwenbox(self.endpoint, None)
        self._client = client


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [httpx.ReadTimeout("ACL timeout"), RuntimeError("HTTP 500: cleanup failed")])
async def test_strict_delete_preserves_original_error(monkeypatch, failure):
    key = "http://localhost:8321|one"
    jb._JiuwenBoxProviderMixin.register_shared_sandbox_id(key, "sandbox")
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.delete_sandbox.side_effect = failure
    monkeypatch.setattr(jb, "_JiuwenBoxClient", Mock(return_value=client))
    with pytest.raises(RuntimeError, match=str(failure)) as exc:
        await jb.delete_jiuwenbox_sandbox(shared_key=key, raise_on_error=True)
    assert exc.value.__cause__ is failure


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    for name in ("_shared_sandbox_ids", "_creation_locks", "_creation_failures", "_lifecycle_hooks",
                 "_pending_deletions", "_delete_tasks"):
        monkeypatch.setattr(jb._JiuwenBoxProviderMixin, name, {})
    monkeypatch.delenv("JIUWENBOX_SANDBOX_ID", raising=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline", ["fs", "exec"])
async def test_slow_initial_create_keeps_loop_responsive(pipeline):
    started, release = threading.Event(), threading.Event()
    main_thread = threading.get_ident()

    def create(**kwargs):
        assert threading.get_ident() != main_thread
        started.set()
        assert release.wait(2)
        return "sandbox"

    client = Mock(create_sandbox=Mock(side_effect=create))
    probe = Probe(client)
    if pipeline == "fs":
        operation = probe._execute_with_sandbox_retry(lambda sid: sid)
    else:
        operation = probe._run_exec_pipeline(
            sandbox_op=lambda sid: {"exit_code": 0, "stdout": sid, "stderr": ""},
            local_op=Mock(), fallback_on_failure=False,
        )
    task = asyncio.create_task(operation)
    try:
        assert await asyncio.to_thread(started.wait, 1)
        # A synchronous cache operation must also remain usable during HTTP.
        assert jb._JiuwenBoxProviderMixin.clear_shared_sandbox_for_key("other") is None
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
    result = await asyncio.wait_for(task, 2)
    assert result == "sandbox" if pipeline == "fs" else result[0]["stdout"] == "sandbox"


@pytest.mark.asyncio
async def test_concurrent_providers_share_one_create():
    client = Mock(create_sandbox=Mock(return_value="sandbox"))
    first, second = Probe(client), Probe(client)
    results = await asyncio.gather(*[
        probe._execute_with_sandbox_retry(lambda sid: sid) for probe in (first, second)
    ])
    assert results == ["sandbox", "sandbox"]
    client.create_sandbox.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("reset", ["clear", "expiry"])
async def test_failed_create_is_shared_and_can_recover(reset):
    client = Mock(create_sandbox=Mock(side_effect=httpx.ReadTimeout("ACL timeout")))
    first, second = Probe(client), Probe(client)
    with pytest.raises(httpx.ReadTimeout):
        await first._execute_with_sandbox_retry(lambda sid: sid)
    for _ in range(45):
        with pytest.raises(RuntimeError, match="temporarily unavailable"):
            await second._execute_with_sandbox_retry(lambda sid: sid)
    client.create_sandbox.assert_called_once()
    if reset == "clear":
        jb._JiuwenBoxProviderMixin.clear_shared_sandbox_for_key(first._shared_scope_key())
    else:
        jb._JiuwenBoxProviderMixin._creation_failures[first._shared_scope_key()] = (0.0, "expired")
    client.create_sandbox.side_effect = None
    client.create_sandbox.return_value = "recovered"
    assert await second._execute_with_sandbox_retry(lambda sid: sid) == "recovered"


@pytest.mark.asyncio
async def test_teardown_during_create_does_not_publish_orphan():
    started, release = threading.Event(), threading.Event()

    def create(**kwargs):
        started.set()
        assert release.wait(2)
        return "orphan"

    client = Mock(create_sandbox=Mock(side_effect=create))
    probe = Probe(client)
    task = asyncio.create_task(probe._execute_with_sandbox_retry(lambda sid: sid))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        jb._JiuwenBoxProviderMixin.clear_shared_sandbox_for_key(probe._shared_scope_key())
    finally:
        release.set()
    with pytest.raises(RuntimeError, match="invalidated"):
        await task
    assert not jb._JiuwenBoxProviderMixin._shared_sandbox_ids
    client.delete_sandbox.assert_called_once_with("orphan")


@pytest.mark.asyncio
async def test_failed_delete_blocks_reuse_and_recreation_until_retry(monkeypatch):
    probe = Probe(Mock())
    key = probe._shared_scope_key()
    jb._JiuwenBoxProviderMixin.register_shared_sandbox_id(key, "old")
    hook = Mock()
    jb._JiuwenBoxProviderMixin.register_lifecycle_hook(key, hook)
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.delete_sandbox.side_effect = [httpx.ReadTimeout("ACL timeout"), None]
    monkeypatch.setattr(jb, "_JiuwenBoxClient", Mock(return_value=client))
    assert await jb.delete_jiuwenbox_sandbox(shared_key=key) == []
    assert jb._JiuwenBoxProviderMixin._shared_sandbox_ids[key] == "old"
    assert jb._JiuwenBoxProviderMixin._lifecycle_hooks[key] is hook
    probe._sandbox_id = "old"
    with pytest.raises(RuntimeError, match="deletion is pending"):
        probe._get_sandbox_id()
    with pytest.raises(RuntimeError, match="deletion is pending"):
        await jb.force_recreate_jiuwenbox_sandbox("http://localhost:8321", shared_key=key)
    assert await jb.delete_jiuwenbox_sandbox(shared_key=key) == ["old"]
    assert [call.args[0] for call in hook.call_args_list] == ["before_delete", "after_delete"]
    assert key not in jb._JiuwenBoxProviderMixin._shared_sandbox_ids
    assert not jb._JiuwenBoxProviderMixin._pending_deletions
    client.create_sandbox.assert_not_called()


@pytest.mark.asyncio
async def test_pending_delete_retry_keeps_original_hook(monkeypatch):
    key = "http://localhost:8321|one"
    cls = jb._JiuwenBoxProviderMixin
    cls.register_shared_sandbox_id(key, "old")
    old_hook, new_hook = Mock(), Mock()
    cls.register_lifecycle_hook(key, old_hook)
    client = Mock(__enter__=Mock(), __exit__=Mock(return_value=False))
    client.__enter__.return_value = client
    client.delete_sandbox.side_effect = [httpx.ReadTimeout("ACL timeout"), None]
    monkeypatch.setattr(jb, "_JiuwenBoxClient", Mock(return_value=client))
    assert await jb.delete_jiuwenbox_sandbox(shared_key=key) == []
    cls._shared_sandbox_ids[key] = "new"
    cls.register_lifecycle_hook(key, new_hook)
    assert await jb.delete_jiuwenbox_sandbox(shared_key=key, sandbox_id="old") == ["old"]
    assert [call.args[0] for call in old_hook.call_args_list] == ["before_delete", "after_delete"]
    new_hook.assert_not_called()
    assert cls._shared_sandbox_ids[key] == "new"
    assert cls._lifecycle_hooks[key] is new_hook


@pytest.mark.asyncio
async def test_after_delete_hook_failure_does_not_restore_deleted_entry(monkeypatch):
    key = "http://localhost:8321|one"
    cls = jb._JiuwenBoxProviderMixin
    cls.register_shared_sandbox_id(key, "old")
    hook = Mock(side_effect=[None, RuntimeError("after hook failed")])
    cls.register_lifecycle_hook(key, hook)
    client = Mock(__enter__=Mock(), __exit__=Mock(return_value=False))
    client.__enter__.return_value = client
    monkeypatch.setattr(jb, "_JiuwenBoxClient", Mock(return_value=client))
    with pytest.raises(RuntimeError, match="after hook failed"):
        await jb.delete_jiuwenbox_sandbox(shared_key=key)
    assert key not in cls._shared_sandbox_ids
    assert not cls._pending_deletions


@pytest.mark.asyncio
async def test_concurrent_delete_runs_hooks_once_and_preserves_new_cache(monkeypatch):
    key = "http://localhost:8321|one"
    cls = jb._JiuwenBoxProviderMixin
    cls.register_shared_sandbox_id(key, "old")
    hook = Mock()
    cls.register_lifecycle_hook(key, hook)
    entered, release = threading.Event(), threading.Event()

    def delete(sid):
        entered.set()
        assert release.wait(2)

    client = Mock(__enter__=Mock(), __exit__=Mock(return_value=False))
    client.__enter__.return_value = client
    client.delete_sandbox.side_effect = delete
    monkeypatch.setattr(jb, "_JiuwenBoxClient", Mock(return_value=client))
    first = asyncio.create_task(jb.delete_jiuwenbox_sandbox(shared_key=key, sandbox_id="old"))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        cls.register_shared_sandbox_id(key, "new")
        second = asyncio.create_task(jb.delete_jiuwenbox_sandbox(shared_key=key, sandbox_id="old"))
        await asyncio.sleep(0)
        assert not second.done()
    finally:
        release.set()
    assert await asyncio.gather(first, second) == [["old"], ["old"]]
    assert cls._shared_sandbox_ids[key] == "new"
    client.delete_sandbox.assert_called_once_with("old")
    assert [call.args[0] for call in hook.call_args_list] == ["before_delete", "after_delete"]
