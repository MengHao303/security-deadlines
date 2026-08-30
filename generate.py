#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate ICS / HTML / Markdown from deadlines.json (stdlib only).

Usage: python3 generate.py
Outputs: docs/security-deadlines.ics, docs/index.html, docs/deadlines.md
(docs/ doubles as the GitHub Pages source directory)
"""
import datetime
import hashlib
import html
import json
import pathlib

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / "deadlines.json"
OUT = ROOT / "docs"

KIND_LABEL = {
    "abstract": "Abstract reg.",
    "registration": "Mandatory reg.",
    "submission": "Paper deadline",
    "notification": "Notification",
    "camera-ready": "Camera-ready",
    "conference": "Conference",
}

# 需要 VALARM 提醒的事件类型 -> (提前天数列表)
ALARM_DAYS = {
    "abstract": (7, 1),
    "registration": (7, 1),
    "submission": (7, 1),
    "notification": (1,),
    "camera-ready": (1,),
    "conference": (7, 1),
}


def parse_date(s):
    return datetime.date.fromisoformat(s) if s else None


def add_days(d, n):
    return d + datetime.timedelta(days=n)


def load():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    return data


def collect_events(data):
    """展平为事件记录列表，附带会议信息与状态。"""
    today = datetime.date.today()
    events = []
    for conf in data["conferences"]:
        for ev in conf["events"]:
            d = parse_date(ev["date"])
            status = "tba" if d is None else ("passed" if d < today else "upcoming")
            events.append({**ev, "conf": conf, "date_obj": d, "status": status})
    return events


def sort_events(events):
    upcoming = sorted(
        [e for e in events if e["status"] == "upcoming"],
        key=lambda e: e["date_obj"],
    )
    passed = sorted(
        [e for e in events if e["status"] == "passed"],
        key=lambda e: e["date_obj"],
        reverse=True,
    )
    tba = [e for e in events if e["status"] == "tba"]
    return upcoming + tba + passed


def uid_for(conf, ev):
    raw = f"{conf['id']}:{ev['kind']}:{ev['label']}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()[:16] + "@deadline-calendar"


def ics_escape(s):
    return (
        s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    )


def ics_fold(line):
    """RFC 5545 行折叠：UTF-8 字节层每 75 字节折叠，回退到完整字符边界。"""
    raw = line.encode("utf-8")
    parts = []
    while len(raw) > 75:
        cut = 75
        while True:
            try:
                raw[:cut].decode("utf-8")
                break
            except UnicodeDecodeError:
                cut -= 1  # 不切断多字节字符
        parts.append(raw[:cut].decode("utf-8"))
        raw = b" " + raw[cut:]  # 续行以空格开头
    parts.append(raw.decode("utf-8"))
    return "\r\n".join(parts) + "\r\n"


def gen_ics(data):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//deadline-calendar//security-deadlines//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for ev in sort_events(collect_events(data)):
        conf = ev["conf"]
        if ev["date_obj"] is None:
            continue  # TBA 事件无法建日历条目
        prefix = "EST. " if ev["estimated"] else ""
        summary = f"{prefix}{conf['short_name']} {ev['label']}"
        desc_parts = [
            conf["full_name"],
            f"Event: {ev['label']}",
            f"Official source: {conf['source_url']}",
            f"Data verified on: {conf['verified_on']}",
        ]
        if ev["tz_note"]:
            desc_parts.append(f"Timezone: {ev['tz_note']} (until 19:59 SGT the next day)")
        if ev["estimated"]:
            desc_parts.append(f"NOTE: CFP not yet published; date projected from {ev['estimated_from']} — verify before relying on it")
        if ev["kind"] == "conference":
            desc_parts.append(f"Location: {conf['location']}")
        description = "\\n".join(desc_parts)

        start = ev["date_obj"]
        end = parse_date(ev["date_end"]) if ev.get("date_end") else None
        dtend = add_days(end or start, 1)

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid_for(conf, ev)}",
            f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
            f"DTEND;VALUE=DATE:{dtend:%Y%m%d}",
            f"SUMMARY:{ics_escape(summary)}",
            f"DESCRIPTION:{ics_escape(description)}",
        ]
        if ev["kind"] == "conference":
            lines.append(f"LOCATION:{ics_escape(conf['location'])}")
        for days in ALARM_DAYS.get(ev["kind"], (1,)):
            lines += [
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{ics_escape(summary)}",
                f"TRIGGER:-P{days}D",
                "END:VALARM",
            ]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "".join(ics_fold(l) for l in lines)


def fmt_date(ev):
    if ev["date_obj"] is None:
        return "TBA"
    d = ev["date_obj"]
    if ev.get("date_end"):
        e = parse_date(ev["date_end"])
        if e:
            return f"{d:%Y-%m-%d} ~ {e:%Y-%m-%d}"
    return f"{d:%Y-%m-%d}"


def gen_md(data):
    today = datetime.date.today()
    out = [
        "# Top-4 Security Conference Deadline Calendar",
        "",
        f"> Data last updated {data['updated_at']} (generated {today:%Y-%m-%d}).",
        "> Dates are as stated by the official CFPs, timezone **AoE (UTC-12)** — in Singapore time (UTC+8) deadlines effectively extend to **19:59 the next day**.",
        "> ⚠️ Rows marked \"est.\": CFP not yet published; dates are projected from past cycles and must be verified.",
        "",
    ]
    for conf in data["conferences"]:
        out.append(f"## {conf['short_name']}")
        out.append("")
        meta = conf["full_name"]
        if conf["conference_dates"]:
            cd = conf["conference_dates"]
            meta += f" (conference {cd['start']} ~ {cd['end']})"
        meta += f", {conf['location']}"
        out.append(f"{meta}  \n[Official source]({conf['source_url']}) · verified {conf['verified_on']}")
        out.append("")
        out.append("| Date | Event | Kind | Notes |")
        out.append("|---|---|---|---|")
        events = [e for e in collect_events(data) if e["conf"]["id"] == conf["id"]]
        for ev in sort_events(events):
            notes = []
            if ev["estimated"]:
                notes.append(f"est. (from {ev['estimated_from']})")
            if ev["status"] == "passed":
                notes.append("passed")
            note = "; ".join(notes) if notes else "—"
            out.append(f"| {fmt_date(ev)} | {ev['label']} | {KIND_LABEL.get(ev['kind'], ev['kind'])} | {note} |")
        out.append("")
    return "\n".join(out) + "\n"


# ---------- HTML ----------

CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, "SF Pro Text", "PingFang SC", "Segoe UI", "Microsoft YaHei", sans-serif;
  margin: 0; padding: 2rem 1rem; background: #f6f7f9; color: #1c1e21;
  line-height: 1.55;
}
@media (prefers-color-scheme: dark) {
  body { background: #101214; color: #e8eaed; }
  .card { background: #1a1d21 !important; border-color: #2c3138 !important; }
  table th { background: #22262c !important; }
  tr.passed { color: #6b7280 !important; }
  tr.estimated { background: #2b2418 !important; }
}
.wrap { max-width: 900px; margin: 0 auto; }
h1 { font-size: 1.6rem; margin: 0 0 .3rem; }
.sub { color: #6b7280; font-size: .9rem; margin-bottom: 1.2rem; }
.notes {
  background: #eef4ff; border: 1px solid #c8d8f5; border-radius: 8px;
  padding: .7rem 1rem; font-size: .88rem; margin-bottom: 1.4rem; color: #27466e;
}
@media (prefers-color-scheme: dark) {
  .notes { background: #16202e; border-color: #2a3d5c; color: #a9c4ec; }
}
.card {
  background: #fff; border: 1px solid #e2e5ea; border-radius: 10px;
  padding: 1.1rem 1.3rem; margin-bottom: 1.2rem;
}
.card h2 { margin: 0 0 .2rem; font-size: 1.2rem; }
.card .meta { font-size: .85rem; color: #6b7280; margin-bottom: .7rem; }
.card .meta a { color: inherit; }
table { width: 100%; border-collapse: collapse; font-size: .92rem; }
th, td { text-align: left; padding: .45rem .55rem; border-bottom: 1px solid #eceef1; vertical-align: top; }
th { background: #fafbfc; font-weight: 600; color: #4b5563; white-space: nowrap; }
tr.passed td { color: #9ca3af; text-decoration: line-through; }
tr.estimated td { background: #fdf6e3; }
.badge {
  display: inline-block; padding: .05rem .5rem; border-radius: 999px;
  font-size: .78rem; white-space: nowrap;
}
.b-submission { background: #fdecea; color: #b3261e; }
.b-registration, .b-abstract { background: #e8f0fe; color: #1a56c4; }
.b-notification { background: #e6f4ea; color: #137333; }
.b-camera-ready { background: #f3e8fd; color: #7627bb; }
.b-conference { background: #eef1f4; color: #3c4043; }
.est-badge { background: #f9ab00; color: #5f3b00; }
.days { white-space: nowrap; font-variant-numeric: tabular-nums; }
.days.soon { color: #b3261e; font-weight: 600; }
footer { margin-top: 2rem; font-size: .8rem; color: #9ca3af; }
"""

