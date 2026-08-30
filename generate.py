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


# ---------- Timeline chart ----------

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# 固定颜色槽位：颜色跟随会议身份，与 JSON 顺序无关
CONF_SLOTS = {"sp-": 1, "ccs-": 2, "usenixsec-": 3, "ndss-": 4}


def month_add(d, n):
    m = d.month - 1 + n
    return d.replace(year=d.year + m // 12, month=m % 12 + 1, day=1)


def gen_timeline(data):
    """未来 12 个月（下月 1 日起）的投稿截止时间轴：横轴月份，纵轴会议。"""
    today = datetime.date.today()
    start = month_add(today.replace(day=1), 1)
    end = month_add(start, 12) - datetime.timedelta(days=1)
    window = (end - start).days

    rows = []  # (conf, events)
    for conf in data["conferences"]:
        evs = [ev for ev in conf["events"]
               if ev["kind"] == "submission" and parse_date(ev["date"])
               and start <= parse_date(ev["date"]) <= end]
        if evs:
            rows.append((conf, sorted(evs, key=lambda e: parse_date(e["date"]))))
    if not rows:
        return ""
    rows.sort(key=lambda r: CONF_SLOTS.get(r[0]["id"].split("-")[0] + "-", 9))

    M_LEFT, M_RIGHT, M_TOP, M_BOTTOM = 150, 24, 46, 32
    ROW_H, W = 56, 960
    plot_w = W - M_LEFT - M_RIGHT
    plot_h = ROW_H * len(rows)
    H = M_TOP + plot_h + M_BOTTOM

    def xpos(d):
        return M_LEFT + (d - start).days / window * plot_w

    # 月份网格线 + 刻度
    ticks = []
    b = start
    boundaries = []
    while b <= end:
        boundaries.append(b)
        b = month_add(b, 1)
    boundaries.append(b)
    for i, bd in enumerate(boundaries):
        x = xpos(bd) if bd <= end else M_LEFT + plot_w
        label = MONTHS[bd.month - 1]
        if i == 0 or bd.month == 1:
            label += " " + str(bd.year)
        anchor = "middle"
        if i == 0:
            anchor = "start"
        elif i == len(boundaries) - 1:
            anchor = "end"
        ticks.append(
            f'<line x1="{x:.1f}" y1="{M_TOP}" x2="{x:.1f}" y2="{M_TOP + plot_h}" '
            f'stroke="var(--gridline)" stroke-width="1"/>'
            f'<text x="{x:.1f}" y="{H - 12}" class="tl-tick" text-anchor="{anchor}">{label}</text>'
        )

    # 今天参考线
    today_line = ""
    if start <= today <= end:
        tx = xpos(today)
        today_line = (
            f'<line x1="{tx:.1f}" y1="{M_TOP}" x2="{tx:.1f}" y2="{M_TOP + plot_h}" '
            f'stroke="var(--ink-muted)" stroke-width="1"/>'
            f'<text x="{tx:.1f}" y="{M_TOP - 8}" class="tl-today" text-anchor="middle">Today</text>'
        )

    # 图例
    legend = ""
    lx = M_LEFT
    for conf, _ in rows:
        slot = CONF_SLOTS[conf["id"].split("-")[0] + "-"]
        name = conf["short_name"]
        legend += (
            f'<circle cx="{lx + 4:.1f}" cy="20" r="4" fill="var(--series-{slot})"/>'
            f'<text x="{lx + 14:.1f}" y="24" class="tl-legend">{name}</text>'
        )
        lx += 14 + len(name) * 6.9 + 28
    legend += (
        f'<circle cx="{lx + 4:.1f}" cy="20" r="4" fill="var(--viz-surface)" '
        f'stroke="var(--ink-muted)" stroke-width="1.5"/>'
        f'<text x="{lx + 14:.1f}" y="24" class="tl-legend">projected</text>'
    )

    # 行 + 圆点 + 日期标签
    parts = []
    parts.append(today_line)
    for i, (conf, evs) in enumerate(rows):
        slot = CONF_SLOTS[conf["id"].split("-")[0] + "-"]
        yc = M_TOP + i * ROW_H + ROW_H / 2
        if i > 0:
            parts.append(
                f'<line x1="{M_LEFT}" y1="{M_TOP + i * ROW_H:.1f}" x2="{W - M_RIGHT}" '
                f'y2="{M_TOP + i * ROW_H:.1f}" stroke="var(--gridline)" stroke-width="1"/>'
            )
        parts.append(
            f'<text x="{M_LEFT - 6}" y="{yc + 4:.1f}" class="tl-row" '
            f'text-anchor="end">{conf["short_name"]}</text>'
        )
        prev_label_x = None
        for ev in evs:
            d = parse_date(ev["date"])
            x = xpos(d)
            note = (f"AoE (UTC-12) · projected from {ev['estimated_from']} — verify"
                    if ev["estimated"] else "AoE (UTC-12)")
            tip_date = f"{d:%Y-%m-%d}"
            aria = f"{conf['short_name']}: {ev['label']} {tip_date}"
            group = (
                f'<g class="tl-group">'
                f'<circle class="tl-hit" cx="{x:.1f}" cy="{yc:.1f}" r="12" fill="transparent" '
                f'tabindex="0" role="img" aria-label="{aria}" data-title="{conf["short_name"]}" '
                f'data-event="{ev["label"]}" data-date="{tip_date}" data-note="{note}"/>'
                f'<circle cx="{x:.1f}" cy="{yc:.1f}" r="7" fill="var(--viz-surface)"/>'
            )
            if ev["estimated"]:
                group += (
                    f'<circle class="tl-dot" cx="{x:.1f}" cy="{yc:.1f}" r="5" '
                    f'fill="var(--viz-surface)" stroke="var(--series-{slot})" stroke-width="2"/>'
                )
            else:
                group += (
                    f'<circle class="tl-dot" cx="{x:.1f}" cy="{yc:.1f}" r="5" '
                    f'fill="var(--series-{slot})"/>'
                )
            group += "</g>"
            parts.append(group)

            # 日期标签：与同排上一个标签过近则翻到圆点上方；两端夹紧不出界
            label_clamped = min(max(x, M_LEFT + 44), W - M_RIGHT - 44)
            above = prev_label_x is not None and label_clamped - prev_label_x < 100
            ly = yc - 16 if above else yc + 24
            label = (
                f'<text x="{label_clamped:.1f}" y="{ly:.1f}" class="tl-date" '
                f'text-anchor="middle">{MONTHS[d.month - 1]} {d.day}'
            )
            if ev["estimated"]:
                label += f'<tspan class="tl-est"> est.</tspan>'
            label += "</text>"
            parts.append(label)
            prev_label_x = label_clamped

    svg = (
        f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Paper submission deadlines '
        f'for the top-4 security conferences, {start:%b %Y} to {end:%b %Y}">'
        f'<g>{legend}</g>'
        f'<line x1="{M_LEFT}" y1="{M_TOP + plot_h:.1f}" x2="{W - M_RIGHT}" '
        f'y2="{M_TOP + plot_h:.1f}" stroke="var(--baseline)" stroke-width="1"/>'
        + "".join(ticks) + "".join(parts) +
        "</svg>"
    )
    caption = (
        f'<p class="tl-caption">Paper submission deadlines, {MONTHS[start.month - 1]} {start.year} '
        f'– {MONTHS[end.month - 1]} {end.year}. Hollow dots = projected (CFP not yet published). '
        f'Registration dates and notifications are listed below.</p>'
    )
    return f'<div class="viz-root tl-wrap">{svg}{caption}</div>'


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
/* Timeline chart (data-viz slots per the validated reference palette) */
.viz-root {
  color-scheme: light;
  --viz-surface: #fcfcfb;
  --ink-primary: #0b0b0b;
  --ink-secondary: #52514e;
  --ink-muted: #898781;
  --gridline: #e1e0d9;
  --baseline: #c3c2b7;
  --series-1: #2a78d6;
  --series-2: #008300;
  --series-3: #e87ba4;
  --series-4: #eda100;
}
@media (prefers-color-scheme: dark) {
  .viz-root {
    color-scheme: dark;
    --viz-surface: #1a1a19;
    --ink-primary: #ffffff;
    --ink-secondary: #c3c2b7;
    --ink-muted: #898781;
    --gridline: #2c2c2a;
    --baseline: #383835;
    --series-1: #3987e5;
    --series-2: #008300;
    --series-3: #d55181;
    --series-4: #c98500;
  }
}
.tl-wrap {
  background: var(--viz-surface);
  border: 1px solid var(--gridline);
  border-radius: 10px;
  padding: .8rem .8rem .4rem;
  margin-bottom: 1.2rem;
}
.tl-wrap svg { display: block; width: 100%; height: auto; }
.tl-row, .tl-date, .tl-legend, .tl-tick, .tl-today, .tl-caption { font-family: inherit; }
.tl-row { font-size: 13px; font-weight: 500; fill: var(--ink-primary); }
.tl-date { font-size: 11.5px; fill: var(--ink-secondary); }
.tl-est { fill: var(--ink-muted); }
.tl-legend { font-size: 12px; fill: var(--ink-secondary); }
.tl-tick { font-size: 11px; fill: var(--ink-muted); }
.tl-today { font-size: 10px; fill: var(--ink-muted); }
.tl-hit { cursor: pointer; }
.tl-group:hover .tl-dot, .tl-group:focus-within .tl-dot { filter: brightness(1.18); }
.tl-caption { font-size: .8rem; color: var(--ink-muted); margin: .5rem 0 .3rem; }
.tl-tip {
  position: fixed; z-index: 10; pointer-events: none; display: none;
  background: var(--viz-surface); color: var(--ink-primary);
  border: 1px solid var(--baseline); border-radius: 6px;
  padding: .45rem .65rem; font-size: 12px; line-height: 1.45; max-width: 280px;
  box-shadow: 0 2px 8px rgba(0,0,0,.12);
}
.tl-tip.show { display: block; }
.tl-tip strong { font-variant-numeric: tabular-nums; }
.tl-tip .tl-tip-note { color: var(--ink-muted); }
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

// Timeline tooltip (values first, labels follow; textContent only)
(function () {
  const tip = document.createElement('div');
  tip.className = 'tl-tip';
  tip.setAttribute('role', 'tooltip');
  document.body.appendChild(tip);

  function fill(hit) {
    tip.replaceChildren();
    const strong = document.createElement('strong');
    strong.textContent = hit.dataset.date;
    const row = document.createElement('div');
    row.textContent = hit.dataset.title + ' — ' + hit.dataset.event;
    const note = document.createElement('div');
    note.className = 'tl-tip-note';
    note.textContent = hit.dataset.note;
    tip.append(strong, row, note);
  }
  function place(x, y) {
    tip.classList.add('show');
    const pad = 10;
    let left = x + 14, top = y + 14;
    if (left + tip.offsetWidth > window.innerWidth - pad) left = x - tip.offsetWidth - 14;
    if (top + tip.offsetHeight > window.innerHeight - pad) top = y - tip.offsetHeight - 14;
    tip.style.left = Math.max(pad, left) + 'px';
    tip.style.top = Math.max(pad, top) + 'px';
  }
  document.querySelectorAll('.tl-hit').forEach(hit => {
    hit.addEventListener('pointerenter', () => fill(hit));
    hit.addEventListener('pointermove', e => place(e.clientX, e.clientY));
    hit.addEventListener('pointerleave', () => tip.classList.remove('show'));
    hit.addEventListener('focus', () => {
      fill(hit);
      const r = hit.getBoundingClientRect();
      place(r.right, r.top);
    });
    hit.addEventListener('blur', () => tip.classList.remove('show'));
  });
})();
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
    timeline = gen_timeline(data)
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
{timeline}
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
