from experiments.guard import LoopGuard


def test_repeated_call():
    guard = LoopGuard()
    assert not guard.check("search", {"date": "2026-10-12"}, [])
    assert not guard.check("search", {"date": "2026-10-12"}, [])
    assert guard.check("search", {"date": "2026-10-12"}, []).startswith("Повтор")


def test_alternating_calls():
    guard = LoopGuard()
    assert not guard.check("search", {"date": "2026-10-12"}, [])
    assert not guard.check("search", {"date": "2026-10-13"}, [])
    assert not guard.check("search", {"date": "2026-10-12"}, [])
    assert guard.check("search", {"date": "2026-10-13"}, []).startswith("Колебание")


def test_different_calls():
    guard = LoopGuard()
    for day in range(12, 20):
        assert not guard.check("search", {"date": f"2026-10-{day}"}, [day])


def test_repeat_inside_window():
    guard = LoopGuard()
    for day in [12, 13, 12, 14]:
        assert not guard.check("search", {"date": day}, [day])
    assert guard.check("search", {"date": 12}, [12]).startswith("Повтор")


def test_no_progress():
    guard = LoopGuard()
    for day in range(5):
        assert not guard.check("search", {"date": day}, [])
    assert guard.check("search", {"date": 5}, []).startswith("Нет прогресса")
