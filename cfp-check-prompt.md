You are maintaining the top-4 security conference deadline calendar in this directory (`deadlines.json` + `generate.py`).

## Task

1. Read `deadlines.json`.
2. For each conference, fetch its `source_url` with curl (only these URLs — never any other site).
3. Compare every event in the JSON against the official page. Look specifically for:
   - changed submission / registration / notification / camera-ready dates
   - newly published CFPs: if an `estimated: true` conference now has official dates, replace the projected dates, set `estimated` to `false`, set `estimated_from` to `null`, and fill `conference_dates` / `location` if now known
   - conference date or location changes
4. If anything changed: update `deadlines.json` accordingly, set `updated_at` and each changed conference's `verified_on` to today's date (YYYY-MM-DD), then re-run `python3 generate.py` and confirm all three files in `docs/` were regenerated.
5. If nothing changed: set `updated_at` to today and each conference's `verified_on` to today (these fields track when data was last checked). Either way (changed or not), re-run `python3 generate.py` at the end so the generated files carry the new check date and the timeline window rolls forward.
6. End your reply with a short report (max 5 lines): what changed, or "No changes".

## Constraints

- Work only inside this directory. Do not modify or read anything else on this machine.
- Only fetch the `source_url` values already present in `deadlines.json`.
- If a page cannot be fetched or parsed reliably, report it and leave that conference's data unchanged.
- Do not add new conferences or new event kinds.
