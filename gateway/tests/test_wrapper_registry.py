import pytest

from app.wrappers.base import ToolWrapper
from app.wrappers.httpx import HttpxWrapper
from app.wrappers.registry import UnknownWrapperError, available_wrappers, get_wrapper
from app.wrappers.subfinder import SubfinderWrapper


def test_get_known_wrappers() -> None:
    assert isinstance(get_wrapper("subfinder"), SubfinderWrapper)
    assert isinstance(get_wrapper("httpx"), HttpxWrapper)
    assert isinstance(get_wrapper("subfinder"), ToolWrapper)


def test_get_unknown_raises() -> None:
    with pytest.raises(UnknownWrapperError):
        get_wrapper("inconnu")


def test_available_wrappers_contains_both() -> None:
    names = available_wrappers()
    assert "subfinder" in names
    assert "httpx" in names
    assert names == sorted(names)
