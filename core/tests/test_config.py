import pytest

from loredock.config import Settings


def test_local_bind_is_allowed() -> None:
    Settings(host="127.0.0.1").assert_safe_bind_host()


def test_non_loopback_bind_is_rejected() -> None:
    with pytest.raises(ValueError, match="loopback"):
        Settings(host="0.0.0.0").assert_safe_bind_host()
