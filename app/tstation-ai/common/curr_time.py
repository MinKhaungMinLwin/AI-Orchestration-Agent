import os
from datetime import datetime, timedelta, timezone
from textwrap import dedent


def get_current_time() -> str:
    # Time
    tz_offset = int(os.getenv("TZ_OFFSET", "0"))
    tz = timezone(timedelta(hours=tz_offset))
    current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    weekday = datetime.now(tz).strftime("%A")
    tz_name = f"UTC{'+' if tz_offset >= 0 else ''}{tz_offset}"

    return f"Current Time: {weekday} - {current_time}, Timezone: {tz_name}"
