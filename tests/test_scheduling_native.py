import datetime as dt

import pytest

from omnix.scheduling import parse_schedule


def test_cron_next_occurrence_is_in_utc_and_matches_schedule():
    kind, timestamp, interval = parse_schedule("*/15 * * * *")
    result = dt.datetime.fromtimestamp(timestamp, dt.timezone.utc)
    assert kind == "cron" and interval is None
    assert result.minute % 15 == 0 and result.second == 0
    assert result > dt.datetime.now(dt.timezone.utc)


@pytest.mark.parametrize("value", ["*/0 * * * *", "61 * * * *", "0 25 * * *"])
def test_invalid_cron_is_rejected(value):
    with pytest.raises(ValueError):
        parse_schedule(value)
