#!/usr/bin/env python3
"""Generate profile SVG cards from GitHub's public API, without third-party renderers."""
import datetime as dt
import html
import json
import math
import os
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

USER = "CatSeed"
PUBLIC_TOKEN = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN", "")
REPOS_TOKEN = os.getenv("PROFILE_REPOS_TOKEN", "")
ACTIVITY_TOKEN = os.getenv("PROFILE_ACTIVITY_TOKEN", "")
OUT = Path("dist")
OUT.mkdir(exist_ok=True)


def request_json(url, payload=None, token=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "CatSeed-profile-workflow",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token is None:
        token = PUBLIC_TOKEN
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(url, data=body, headers=headers), timeout=25) as response:
            return json.load(response)
    except HTTPError as exc:
        # Never print API endpoints: private repository paths must not leak into public logs.
        raise RuntimeError(f"GitHub API request failed (HTTP {exc.code})") from exc


def get_languages():
    if REPOS_TOKEN:
        actor = request_json("https://api.github.com/user", token=REPOS_TOKEN)
        if actor.get("login", "").lower() != USER.lower():
            raise RuntimeError("PROFILE_REPOS_TOKEN belongs to the wrong GitHub account")
    totals = Counter()
    counted = 0
    page = 1
    while page <= 10:
        if REPOS_TOKEN:
            repos = request_json(f"https://api.github.com/user/repos?per_page=100&page={page}&affiliation=owner&visibility=all", token=REPOS_TOKEN)
        else:
            repos = request_json(f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}&type=owner")
        if not isinstance(repos, list):
            raise RuntimeError(f"Unexpected repositories response: {repos}")
        for repo in repos:
            if repo.get("fork") or repo.get("archived") or (repo.get("private") and not REPOS_TOKEN):
                continue
            counted += 1
            languages = request_json(repo["languages_url"], token=REPOS_TOKEN or PUBLIC_TOKEN)
            for language, size in languages.items():
                if size > 0:
                    totals[language] += size
        if len(repos) < 100:
            break
        page += 1
    if not totals:
        raise RuntimeError("No languages returned from repositories visible to the selected token")
    return totals, counted


