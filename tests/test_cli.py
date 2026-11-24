import pytest

from harvestweb.cli import main as cli


@pytest.mark.parametrize("command", ["review", "scrape", "search", "map", "crawl"])
def test_main_dispatches_to_selected_handler(monkeypatch, command):
    def run(args):
        assert args.command == command
        return 17

    monkeypatch.setattr(cli, f"_run_{command}", run)

    assert cli.main([command, "https://example.com"]) == 17