JS = """
function daysUntil(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number);
  const target = new Date(y, m - 1, d);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return Math.round((target - today) / 86400000);
}
document.querySelectorAll('[data-date]').forEach(el => {
  const n = daysUntil(el.dataset.date);
  if (n > 0) { el.textContent = 'in ' + n + ' days'; if (n <= 14) el.classList.add('soon'); }
  else if (n === 0) { el.textContent = 'today!'; el.classList.add('soon'); }
  else el.textContent = (-n) + ' days ago';
});
"""


def gen_html(data):
    today = datetime.date.today()
    cards = []
    for conf in data["conferences"]:
        rows = []
        events = [e for e in collect_events(data) if e["conf"]["id"] == conf["id"]]
        for ev in sort_events(events):
            cls = f" {ev['status']}" if ev["status"] in ("passed",) else ""
            if ev["estimated"]:
                cls += " estimated"
            badge_cls = "b-" + ev["kind"]
            est = ' <span class="badge est-badge">EST.</span>' if ev["estimated"] else ""
            date_cell = html.escape(fmt_date(ev))
            days_cell = (
                f'<span class="days" data-date="{ev["date"]}"></span>'
                if ev["date_obj"] else "TBA"
            )
            rows.append(
                f'<tr class="{cls}"><td>{date_cell}</td>'
                f'<td>{html.escape(ev["label"])}{est}</td>'
                f'<td><span class="badge {badge_cls}">{KIND_LABEL.get(ev["kind"], ev["kind"])}</span></td>'
                f'<td>{days_cell}</td></tr>'
            )
        cd = conf["conference_dates"]
        dates_txt = f"conference {cd['start']} ~ {cd['end']}" if cd else "conference dates TBA"
        meta = (
            f'<div class="meta">{html.escape(conf["full_name"])} · {dates_txt} · '
            f'{html.escape(conf["location"])} · <a href="{html.escape(conf["source_url"])}">official CFP</a> · '
            f'verified {conf["verified_on"]}</div>'
        )
        cards.append(
            f'<div class="card"><h2>{html.escape(conf["short_name"])}</h2>{meta}'
            f'<table><tr><th>Date</th><th>Event</th><th>Kind</th><th>Countdown</th></tr>'
            f'{"".join(rows)}</table></div>'
        )
    body = "\n".join(cards)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Top-4 Security Conference Deadline Calendar</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<h1>🗓️ Top-4 Security Conference Deadline Calendar</h1>
<div class="sub">IEEE S&amp;P · ACM CCS · USENIX Security · NDSS ｜ data updated {data["updated_at"]} (generated {today:%Y-%m-%d})</div>
<div class="notes">
Dates are as stated by the official CFPs, timezone <b>AoE (UTC-12)</b> — in Singapore time (UTC+8) deadlines
effectively extend to 19:59 the next day. <b>Orange rows</b> = CFP not yet published, dates projected from past
cycles and must be verified. Strikethrough = passed.
</div>
{body}
<footer>Generated from deadlines.json by generate.py — edit the data file and re-run <code>python3 generate.py</code> to update.</footer>
</div>
<script>{JS}</script>
</body>
</html>
"""


def main():
    data = load()
    OUT.mkdir(exist_ok=True)
    (OUT / "security-deadlines.ics").write_text(gen_ics(data), encoding="utf-8")
    (OUT / "index.html").write_text(gen_html(data), encoding="utf-8")
    (OUT / "deadlines.md").write_text(gen_md(data), encoding="utf-8")
    n = sum(len(c["events"]) for c in data["conferences"])
    print(f"已生成 3 份产物（共 {n} 个事件）到 {OUT}/")


if __name__ == "__main__":
    main()
