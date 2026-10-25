import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from calendar_parser import parse_calendar


def calendar_fixture(width, offset=0):
    rows = []
    merges = []
    for month in ("January", "April", "July", "October"):
        row = len(rows)
        values = [{} for _ in range(offset + width)]
        values[offset] = {"formattedValue": month}
        rows.append({"values": values})
        merges.append(dict(startRowIndex=row, endRowIndex=row + 1,
                           startColumnIndex=offset, endColumnIndex=offset + width))
        values = [{} for _ in range(offset + width)]
        values[-1] = {"formattedValue": "2"}
        rows.append({"values": values})
        values = [{} for _ in range(offset + width)]
        values[-1] = {"formattedValue": "Test event\nOrganizer\n[SE - Town - Hall]"}
        rows.append({"values": values})
        rows.append({})
    return {"sheets": [{"data": [{"rowData": rows}], "merges": merges}]}


class CalendarTests(unittest.TestCase):
    def test_different_header_widths_and_offsets(self):
        for year, width, offset in ((2026, 8, 1), (2027, 7, 0)):
            with self.subTest(year=year):
                events = parse_calendar(calendar_fixture(width, offset), year)
                self.assertEqual([e["start_date"] for e in events],
                                 [f"{year}-{month:02}-02" for month in (1, 4, 7, 10)])
                self.assertTrue(all(e["location"] == "Town - Hall" for e in events))

    def test_event_formats(self):
        cases = [
            (2026, 'An Event', 'DOUBLES', None, 'Doubles'),
            (2026, 'An Event', ' singles ', None, 'Singles'),
            (2026, 'An Event', 'TEAMS', None, 'Team'),
            (2026, 'An Event', 'DOUBLES', 'Singles', 'Doubles'),
            (2026, 'An Event', '', 'Doubles', 'Doubles'),
            (2027, 'Bristol Doubles', '', None, 'Doubles'),
            (2027, 'DOUBLE Trouble', '', None, 'Doubles'),
            (2027, 'Bristol Doubles', 'Singles', None, 'Doubles'),
            (2027, 'An Event', '', None, 'Singles'),
            (2027, 'An Event', '', 'Doubles Cup\nOther Organizer\n[SE - Town]', 'Singles'),
        ]
        for year, name, label, below, expected in cases:
            with self.subTest(year=year, name=name, label=label, below=below):
                result = calendar_fixture(7)
                rows = result['sheets'][0]['data'][0]['rowData']
                rows[2]['values'][-1]['formattedValue'] = (
                    f'{name}\nOrganizer\n[SE - Town]\n{label}')
                if below is not None:
                    rows[3] = {'values': [{}] * 6 + [{'formattedValue': below}]}
                self.assertEqual(parse_calendar(result, year)[0]['format'], expected)

    def test_saved_years_survive_refresh_and_repeat_save(self):
        notebook = json.loads(Path(__file__).with_name("gbhl_events.ipynb").read_text(encoding="utf-8"))
        save_code = "".join(notebook["cells"][15]["source"])
        for years in ([2026], [2027], [2026, 2027]):
            with self.subTest(years=years), tempfile.TemporaryDirectory() as directory:
                old = pd.DataFrame([dict(start_date=f"{year}-01-01", event_name="old")
                                    for year in (2025, 2026, 2027)])
                refreshed = pd.DataFrame([dict(start_date=f"{year}-02-01", event_name="new")
                                          for year in years])
                path = Path(directory) / "events.csv"
                scope = dict(pd=pd, old_df=old, df=refreshed, years=years, output_path=path)
                for _ in range(2):
                    exec(save_code, scope)
                    saved = pd.read_csv(path)
                    self.assertEqual(len(saved), 3)
                    self.assertEqual(set(saved.start_date.str[:4]), {"2025", "2026", "2027"})
                    for year in years:
                        self.assertEqual(saved.loc[saved.start_date.str.startswith(str(year)),
                                                   "event_name"].tolist(), ["new"])
                    scope["old_df"] = saved


if __name__ == "__main__":
    unittest.main()
