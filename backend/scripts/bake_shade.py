"""Precompute shade for the demo afternoons and ship it with the data.

Writes data/processed/shade/sun_<date>_<time>_<version>.bits.npy (packed bits), so the
demo trip and its leave-later timeline are fast even on a fresh server.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from heatsafe.config import LOCAL_TZ, SLOT_MINUTES, get_settings
from heatsafe.data_store import get_store
from heatsafe.shade import cache_name, sample_sun_mask

EXTRA_DAYS = [date(2026, 9, 9)]  # the hottest afternoon, kept for the "no safe route" story
FIRST, LAST = time(15, 0), time(20, 0)


def main() -> None:
    settings = get_settings()
    store = get_store()
    out = settings.data_dir / "processed" / "shade"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("sun_*.bits.npy"):
        if store.version not in old.name:
            old.unlink()
    days = sorted({*EXTRA_DAYS, *([settings.demo_date] if settings.demo_date else [])})
    tz = ZoneInfo(LOCAL_TZ)
    for day in days:
        slot = datetime.combine(day, FIRST, tz)
        while slot.time() <= LAST:
            target = out / f"{cache_name(store, slot)}.bits.npy"
            if not target.exists():
                np.save(target, np.packbits(sample_sun_mask(store, slot)))
            slot += timedelta(minutes=SLOT_MINUTES)
        print(f"{day}: done")
    total = sum(f.stat().st_size for f in out.glob("*.bits.npy")) / 1e6
    print(f"{len(list(out.glob('*.bits.npy')))} files, {total:.1f} MB")


if __name__ == "__main__":
    main()
