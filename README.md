# gbhl-events

Map of GBHL events.

Run `gbhl_events.ipynb` from the repository root with the Google Sheets API key
in the ignored `api_key.txt` file. The notebook refreshes `years = [2026, 2027]`
by default. Change that list to refresh selected tabs; saving replaces only those
years and retains other years in both `data/gbhl_events.csv` and `data/events.json`.
Existing coordinates are reused by event name and start date before geocoding.

`calendar_parser.py` reads month blocks using their header positions and merged
widths, allowing the 2026 and 2027 layouts to differ. Whole tabs are requested so
added rows or columns are included. Notebook outputs are cleared for review.

Run regression checks with `python -m unittest -v test_calendar_parser` in an
environment with pandas installed.

Event formats use labels inside event cells (including 2026 Singles, Doubles,
and Teams labels). In 2027, event names containing "double" are marked Doubles,
case-insensitively. Events without a format label default to Singles.
