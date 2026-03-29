"""Unit tests for CLI argument parsing."""

import pytest

from migrator.cli import _build_parser


REQUIRED_ARGS = [
    "--profile-url", "https://www.fragrantica.com/member/123",
    "--parfumo-user", "testuser",
    "--parfumo-pass", "testpass",
]


def parse(extra=None):
    parser = _build_parser()
    return parser.parse_args(REQUIRED_ARGS + (extra or []))


def test_required_flags_parsed():
    args = parse()
    assert args.profile_url == "https://www.fragrantica.com/member/123"
    assert args.parfumo_user == "testuser"
    assert args.parfumo_pass == "testpass"


def test_defaults():
    args = parse()
    assert args.data_type == "reviews"
    assert args.confidence == 80
    assert args.output is None
    assert args.headless is False


def test_data_type_flag():
    args = parse(["--data-type", "ratings"])
    assert args.data_type == "ratings"


def test_confidence_flag():
    args = parse(["--confidence", "90"])
    assert args.confidence == 90


def test_output_flag():
    args = parse(["--output", "/tmp/report.txt"])
    assert args.output == "/tmp/report.txt"


def test_headless_flag():
    args = parse(["--headless"])
    assert args.headless is True


def test_missing_parfumo_pass_exits(capsys):
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args([
            "--profile-url", "https://www.fragrantica.com/member/123",
            "--parfumo-user", "testuser",
            # --parfumo-pass intentionally omitted
        ])
    assert exc_info.value.code != 0


def test_missing_profile_url_exits():
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args([
            "--parfumo-user", "testuser",
            "--parfumo-pass", "testpass",
        ])
    assert exc_info.value.code != 0


def test_missing_parfumo_user_exits():
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args([
            "--profile-url", "https://www.fragrantica.com/member/123",
            "--parfumo-pass", "testpass",
        ])
    assert exc_info.value.code != 0
