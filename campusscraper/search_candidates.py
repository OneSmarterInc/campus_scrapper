"""Cheap search triage. Ranking is a hint; page evidence still decides eligibility."""
import re
from collections import defaultdict, deque
from urllib.parse import urlsplit


REFERENCE_HOSTS = (
    "dictionary.cambridge.org", "dictionary.com", "thesaurus.com",
    "merriam-webster.com", "collinsdictionary.com", "wiktionary.org",
    "oxfordlearnersdictionaries.com", "dictionary.langeek.co",
)


def exclusion_reason(url):
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return "Malformed source URL"
    if any(host == h or host.endswith("." + h) for h in REFERENCE_HOSTS):
        return "Reference/dictionary site, not an official campus staff source"
    return ""


def rank_urls(urls, details, context):
    """Prefer relevant campus pages, then interleave hosts to avoid one-site floods.

    No institution, city or TLD allowlist. A school on .org/.com remains eligible;
    titles/snippets are never accepted as evidence of ownership or location.
    """
    valid = []
    for url in dict.fromkeys(urls):
        try:
            parts = urlsplit(url)
            if parts.scheme in {"https", "http"} and parts.hostname and not parts.username and not parts.password:
                valid.append(url)
        except ValueError:
            continue
    terms = set(re.findall(r"\w{3,}", context.casefold())) - {
        "the", "for", "and", "from", "with", "find", "must", "site", "https", "www",
        "faculty", "directory", "official", "website", "urls", "college", "colleges",
    }
    def score(url):
        d = details.get(url, {})
        text = " ".join([url, d.get("title", ""), d.get("content", "")]).casefold()
        words = set(re.findall(r"\w{3,}", text))
        host = (urlsplit(url).hostname or "").lower()
        academic = bool(re.search(r"\.(?:ac\.[a-z]{2}|edu(?:\.[a-z]{2})?)$", host))
        return (6 * len(terms & words)
                + 5 * bool(re.search(r"college|university|institute|institution", text))
                + 4 * bool(re.search(r"facult|staff|people|department", text)) + 2 * academic)
    groups = defaultdict(deque)
    for url in sorted(valid, key=score, reverse=True):
        groups[urlsplit(url).netloc.lower()].append(url)
    ordered = []
    while groups:
        for host in list(groups):
            ordered.append(groups[host].popleft())
            if not groups[host]:
                del groups[host]
    return ordered


def relaxed_queries(queries, searched):
    """Remove exact-phrase/TLD syntax for another search, never change the plan."""
    output = []
    for query in queries:
        # Keep negative site filters; those may express an explicit exclusion.
        relaxed = re.sub(r"(?<!\S)site:\S+\s*", "", query).replace('"', '')
        relaxed = " ".join(relaxed.split())
        if relaxed and relaxed != query and relaxed not in searched and relaxed not in output:
            output.append(relaxed)
    return output[:3]
