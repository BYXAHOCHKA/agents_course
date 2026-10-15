import asyncio
import json
import random
from pathlib import Path

from experiments.guard import LoopGuard
from experiments.model import Model
from server import server


MAX_STEPS = 8
SYSTEM = (
    "Ты ищешь занятие в журнале расписания. Выбирай следующее действие по результатам предыдущих. "
    "Возвращай только один JSON-объект, без пояснений. "
    'Поиск: {"tool":"schedule_search","args":{"handle":"main","date":"YYYY-MM-DD",'
    '"group":"A","query":"название занятия","response_format":"concise"}}. '
    'Завершение: {"tool":"finish","args":{"entry_id":ID}}. '
    "Заменяй ID на число из полученного результата. Не придумывай id. "
    "Разрешены только две даты из задачи."
)


def parse_action(text):
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = "\n".join(text.splitlines()[1:-1]).strip()
    return json.loads(text)


def has_loop(calls):
    keys = [json.dumps(call, sort_keys=True) for call in calls]
    for i in range(len(keys)):
        if i >= 2 and keys[i] == keys[i - 1] == keys[i - 2]:
            return True
        if i >= 3 and keys[i - 3] == keys[i - 1] and keys[i - 2] == keys[i] and keys[i] != keys[i - 1]:
            return True
    return False


async def episode(model, task, repeat, condition):
    seed = 1000 + int(task["id"][1:]) * 3 + repeat
    rng = random.Random(seed)
    guard = LoopGuard(repeats=3, window=6)
    signals = 0
    observed_ids = set()
    calls = []
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task["text"]}]
    row = {"task_id": task["id"], "repeat": repeat, "condition": condition, "seed": seed,
           "model": model.name, "parser": "json_or_markdown", "task": task, "trace": [], "steps": 0, "tokens": 0,
           "usage_complete": True, "loop": False, "success": False, "status": "step_limit"}
    for step in range(MAX_STEPS):
        event = {"step": step + 1, "messages": [m.copy() for m in messages]}
        row["steps"] += 1
        try:
            response = model.call(messages, seed + step)
            event["response"] = response
            row["tokens"] += response["input_tokens"] + response["output_tokens"]
        except Exception as error:
            event["error"] = type(error).__name__
            row["usage_complete"] = False
            row["status"] = "error"
            row["trace"].append(event)
            break
        messages.append({"role": "assistant", "content": response["text"]})
        try:
            action = parse_action(response["text"])
            if not isinstance(action, dict) or set(action) != {"tool", "args"} or not isinstance(action["args"], dict):
                raise ValueError
            name, args = action["tool"], action["args"]
            if name == "finish":
                row["success"] = (
                    set(args) == {"entry_id"}
                    and type(args["entry_id"]) is int
                    and args["entry_id"] == task["expected_id"]
                    and args["entry_id"] in observed_ids
                    and response["finish_reason"] != "length"
                )
                row["status"] = "finished"
                event["action"] = action
                row["trace"].append(event)
                break
            if (name != "schedule_search" or args.get("date") not in task["dates"]
                    or args.get("handle") != task["handle"] or args.get("group") != task["group"]
                    or args.get("query") != task["query"]):
                raise ValueError
            args.setdefault("response_format", "concise")
            event["action"] = {"tool": name, "args": args}
        except (ValueError, TypeError, KeyError):
            observation = "Некорректное действие. Верни JSON по схеме, используя handle, group, query и одну из дат задачи."
            event["observation"] = observation
            messages.append({"role": "user", "content": observation})
            row["trace"].append(event)
            continue
        actual = await server.call_tool(name, args)
        actual_text = actual.content[0].text
        drop = rng.random() < 0.5
        observation = "[]" if drop else actual_text
        event["unstable_drop"] = drop
        event["actual_result"] = actual.model_dump(by_alias=True, exclude_none=True)
        if condition == "hint" and observation == "[]":
            observation = "Ничего не найдено; попробуйте другое значение date."
        event["observation"] = observation
        if not actual.is_error and not drop:
            data = json.loads(actual_text)
            observed_ids.update(entry["id"] for entry in data)
        calls.append([name, args])
        row["loop"] = has_loop(calls)
        messages.append({"role": "user", "content": "Результат schedule_search: " + observation})
        if condition == "guard":
            signal = guard.check(name, args, observation)
            if signal:
                signals += 1
                event["guard_signal"] = signal
                messages.append({"role": "user", "content": "LoopGuard: " + signal})
                if signals >= 2:
                    row["status"] = "guard_stop"
                    row["trace"].append(event)
                    break
        row["trace"].append(event)
    return row


async def main():
    tasks = json.loads(Path("data/loop_tasks.json").read_text())
    assert len(tasks) == 20
    model = Model()
    with Path("logs/loops.jsonl").open("w") as output:
        for condition in ["empty", "guard", "hint"]:
            for task in tasks:
                for repeat in range(3):
                    row = await episode(model, task, repeat, condition)
                    output.write(json.dumps(row, ensure_ascii=False) + "\n")
                    output.flush()
                print(f"{condition}: {task['id']} завершена", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
