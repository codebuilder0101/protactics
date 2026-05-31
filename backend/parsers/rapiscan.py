"""Parser Formato B — Rapiscan Legacy (Cargo Inspection Report)"""
from datetime import datetime, timezone, timedelta


def _excel_serial_to_date(serial: float) -> datetime | None:
    try:
        dt = datetime(1899, 12, 30, tzinfo=timezone.utc) + timedelta(days=float(serial))
        return dt
    except Exception:
        return None


def _parse_date_cell(raw, filter_month: int | None) -> tuple[int | None, int | None, int | None]:
    """Returns (year, month, day) or (None, None, None)"""
    if raw is None:
        return None, None, None

    if isinstance(raw, (int, float)):
        dt = _excel_serial_to_date(raw)
        if not dt:
            return None, None, None
        yr, mon, day = dt.year, dt.month, dt.day
    else:
        s = str(raw).strip()
        if not s or s.lower() in ("total", "date", "nan"):
            return None, None, None
        # Try ISO: 2026-01-05...
        try:
            dt = datetime.fromisoformat(s[:10])
            yr, mon, day = dt.year, dt.month, dt.day
        except Exception:
            # Try M/D/YYYY
            import re
            m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
            if m:
                mon, day, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                return None, None, None

    # Fix Excel day/month inversion (e.g. 2026-01-05 should be 2026-05-01)
    if filter_month and mon != filter_month and day == filter_month:
        mon, day = day, mon

    return yr, mon, day


def parse(rows: list, port_name: str, month_name: str,
          filter_year: int, filter_month: int) -> dict:

    # Find header row index ("Scan Date & Time")
    header_idx = -1
    for i, row in enumerate(rows):
        vals = list(row) if isinstance(row, (list, tuple)) else list(row.values())
        if any("Scan Date" in str(v) for v in vals):
            header_idx = i
            break

    daily, hourly = {}, {}
    total_from_summary = 0

    # --- Step 1: summary rows (above detail header) ---
    summary_end = header_idx if header_idx != -1 else len(rows)
    for i in range(summary_end):
        row = rows[i]
        vals = list(row) if isinstance(row, (list, tuple)) else list(row.values())
        if len(vals) < 2:
            continue
        raw_date, raw_total = vals[0], vals[1]
        try:
            tot = int(float(str(raw_total).replace(",", "")))
        except Exception:
            continue
        if tot <= 0:
            continue
        if str(raw_date).lower() in ("total", "date", "nan", "non suspect", "suspect", ""):
            continue

        yr, mon, day = _parse_date_cell(raw_date, filter_month)
        if not day:
            continue
        if filter_year and yr != filter_year:
            continue
        if filter_month and mon != filter_month:
            continue

        daily[day] = daily.get(day, 0) + tot
        total_from_summary += tot

    # --- Step 2: detail rows for hourly distribution ---
    if header_idx != -1:
        header_row = rows[header_idx]
        header_vals = list(header_row) if isinstance(header_row, (list, tuple)) else list(header_row.values())
        date_col = next((i for i, v in enumerate(header_vals) if "Scan Date" in str(v)), None)

        if date_col is not None:
            for row in rows[header_idx + 1:]:
                vals = list(row) if isinstance(row, (list, tuple)) else list(row.values())
                if len(vals) <= date_col:
                    continue
                raw = vals[date_col]
                if not raw:
                    continue
                try:
                    if isinstance(raw, (int, float)):
                        dt = _excel_serial_to_date(raw)
                    else:
                        dt = datetime.fromisoformat(str(raw)[:19])
                    if not dt:
                        continue
                    if filter_year and dt.year != filter_year:
                        continue
                    if filter_month and dt.month != filter_month:
                        continue
                    h = dt.hour
                    hourly[h] = hourly.get(h, 0) + 1
                except Exception:
                    continue

    total = total_from_summary or sum(daily.values())
    days  = len(daily)
    peak  = max(daily.values(), default=0)
    avg   = round(total / days) if days else 0

    return dict(port_name=port_name, month_name=month_name, total_scans=total,
                days_active=days, peak_day=peak, avg_daily=avg,
                daily=daily, hourly=hourly, operators={"Operador": total},
                format="rapiscan")
