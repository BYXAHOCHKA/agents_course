from experiments.analysis import interval
from experiments.loops import has_loop, parse_action


def test_json_from_model():
    text = '{"tool":"schedule_search","args":{"date":"2026-10-19"}}'
    assert parse_action(text) == parse_action("```json\n" + text + "\n```")


def test_loop_definition():
    a, b = ["search", {"date": "2026-10-19"}], ["search", {"date": "2026-10-20"}]
    assert has_loop([a, a, a])
    assert has_loop([a, b, a, b])
    assert not has_loop([a, a, b])


def test_bootstrap_unit_is_query():
    scores = [0, 1, 1 / 3, 2 / 3] * 7 + [0, 1]
    low, high = interval(scores)
    assert 0 <= low < 0.5 < high <= 1
