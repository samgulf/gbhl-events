import calendar
import re
import unicodedata
from datetime import datetime


def parse_calendar(result, year):
    """Extract events from a complete Sheets calendar tab, independent of block spacing."""
    grid = result['sheets'][0]['data'][0].get('rowData', [])
    # Step 1: Find all month labels (like 'JANUARY', 'FEBRUARY', etc.)
    month_positions = {}  # (row_idx, col_idx) => month_num
    month_names = {name.upper(): i for i, name in enumerate(calendar.month_name) if name}

    for row_idx, row in enumerate(grid):
        for col_idx, cell in enumerate(row.get('values', [])):
            val = cell.get('formattedValue', '')
            val_clean = val.strip().upper()
            if val_clean in month_names:
                month_num = month_names[val_clean]
                month_positions[(row_idx, col_idx)] = month_num

    # Month headers span different numbers of columns in different years.
    month_ends = {}
    for (r, c) in month_positions:
        header_merge = next((m for m in result['sheets'][0].get('merges', [])
                             if m['startRowIndex'] == r and m['startColumnIndex'] == c), None)
        next_header = min((c2 for r2, c2 in month_positions if r2 == r and c2 > c),
                          default=max((len(row.get('values', [])) for row in grid), default=0))
        month_ends[(r, c)] = header_merge['endColumnIndex'] if header_merge else next_header

    # Associate day cells with the month block directly above them.
    date_map = {}  # (row_idx, col_idx) -> datetime

    for row_idx, row in enumerate(grid):
        for col_idx, cell in enumerate(row.get('values', [])):
            val = cell.get('formattedValue', '')
            if not val.isdigit():
                continue
            day = int(val)

            # Use the most recent header row, then its rightmost month to the left.
            # Vertical boundaries take precedence over horizontal distance.
            headers_above = [(r, c, month) for (r, c), month in month_positions.items()
                             if r < row_idx]
            best_month = None
            if headers_above:
                header_row = max(r for r, c, month in headers_above)
                candidates = [(c, month) for r, c, month in headers_above
                              if r == header_row and c <= col_idx < month_ends[(r, c)]]
                if candidates:
                    best_month = max(candidates)[1]

            if best_month is not None:
                try:
                    date_map[(row_idx, col_idx)] = datetime(year, best_month, day)
                except ValueError:
                    pass  # Ignore invalid day numbers.
    events = []
    merged_ranges = result['sheets'][0].get('merges', [])
    visited = set()

    # Helper to find merged range for a given cell
    def get_merged_range(row, col):
        for mr in merged_ranges:
            if (
                mr['startRowIndex'] <= row < mr['endRowIndex']
                and mr['startColumnIndex'] <= col < mr['endColumnIndex']
            ):
                return mr
        return None

    for row_idx, row in enumerate(grid):
        for col_idx, cell in enumerate(row.get('values', [])):
            if (row_idx, col_idx) in visited:
                continue

            val = cell.get('formattedValue')
            if not val or val.strip().isdigit():
                continue
            link = cell.get('hyperlink', '')

            # === Get event start date and event type color from the date cell above ===
            event_date = None
            event_type = 'Other'

            for r2 in range(row_idx - 1, -1, -1):
                if (r2, col_idx) in date_map:
                    event_date = date_map[(r2, col_idx)]

                    # Try to read the background color from the date cell
                    try:
                        date_cell = grid[r2]['values'][col_idx]  # <-- correct path
                        color = date_cell.get('effectiveFormat', {}).get('backgroundColor', {})
                        r = color.get('red', 0)
                        g = color.get('green', 0)
                        b = color.get('blue', 0)

                        if r > 0.8 and g < 0.5:
                            event_type = 'GBHL100'
                        elif r > 0.8 and g > 0.8:
                            event_type = 'GBHL90'
                        elif b > 0.8:
                            event_type = 'GBHL80'
                        else:
                            event_type = 'Other'
                    except Exception as e:
                        print(f"Warning: Failed to read event type color from ({r2},{col_idx}): {e}")

                    break

            if not event_date:
                continue

            # Parse event text
            lines = val.strip().split('\n')
            if len(lines) < 3:
                continue

            event_name = lines[0].strip()
            organizer = lines[1].strip()
            region_loc = lines[2].strip().strip('[]')
            region, location = region_loc.split(' - ', 1) if ' - ' in region_loc else ('Unknown', region_loc)

            # Determine merged range (if any)
            merged = get_merged_range(row_idx, col_idx)
            if merged:
                end_col = merged['endColumnIndex'] - 1
                # Mark all merged cells as visited
                for r in range(merged['startRowIndex'], merged['endRowIndex']):
                    for c in range(merged['startColumnIndex'], merged['endColumnIndex']):
                        visited.add((r, c))
            else:
                end_col = col_idx
                visited.add((row_idx, col_idx))

            # Get end date from the right-most merged cell's column
            end_date = event_date
            for r2 in range(row_idx - 1, -1, -1):
                if (r2, end_col) in date_map:
                    end_date = date_map[(r2, end_col)]
                    break

            # 2026 stores the format after the location inside the event cell.
            labels = {'single': 'Singles', 'singles': 'Singles',
                      'double': 'Doubles', 'doubles': 'Doubles',
                      'team': 'Team', 'teams': 'Team'}
            format_type = next((labels[line.strip().lower()] for line in lines[3:]
                                if line.strip().lower() in labels), None)

            # Retain support for a separate format cell, but only accept a label:
            # another event's name below must not determine this event's format.
            format_row_idx = merged['endRowIndex'] if merged else row_idx + 1
            format_col_idx = merged['startColumnIndex'] if merged else col_idx
            if format_type is None and format_row_idx < len(grid):
                format_cells = grid[format_row_idx].get('values', [])
                if format_col_idx < len(format_cells):
                    label = format_cells[format_col_idx].get('formattedValue', '').strip().lower()
                    format_type = labels.get(label)

            format_type = format_type or 'Singles'
            # The 2027 tab has no consistent format labels; use its event names.
            if year == 2027 and 'double' in event_name.lower():
                format_type = 'Doubles'

            event = {
                'start_date': event_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
                'event_name': event_name,
                'organizer': organizer,
                'region': region,
                'location': location,
                'format': format_type,
                'event_type': event_type,
                'link': link
            }

            events.append(event)

    return events


def _normalise_event_name(name):
    name = unicodedata.normalize('NFKD', str(name)).casefold()
    name = re.sub(r"\b20\d{2}\b", '', name)
    return ' '.join(re.findall(r"[^\W_]+", name, flags=re.UNICODE))


# Explicit recurring-title variants; the organiser must also match.
_DOUBLES_NAME_VARIANTS = {
    'i will carry him again': 'i will carry him if i must',
}


def inherit_doubles_formats(events, historical_events=()):
    """Mark recurring 2027 events from 2026 doubles, returning copied records."""
    events = [dict(event) for event in events]
    # Freshly parsed records take precedence over saved versions of the same event.
    history = {(event['event_name'], event['start_date']): event
               for event in [*historical_events, *events]}

    def identity(event):
        name = _normalise_event_name(event['event_name'])
        name = _DOUBLES_NAME_VARIANTS.get(name, name)
        organiser = ' '.join(str(event.get('organizer', '')).casefold().split())
        return name, organiser

    doubles = {identity(event) for event in history.values()
               if str(event['start_date']).startswith('2026-')
               and event.get('format') == 'Doubles' and identity(event)[1]}
    for event in events:
        if str(event['start_date']).startswith('2027-') and identity(event) in doubles:
            event['format'] = 'Doubles'
    return events
