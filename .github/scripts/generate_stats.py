#!/usr/bin/env python3
"""
Regenerates assets/telemetry.svg from live GitHub data.

Run by .github/workflows/update-stats.yml on a daily schedule.
Reads:  env GH_TOKEN  (a token with read access to the account)
        env GH_USER   (the GitHub login to render)
Writes: assets/telemetry.svg

Pure standard library — no pip install needed.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime

USER = os.environ.get("GH_USER", "L0rdDarkk")
TOKEN = os.environ.get("GH_TOKEN", "")
OUT = os.path.join("assets", "telemetry.svg")

# console theme — language segments/legend reuse these so the panel stays on-brand
PALETTE = ["#00f7a5", "#4fe3ff", "#ffb000", "#ff4d5e", "#8a63d2", "#6b7f90"]

GRAPHQL = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": f"{USER}-profile-stats",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if "errors" in payload:
        raise RuntimeError(json.dumps(payload["errors"]))
    return payload["data"]


def collect():
    data = gql(GRAPHQL, {"login": USER})["user"]
    cc = data["contributionsCollection"]
    cal = cc["contributionCalendar"]

    repos = data["repositories"]["nodes"]
    stars = sum(r["stargazerCount"] for r in repos)

    # aggregate language sizes + remember each language's GitHub color
    sizes, colors = {}, {}
    for r in repos:
        for e in r["languages"]["edges"]:
            name = e["node"]["name"]
            sizes[name] = sizes.get(name, 0) + e["size"]
            colors.setdefault(name, e["node"]["color"] or "#6b7f90")

    # flatten the calendar to an ordered list of daily counts
    days = []
    for wk in cal["weeks"]:
        for d in wk["contributionDays"]:
            days.append((d["date"], d["contributionCount"]))
    days.sort()
    counts = [c for _, c in days]

    # current streak = trailing run of non-zero days; longest = max run in window
    cur = 0
    for c in reversed(counts):
        if c > 0:
            cur += 1
        else:
            break
    longest = run = 0
    for c in counts:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)

    return {
        "commits": cc["totalCommitContributions"] + cc.get("restrictedContributionsCount", 0),
        "contrib": cal["totalContributions"],
        "repos": data["repositories"]["totalCount"],
        "followers": data["followers"]["totalCount"],
        "stars": stars,
        "prs": cc["totalPullRequestContributions"],
        "sizes": sizes,
        "colors": colors,
        "recent": counts[-28:],
        "cur_streak": cur,
        "longest_streak": longest,
    }


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_svg(s):
    # ---- metric tiles ----
    tiles = [
        (s["commits"], "COMMITS", "#00f7a5"),
        (s["contrib"], "CONTRIB", "#00f7a5"),
        (s["repos"], "REPOS", "#00f7a5"),
        (s["followers"], "FOLLOWERS", "#4fe3ff"),
        (s["stars"], "STARS", "#ffb000"),
        (s["prs"], "PULL REQ", "#ff4d5e"),
    ]
    cx = [93, 232, 370, 509, 648, 786]
    nums = "".join(
        f'<text x="{cx[i]}" y="96" fill="{c}">{esc(v)}</text>'
        for i, (v, _, c) in enumerate(tiles)
    )
    labels = "".join(
        f'<text x="{cx[i]}" y="114">{esc(lbl)}</text>' for i, (_, lbl, _) in enumerate(tiles)
    )

    # ---- language distribution ----
    total = sum(s["sizes"].values()) or 1
    ranked = sorted(s["sizes"].items(), key=lambda kv: kv[1], reverse=True)
    top = ranked[:6]

    segs, x = [], 24.0
    for i, (name, size) in enumerate(top):
        w = size / total * 832.0
        segs.append(
            f'<rect x="{x:.1f}" y="170" height="14" fill="{PALETTE[i]}">'
            f'<animate attributeName="width" from="0" to="{w:.1f}" begin="{0.3 + i*0.12:.2f}s" dur="0.7s" fill="freeze"/></rect>'
        )
        x += w
    if x < 856:  # fill any remainder so the bar reads full
        segs.append(f'<rect x="{x:.1f}" y="170" width="{856 - x:.1f}" height="14" fill="#2a3340"/>')

    legend, lx = [], 24
    for i, (name, size) in enumerate(top):
        p = size / total * 100
        pct = f"{p:.1f}%" if p >= 1 else f"{p:.2f}%"
        label = f"{name} {pct}"
        legend.append(
            f'<circle cx="{lx+4}" cy="205" r="4" fill="{PALETTE[i]}"/>'
            f'<text x="{lx+14}" y="209">{esc(label)}</text>'
        )
        lx += int(len(label) * 7.1) + 26

    # ---- contribution activity equalizer (last 28 days, real heights) ----
    recent = s["recent"] or [0] * 28
    recent = ([0] * (28 - len(recent)) + recent)[-28:]
    peak = max(recent) or 1
    bars = []
    for i, c in enumerate(recent):
        h = 22 + (c / peak) * 34  # 22..56 px
        y = 314 - h
        if c == 0:
            fill = "#0e3b2c"
        elif c >= 0.75 * peak:
            fill = "#00f7a5"
        elif c >= 0.4 * peak:
            fill = "#1a7a57"
        else:
            fill = "#12543d"
        delay = -((i * 0.13) % 1.3)
        bars.append(
            f'<rect x="{24 + i*30}" y="{y:.1f}" width="18" height="{h:.1f}" rx="2" '
            f'fill="{fill}" style="animation-delay:{delay:.2f}s"/>'
        )

    return SVG_TEMPLATE.format(
        nums=nums,
        labels=labels,
        segs="".join(segs),
        legend="".join(legend),
        bars="".join(bars),
        contrib=esc(s["contrib"]),
        cur=esc(s["cur_streak"]),
        longest=esc(s["longest_streak"]),
        year=datetime.utcnow().year,
    )


SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 880 352" width="880" height="352" font-family="'JetBrains Mono','Fira Code',ui-monospace,Consolas,monospace" role="img" aria-label="L0rdDarkk git telemetry">
  <defs>
    <linearGradient id="tpanel" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0b1017"/><stop offset="1" stop-color="#070b11"/>
    </linearGradient>
    <pattern id="tgrid" width="26" height="26" patternUnits="userSpaceOnUse">
      <path d="M26 0H0V26" fill="none" stroke="#17202b" stroke-width="1"/>
    </pattern>
    <style>
      .eq rect {{ transform-box: fill-box; transform-origin: bottom; animation: eq 1.3s ease-in-out infinite; }}
      @keyframes eq {{ 0%,100% {{ transform: scaleY(0.22); }} 50% {{ transform: scaleY(1); }} }}
    </style>
  </defs>
  <rect x="1" y="1" width="878" height="350" rx="14" fill="url(#tpanel)" stroke="#1b2a1f" stroke-width="1.5"/>
  <rect x="14" y="44" width="852" height="294" fill="url(#tgrid)" opacity="0.5"/>

  <circle cx="28" cy="24" r="5.5" fill="#ff5f57"/><circle cx="48" cy="24" r="5.5" fill="#febc2e"/><circle cx="68" cy="24" r="5.5" fill="#28c840"/>
  <text x="92" y="29" fill="#4a5a6a" font-size="13">l0rddarkk@darknet: ~/telemetry — git-ops</text>
  <text x="856" y="29" fill="#2f6b4f" font-size="12" text-anchor="end">updated {year}</text>
  <line x1="0" y1="42" x2="880" y2="42" stroke="#161f29"/>

  <g text-anchor="middle">
    <g font-size="30" font-weight="700">{nums}</g>
    <g font-size="10.5" fill="#6b7f90" letter-spacing="1.5">{labels}</g>
  </g>
  <line x1="162" y1="72" x2="162" y2="108" stroke="#161f29"/><line x1="301" y1="72" x2="301" y2="108" stroke="#161f29"/>
  <line x1="440" y1="72" x2="440" y2="108" stroke="#161f29"/><line x1="579" y1="72" x2="579" y2="108" stroke="#161f29"/>
  <line x1="718" y1="72" x2="718" y2="108" stroke="#161f29"/>
  <line x1="0" y1="130" x2="880" y2="130" stroke="#161f29"/>

  <text x="24" y="158" font-size="11.5" fill="#6b7f90" letter-spacing="2">LANGUAGE DISTRIBUTION</text>
  <rect x="24" y="170" width="832" height="14" rx="4" fill="#0f1620"/>
  <clipPath id="barclip"><rect x="24" y="170" width="832" height="14" rx="4"/></clipPath>
  <g clip-path="url(#barclip)">{segs}</g>
  <g font-size="11.5" fill="#9fb0bf">{legend}</g>
  <line x1="0" y1="228" x2="880" y2="228" stroke="#161f29"/>

  <text x="24" y="256" font-size="11.5" fill="#6b7f90" letter-spacing="2">CONTRIBUTION ACTIVITY</text>
  <g class="eq">{bars}</g>
  <text x="24" y="336" font-size="11" fill="#2f6b4f">{contrib} contributions</text>
  <text x="856" y="336" font-size="11" fill="#2f4150" text-anchor="end">current: {cur} · longest streak: {longest}</text>
</svg>
"""


def main():
    if not TOKEN:
        sys.exit("GH_TOKEN not set — add a repo secret and pass it to the workflow.")
    stats = collect()
    svg = build_svg(stats)
    os.makedirs("assets", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {OUT}: {stats['commits']} commits, {stats['contrib']} contrib, "
          f"{stats['repos']} repos, {stats['stars']} stars, streak {stats['cur_streak']}/{stats['longest_streak']}")


if __name__ == "__main__":
    main()
