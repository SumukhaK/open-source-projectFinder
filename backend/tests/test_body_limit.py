import asyncio

from app.core.config import Settings
from app.main import BodyLimit

SCOPE = {"type": "http", "path": "/auth/session"}


def run(messages):
    received, calls = list(messages), []

    async def receive():
        return received.pop(0)

    async def app(scope, receive, send):
        calls.append(await receive())
        calls.append(await receive())

    limited = BodyLimit(app, ("/auth/",), Settings(_env_file=None))
    asyncio.run(limited(SCOPE, receive, None))
    return calls


def test_disconnect_while_buffering_never_reaches_the_app():
    calls = run(
        [{"type": "http.request", "body": b"{", "more_body": True}]
        + [{"type": "http.disconnect"}]
    )
    assert calls == []


def test_buffered_body_is_replayed_once_then_later_messages_pass_through():
    calls = run(
        [
            {"type": "http.request", "body": b'{"a":', "more_body": True},
            {"type": "http.request", "body": b"1}", "more_body": False},
            {"type": "http.disconnect"},
        ]
    )
    assert calls == [
        {"type": "http.request", "body": b'{"a":1}', "more_body": False},
        {"type": "http.disconnect"},
    ]
