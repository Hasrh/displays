"""Loopback integration tests for host and reconnecting Pi transport."""

from __future__ import annotations

import asyncio
import socket
from dataclasses import replace
from pathlib import Path

from pc.config import load_config as load_host_config
from pc.network import WebSocketHost
from pi.config import load_config as load_pi_config
from pi.network import PiNetworkClient
from pi.state import LatestStateStore

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "integration-test-token-32-characters"


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


async def wait_for_transport(store: LatestStateStore) -> None:
    async with asyncio.timeout(5):
        while True:
            snapshot = store.snapshot()
            if (
                snapshot.connected
                and snapshot.state is not None
                and snapshot.latest_fft is not None
            ):
                return
            await asyncio.sleep(0.02)


async def exercise_loopback_transport() -> None:
    port = available_port()
    host_config = replace(
        load_host_config(ROOT / "config" / "host.example.toml"),
        bind_host="127.0.0.1",
        port=port,
        heartbeat_interval_seconds=1,
        client_timeout_seconds=3,
    )
    pi_config = replace(
        load_pi_config(ROOT / "config" / "pi.example.toml"),
        host_url=f"ws://127.0.0.1:{port}",
        reconnect_initial_seconds=0.05,
        reconnect_max_seconds=0.1,
    )
    host_stop = asyncio.Event()
    host_started = asyncio.Event()
    client_stop = asyncio.Event()
    store = LatestStateStore()
    host = WebSocketHost(host_config, TOKEN)
    client = PiNetworkClient(pi_config, TOKEN, store)

    host_task = asyncio.create_task(host.run(host_stop, host_started))
    client_task: asyncio.Task[None] | None = None
    try:
        await asyncio.wait_for(host_started.wait(), timeout=2)
        client_task = asyncio.create_task(client.run(client_stop))
        await wait_for_transport(store)
        snapshot = store.snapshot()
        assert snapshot.state is not None
        assert snapshot.state.media is not None
        assert snapshot.state.media.title == "Desktop Display Network Test"
        assert snapshot.latest_fft is not None
        assert len(snapshot.latest_fft.bins) == 64
    finally:
        client_stop.set()
        if client_task is not None:
            await asyncio.wait_for(client_task, timeout=2)
        host_stop.set()
        await asyncio.wait_for(host_task, timeout=2)


def test_host_and_pi_client_exchange_snapshot_and_fft() -> None:
    asyncio.run(exercise_loopback_transport())


async def exercise_reconnect_after_server_appears() -> None:
    port = available_port()
    host_config = replace(
        load_host_config(ROOT / "config" / "host.example.toml"),
        bind_host="127.0.0.1",
        port=port,
        heartbeat_interval_seconds=1,
        client_timeout_seconds=3,
    )
    pi_config = replace(
        load_pi_config(ROOT / "config" / "pi.example.toml"),
        host_url=f"ws://127.0.0.1:{port}",
        reconnect_initial_seconds=0.05,
        reconnect_max_seconds=0.1,
    )
    host_stop = asyncio.Event()
    host_started = asyncio.Event()
    client_stop = asyncio.Event()
    store = LatestStateStore()
    client_task = asyncio.create_task(PiNetworkClient(pi_config, TOKEN, store).run(client_stop))
    host_task: asyncio.Task[None] | None = None
    try:
        await asyncio.sleep(0.15)
        assert not store.snapshot().connected
        host_task = asyncio.create_task(
            WebSocketHost(host_config, TOKEN).run(host_stop, host_started)
        )
        await asyncio.wait_for(host_started.wait(), timeout=2)
        await wait_for_transport(store)
        assert store.snapshot().connected
    finally:
        client_stop.set()
        await asyncio.wait_for(client_task, timeout=2)
        host_stop.set()
        if host_task is not None:
            await asyncio.wait_for(host_task, timeout=2)


def test_pi_client_reconnects_when_server_becomes_available() -> None:
    asyncio.run(exercise_reconnect_after_server_appears())