def get_activity():
    if ACTIVITY_TOKEN:
        actor = request_json("https://api.github.com/user", token=ACTIVITY_TOKEN)
        if actor.get("login", "").lower() != USER.lower():
            raise RuntimeError("PROFILE_ACTIVITY_TOKEN belongs to the wrong GitHub account")
    now = dt.datetime.now(dt.timezone.utc)
    dates = [(now.date() - dt.timedelta(days=i)) for i in range(30, -1, -1)]
    begin = dt.datetime.combine(dates[0], dt.time.min, tzinfo=dt.timezone.utc)
    query = """query($login:String!, $from:DateTime!, $to:DateTime!){
      user(login:$login){contributionsCollection(from:$from,to:$to){
        contributionCalendar{weeks{contributionDays{date contributionCount}}}
      }}
    }"""
    try:
        graph = request_json("https://api.github.com/graphql", {
            "query": query,
            "variables": {"login": USER, "from": begin.isoformat(), "to": now.isoformat()}
        }, token=ACTIVITY_TOKEN or PUBLIC_TOKEN)
        if graph.get("errors"):
            raise RuntimeError(str(graph["errors"])[:250])
        weeks = graph["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        date_to_count = {day["date"]: day["contributionCount"] for week in weeks for day in week["contributionDays"]}
        values = [date_to_count.get(day.isoformat(), 0) for day in dates]
        if not date_to_count:
            raise RuntimeError("Empty contribution calendar")
        label = "Public + private GitHub contributions" if ACTIVITY_TOKEN else "Public contributions (private not verified)"
        return dates, values, label, "GitHub contribution calendar, last 31 days"
    except Exception as exc:
        if ACTIVITY_TOKEN:
            raise RuntimeError("Private contribution query failed: check read:user permission") from exc
        print("Public contribution calendar unavailable; falling back to public events.")
        counts = Counter()
        seen = set()
        for page in range(1, 4):
            events = request_json(f"https://api.github.com/users/{USER}/events/public?per_page=100&page={page}")
            if not isinstance(events, list):
                raise RuntimeError("Public events API returned an invalid response")
            for event in events:
                if event.get("id") in seen:
                    continue
                seen.add(event.get("id"))
                date = event.get("created_at", "")[:10]
                if date:
                    counts[date] += 1
            if len(events) < 100:
                break
        if not seen:
            raise RuntimeError("Neither contribution calendar nor public events are available")
        values = [counts[day.isoformat()] for day in dates]
        return dates, values, "Public GitHub events only", "Public events only; this is not a complete contribution calendar."


def svg_frame(inner, width, height, title, note):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title, quote=True)}">
<rect x="0.5" y="0.5" width="{width-1}" height="{height-1}" rx="6" fill="#0d1117" stroke="#30363d"/>
<text x="25" y="36" font-family="Arial, sans-serif" font-size="17" font-weight="700" fill="#7ee787">{html.escape(title)}</text>
<text x="25" y="59" font-family="Arial, sans-serif" font-size="11" fill="#8b949e">{html.escape(note)}</text>
{inner}
</svg>'''


def language_svg(totals, repo_count):
    width, height = 670, 355
    total = sum(totals.values())
    colors = ["#39d353", "#7ee787", "#2ea44f", "#80cc9a", "#31724d", "#a8e5bd", "#267448"]
    rows = []
    for i, (lang, byte_count) in enumerate(totals.most_common(7)):
        percentage = byte_count * 100 / total
        y = 89 + i * 35
        barw = 390 * (percentage / 100)
        rows.append(f'<text x="26" y="{y+7}" fill="#c9d1d9" font-family="Arial,sans-serif" font-size="13">{html.escape(lang)}</text>')
        rows.append(f'<rect x="185" y="{y-7}" width="390" height="11" rx="2" fill="#21262d"/>')
        rows.append(f'<rect x="185" y="{y-7}" width="{barw:.2f}" height="11" rx="2" fill="{colors[i]}"/>')
        rows.append(f'<text x="636" y="{y+6}" text-anchor="end" fill="#c9d1d9" font-family="Arial,sans-serif" font-size="12">{percentage:.1f}%</text>')
    rows.append('<text x="25" y="340" fill="#8b949e" font-family="Arial,sans-serif" font-size="10">Share of detected language bytes; not proficiency or coding time.</text>')
    label = "Public + authorised private repos" if REPOS_TOKEN else "Public repos only — private access not configured"
    return svg_frame("\n".join(rows), width, height, "LANGUAGE INVENTORY", label)


def activity_svg(dates, values, source, caption):
    width, height = 825, 290
    x0, y0, x1, y1 = 55, 88, 790, 226
    top = max(4, math.ceil(max(max(values), 1) / 4) * 4)
    points = []
    for i, n in enumerate(values):
        x = x0 + (x1-x0) * i / (len(values)-1)
        y = y1 - (y1-y0) * n / top
        points.append((x,y))
    elems = []
    for k in range(5):
        amount = top * k / 4
        y = y1 - (y1-y0) * k/4
        elems.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#21262d"/>')
        elems.append(f'<text x="{x0-10}" y="{y+4:.1f}" text-anchor="end" fill="#8b949e" font-family="Arial,sans-serif" font-size="11">{amount:g}</text>')
    for index in [0, 7, 14, 21, 30]:
        x = points[index][0]
        elems.append(f'<text x="{x:.1f}" y="247" text-anchor="middle" fill="#8b949e" font-family="Arial,sans-serif" font-size="11">{dates[index].strftime("%b %d")}</text>')
    path = " ".join(("M" if i == 0 else "L") + f"{x:.2f},{y:.2f}" for i, (x,y) in enumerate(points))
    area = path + f" L{x1},{y1} L{x0},{y1} Z"
    elems.append('<defs><linearGradient id="area" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#39d353" stop-opacity="0.30"/><stop offset="1" stop-color="#39d353" stop-opacity="0.015"/></linearGradient></defs>')
    elems.append(f'<path d="{area}" fill="url(#area)"/>')
    elems.append(f'<path d="{path}" fill="none" stroke="#39d353" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>')
    for i,(x,y) in enumerate(points):
        if values[i] > 0:
            elems.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.8" fill="#7ee787"/>')
    elems.append(f'<text x="790" y="59" text-anchor="end" fill="#c9d1d9" font-family="Arial,sans-serif" font-size="12">Total: {sum(values)}</text>')
    elems.append(f'<text x="25" y="273" fill="#8b949e" font-family="Arial,sans-serif" font-size="11">{html.escape(caption)}</text>')
    return svg_frame("\n".join(elems), width, height, "ACTIVITY MAP", source)


def main():
    totals, nrepos = get_languages()
    dates, counts, source, caption = get_activity()
    (OUT / "languages.svg").write_text(language_svg(totals, nrepos), encoding="utf-8")
    (OUT / "activity.svg").write_text(activity_svg(dates, counts, source, caption), encoding="utf-8")
    print("Generated language distribution (no repository names or raw language sizes logged).")
    print("Generated contribution activity (daily totals only; no private repository details logged).")


if __name__ == "__main__":
    main()
