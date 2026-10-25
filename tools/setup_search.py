"""Create a private SearXNG config once; never overwrite existing settings."""
from pathlib import Path
import secrets


def main(root=None):
    root = Path(root or Path(__file__).resolve().parents[1])
    folder = root / "searxng"
    folder.mkdir(exist_ok=True)
    (folder / "data").mkdir(exist_ok=True)
    config = folder / "settings.yml"
    try:
        with config.open("x", encoding="utf-8") as f:
            f.write("""use_default_settings:
  engines:
    keep_only: [google, bing, duckduckgo, brave]
general:
  instance_name: CampusScraper Search
search:
  formats: [html, json]
server:
  bind_address: "0.0.0.0"
  port: 8080
  limiter: false
  public_instance: false
  secret_key: """ + '"' + secrets.token_hex(32) + '"\n' + """outgoing:
  request_timeout: 10.0
  max_request_timeout: 15.0
engines:
  - name: google
    disabled: false
  - name: bing
    disabled: false
  - name: duckduckgo
    disabled: false
  - name: brave
    disabled: false
""")
        print("Created searxng/settings.yml with a random secret.")
    except FileExistsError:
        print("Keeping existing searxng/settings.yml.")
    print("Start search: docker compose -f compose.search.yml up -d")


if __name__ == "__main__":
    main()
