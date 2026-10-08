from datetime import UTC, datetime

from app.core.clock import ControllableClock, SystemClock


def test_system_clock():
    clock = SystemClock()
    now_utc = clock.now()
    assert now_utc.tzinfo == UTC
    assert clock.today() is not None


def test_controllable_clock():
    # 2026-06-15 23:00 UTC is 2026-06-16 07:00 Manila (UTC+8)
    dt = datetime(2026, 6, 15, 23, 0, 0, tzinfo=UTC)
    clock = ControllableClock(dt)

    assert clock.now() == dt
    # Business date in Asia/Manila should be 2026-06-16
    today_manila = clock.today()
    assert today_manila.year == 2026
    assert today_manila.month == 6
    assert today_manila.day == 16

    # Advance clock by 2 hours -> 2026-06-16 01:00 UTC
    clock.advance(hours=2)
    assert clock.now().hour == 1
