import json
from collections import Counter


class LoopGuard:
    def __init__(self, repeats=3, window=6):
        self.repeats = repeats
        self.window = window
        self.calls = []
        self.observations = []

    def check(self, name, arguments, observation):
        self.calls.append(json.dumps([name, arguments], sort_keys=True))
        self.observations.append(json.dumps(observation, sort_keys=True, ensure_ascii=False))
        recent = self.calls[-self.window:]
        if Counter(recent)[recent[-1]] >= self.repeats:
            return "Повтор: смените инструмент или аргументы."
        if len(recent) >= 4 and recent[-4:-2] == recent[-2:]:
            return "Колебание между двумя действиями."
        observations = self.observations[-self.window:]
        if len(observations) == self.window and len(set(observations)) == 1:
            return "Нет прогресса: наблюдения не меняются."
        return None
