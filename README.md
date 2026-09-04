# Top-4 Security Conference Deadline Calendar

Deadline tracking for the top-4 security conferences — **IEEE S&P / ACM CCS / USENIX Security / NDSS**. One JSON data source, one Python script, three generated artifacts.

Tracked dates: **abstract / mandatory registration**, **paper deadline**, **notification**, and **conference dates**. Camera-ready / final-paper deadlines are intentionally not tracked.

| Artifact | Path | Purpose |
|---|---|---|
| ICS | `docs/security-deadlines.ics` | Import into Google/Apple Calendar; reminders 7 + 1 days before deadlines |
| HTML | `docs/index.html` | Browser view with a 12-month submission-deadline timeline at the top and live countdowns — published at <https://menghao303.github.io/security-deadlines/> |
| Markdown | `docs/deadlines.md` | Quick-reference table in the repo |

## Importing the calendar

- **Apple Calendar**: double-click `security-deadlines.ics` (or `open docs/security-deadlines.ics`) and choose a calendar.
- **Google Calendar**: Settings → Import & export → Import the ICS file. A dedicated "Deadlines" calendar is recommended so reminders can be toggled as a group.
- Events are all-day, e.g. `S&P 2027 Cycle 2 paper deadline`. Reminders (VALARM): 7 + 1 days for registration/submission and conferences, 1 day for notifications.

## Timezone note

All dates are as stated by the official CFPs, in **AoE (UTC-12)**:
- In Singapore time (UTC+8), a deadline effectively extends to **19:59 the next day** — e.g. 2026-11-17 AoE ≈ by 19:59 on 2026-11-18 SGT.
- Calendar entries are placed on the official (AoE) date; plan for the extra half-day when submitting from Asia.

## Current data (verified 2026-08-30)

- **IEEE S&P 2027** (May 17–19, Montreal): Cycle 2 abstract 11/10, paper deadline 11/17, notification 3/5
- **USENIX Security 2027** (Aug 11–13, Denver): Cycle 2 registration 1/19, paper deadline 1/26, notification 5/6
- **NDSS 2027** (Mar 22–26, Seoul): Fall cycle notification 11/4
- **CCS 2026** (Nov 15–19, The Hague): conference dates only
- **CCS 2027 / NDSS 2028**: CFPs not yet published — dates are **projections** from past cycles (`estimated: true`, shown in orange with an "EST." badge)

## Updating the data

```bash
python3 generate.py    # stdlib only, no dependencies
```

## TODO (replace projections once CFPs are published)

- [ ] **CCS 2027**: replace the 4 projected events in `ccs-2027` with official dates once the CFP is out; add conference dates (Atlanta, October 2027)
- [ ] **NDSS 2028**: replace the 4 projected events in `ndss-2028`; add conference dates and location
- Every conference record carries its official `source_url` and `verified_on` for auditing.

## Automated weekly CFP check (launchd)

A weekly job verifies the official CFP pages against `deadlines.json`, updates anything that changed, regenerates the artifacts, and — only if the check succeeded — commits and pushes the changes so the public site stays current:

- `cfp-check.sh` — wrapper that runs Claude Code headless with the fixed prompt in `cfp-check-prompt.md`, then commits/pushes if the check succeeded and files changed
- `com.menghao.security-deadlines-cfpcheck.plist` — launchd agent, runs every Monday at 09:07 local time
- Logs to `cfp-check.log`

Note: the job runs as the account you are logged into with `claude` (credentials live in the macOS Keychain). The wrapper unsets any inherited `ANTHROPIC_*` gateway variables so it always talks to the default endpoint — no tokens are needed in or next to the repo.

Install / inspect:

```bash
cp com.menghao.security-deadlines-cfpcheck.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.menghao.security-deadlines-cfpcheck.plist
launchctl list | grep cfpcheck          # status
launchctl kickstart gui/$(id -u)/com.menghao.security-deadlines-cfpcheck   # run now
```

The prompt restricts the agent to this directory and to the official CFP URLs listed in `deadlines.json`; `estimated: true` entries are its priority checklist — replace them as soon as a CFP appears.

## Data schema (`deadlines.json`)

```jsonc
{
  "updated_at": "last data update",
  "conferences": [{
    "id": "unique id, e.g. sp-2027",
    "short_name": "short name used in calendar summaries",
    "full_name": "full conference name",
    "conference_dates": { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" } | null,
    "location": "venue",
    "source_url": "official CFP page",
    "verified_on": "date the data was checked against the source",
    "events": [{
      "kind": "abstract | registration | submission | notification | conference",
      "label": "event name",
      "date": "YYYY-MM-DD | null (TBA)",
      "date_end": "end date for conference events | null",
      "tz_note": "timezone note, e.g. AoE | null",
      "estimated": "true = projection; shown with EST. badge",
      "estimated_from": "past cycle the projection is based on | null"
    }]
  }]
}
```
