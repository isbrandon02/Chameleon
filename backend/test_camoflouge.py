import pytest
from camoflouge import parse_timestamps, to_seconds


def test_to_seconds():
    assert to_seconds("1:02:03") == 3723
    assert to_seconds("0:05") == 5
    assert to_seconds("12") == 12


def test_parse_timestamps_simple():
    text = "00:00:05 - 00:00:12\n1:02-1:09"
    assert parse_timestamps(text) == [(5, 12), (62, 69)]


def test_parse_timestamps_random_format():
    text = "3:21 - 4:00\n10:00-12:30"
    assert parse_timestamps(text) == [(201, 240), (600, 750)]
