"""Generated local service settings must be safe to rerun on Windows/Linux."""
from pathlib import Path
import importlib.util

def test_setup_search_preserves_existing_configuration(tmp_path):
    source = Path(__file__).resolve().parents[1] / "tools" / "setup_search.py"
    spec = importlib.util.spec_from_file_location("setup_search", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main(tmp_path)
    path = tmp_path / "searxng" / "settings.yml"
    original = path.read_text()
    assert "formats: [html, json]" in original
    assert "secret_key:" in original and "limiter: false" in original
    module.main(tmp_path)
    assert path.read_text() == original
    assert (tmp_path / "searxng" / "data").is_dir()


def test_compose_search_binds_only_localhost():
    root = Path(__file__).resolve().parents[1]
    config = (root / "compose.search.yml").read_text()
    assert '"127.0.0.1:8080:8080"' in config
    assert "settings.yml:ro" in config
    assert "mem_limit:" in config and "cpus:" in config
