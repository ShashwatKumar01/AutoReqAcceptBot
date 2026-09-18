from app.core.deep_links import parse_welcome_start, welcome_deeplink, welcome_start_payload


def test_welcome_payload_roundtrip():
    cid = -1002616119812
    assert welcome_start_payload(cid) == "wel_-1002616119812"
    assert parse_welcome_start("wel_-1002616119812") == cid


def test_welcome_deeplink():
    url = welcome_deeplink("mybot", -100123)
    assert url == "https://t.me/mybot?start=wel_-100123"


def test_parse_invalid():
    assert parse_welcome_start(None) is None
    assert parse_welcome_start("foo") is None
    assert parse_welcome_start("wel_") is None
