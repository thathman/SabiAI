from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
import time

from sabiai.sources import Source, SourceKind, SourceRegistry, SourceRequest, SourceService
from sabiai.storage import SabiDatabase


def test_identical_concurrent_requests_share_one_network_fetch(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    registry = SourceRegistry()
    registry.register(
        Source(
            name="free-test",
            kind=SourceKind.PUBLIC_ENDPOINT,
            capabilities={"fixtures"},
        )
    )
    service = SourceService(db, registry)
    calls = {"count": 0}
    lock = Lock()

    def fetcher(request):
        with lock:
            calls["count"] += 1
        time.sleep(0.12)
        return {"events": [request.request_key]}

    request = SourceRequest(
        request_key="football:fixtures:today",
        capability="fixtures",
        sport="football",
        ttl_seconds=60,
    )

    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(
            pool.map(
                lambda _: service.execute(request, {"free-test": fetcher}),
                range(6),
            )
        )

    assert calls["count"] == 1
    assert all(response.payload == {"events": ["football:fixtures:today"]} for response in responses)
    assert sum(1 for response in responses if response.cache_hit) >= 5


def test_different_request_keys_do_not_coalesce(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    registry = SourceRegistry()
    registry.register(Source(name="free-test", kind=SourceKind.PUBLIC_ENDPOINT, capabilities={"fixtures"}))
    service = SourceService(db, registry)
    calls = {"count": 0}
    lock = Lock()

    def fetcher(request):
        with lock:
            calls["count"] += 1
        time.sleep(0.05)
        return {"key": request.request_key}

    requests = [
        SourceRequest(request_key=f"fixture:{idx}", capability="fixtures", ttl_seconds=60)
        for idx in range(4)
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda req: service.execute(req, {"free-test": fetcher}), requests))

    assert calls["count"] == 4
    assert {response.payload["key"] for response in responses} == {f"fixture:{idx}" for idx in range(4)}
