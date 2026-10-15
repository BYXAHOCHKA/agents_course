import json
import os
import sqlite3
from datetime import date as Date, datetime
from pathlib import Path
from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError
from mcp.server.mcpserver.tools.base import Tool
from mcp.types import CallToolResult, TextContent
from pydantic import Field


DB_PATH = Path(os.environ.get("SCHEDULE_DB", "tmp/journal.db"))
Handle = Annotated[Literal["main", "second"], Field(description="Handle журнала: main или second. Передаётся в каждом вызове.")]
Day = Annotated[str, Field(description="Дата в формате YYYY-MM-DD.")]
Group = Annotated[Literal["A", "B"], Field(description="Учебная группа A или B.")]
Format = Annotated[Literal["concise", "detailed"], Field(description="concise: основные поля; detailed: все поля результата.")]


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE IF NOT EXISTS entries ("
        "id INTEGER PRIMARY KEY, handle TEXT, date TEXT, start TEXT, duration INTEGER, "
        "title TEXT, group_name TEXT, kind TEXT, room TEXT, teacher TEXT)"
    )
    if not db.execute("SELECT 1 FROM entries LIMIT 1").fetchone():
        seed_path = Path(__file__).parent / "data/schedule.json"
        for entry in json.loads(seed_path.read_text()):
            db.execute(
                "INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(entry[key] for key in ["id", "handle", "date", "start", "duration", "title", "group", "kind", "room", "teacher"]),
            )
        db.commit()
    return db


def failure(hint):
    return CallToolResult(content=[TextContent(text=hint)], is_error=True)


def result(data, response_format):
    if response_format == "concise" and isinstance(data, list):
        data = [{k: row[k] for k in ["id", "date", "start", "title"] if k in row} for row in data]
    return CallToolResult(content=[TextContent(text=json.dumps(data, ensure_ascii=False, separators=(",", ":")))])


def check(handle, day=None):
    if handle not in ["main", "second"]:
        return "Журнал не найден. Передайте handle=main или handle=second."
    if day is not None:
        try:
            if Date.fromisoformat(day).isoformat() != day:
                raise ValueError
        except ValueError:
            return "Некорректная дата. Передайте date в формате YYYY-MM-DD, например 2026-10-19."
    return None


def minutes(value):
    parsed = datetime.strptime(value, "%H:%M")
    if parsed.strftime("%H:%M") != value:
        raise ValueError
    return parsed.hour * 60 + parsed.minute


def clock(value):
    return f"{value // 60:02d}:{value % 60:02d}"


def schedule_search(
    handle: Handle, date: Day, group: Group,
    query: Annotated[str, Field(description="Часть названия занятия. Пустая строка означает все занятия дня.")],
    response_format: Format = "concise",
) -> CallToolResult:
    """Найти записи журнала расписания по дате, группе и названию. Не использовать для получения записи по известному id или поиска свободного времени."""
    if hint := check(handle, date):
        return failure(hint)
    with connect() as db:
        entries = db.execute(
            "SELECT * FROM entries WHERE handle=? AND date=? AND group_name=? ORDER BY start, id",
            (handle, date, group),
        ).fetchall()
    data = [dict(row) for row in entries if query.casefold() in row["title"].casefold()]
    return result(data, response_format)


def schedule_get(
    handle: Handle,
    entry_id: Annotated[int, Field(description="Идентификатор записи, полученный из schedule_search или schedule_add.", ge=1)],
    response_format: Format = "concise",
) -> CallToolResult:
    """Получить одну запись журнала расписания по известному id. Не использовать, если id неизвестен: сначала вызвать schedule_search."""
    if hint := check(handle):
        return failure(hint)
    with connect() as db:
        entry = db.execute("SELECT * FROM entries WHERE handle=? AND id=?", (handle, entry_id)).fetchone()
    if entry is None:
        return failure("Запись не найдена. Проверьте handle и entry_id; найдите id через schedule_search.")
    return result([dict(entry)], response_format)


def schedule_free(
    handle: Handle, date: Day, group: Group,
    duration: Annotated[int, Field(description="Минимальная длительность свободного интервала в минутах.", ge=15, le=240)],
    response_format: Format = "concise",
) -> CallToolResult:
    """Найти свободные интервалы группы в журнале расписания между 08:00 и 20:00. Не использовать для поиска занятия по названию или для добавления записи."""
    if hint := check(handle, date):
        return failure(hint)
    with connect() as db:
        busy = db.execute(
            "SELECT start, duration FROM entries WHERE handle=? AND date=? AND group_name=? ORDER BY start",
            (handle, date, group),
        ).fetchall()
    cursor = 8 * 60
    slots = []
    for row in busy:
        start = minutes(row["start"])
        if start - cursor >= duration:
            slots.append({"start": clock(cursor), "end": clock(start), "minutes": start - cursor})
        cursor = max(cursor, start + row["duration"])
    if 20 * 60 - cursor >= duration:
        slots.append({"start": clock(cursor), "end": "20:00", "minutes": 20 * 60 - cursor})
    if response_format == "concise":
        return result([{ "start": s["start"], "end": s["end"]} for s in slots], "detailed")
    return result({"date": date, "group": group, "duration": duration, "slots": slots}, response_format)


def schedule_add(
    handle: Handle, date: Day, group: Group,
    start: Annotated[str, Field(description="Начало занятия в формате HH:MM, с 08:00 до 20:00.")],
    duration: Annotated[int, Field(description="Длительность занятия в минутах.", ge=15, le=240)],
    title: Annotated[str, Field(description="Непустое название занятия.", min_length=1)],
    kind: Annotated[Literal["lecture", "practice", "exam"], Field(description="Тип занятия: lecture, practice или exam.")],
    room: Annotated[str, Field(description="Аудитория занятия.", min_length=1)],
    teacher: Annotated[str, Field(description="Имя преподавателя.", min_length=1)],
    response_format: Format = "concise",
) -> CallToolResult:
    """Добавить новое занятие в журнал расписания, если у группы нет пересечения по времени. Не использовать для изменения существующей записи или простого просмотра расписания."""
    if hint := check(handle, date):
        return failure(hint)
    try:
        begin = minutes(start)
    except ValueError:
        return failure("Некорректное время. Передайте start в формате HH:MM, например 10:30.")
    if begin < 8 * 60 or begin + duration > 20 * 60:
        return failure("Занятие выходит за 08:00-20:00. Измените start или duration.")
    if not all(value.strip() for value in [title, room, teacher]):
        return failure("Пустое название, аудитория или преподаватель. Заполните title, room и teacher.")
    with connect() as db:
        entries = db.execute(
            "SELECT start, duration FROM entries WHERE handle=? AND date=? AND group_name=?",
            (handle, date, group),
        ).fetchall()
        for entry in entries:
            other = minutes(entry["start"])
            if begin < other + entry["duration"] and other < begin + duration:
                return failure("Время занято. Найдите другой интервал через schedule_free и измените start.")
        cursor = db.execute(
            "INSERT INTO entries (handle,date,start,duration,title,group_name,kind,room,teacher) VALUES (?,?,?,?,?,?,?,?,?)",
            (handle, date, start, duration, title.strip(), group, kind, room.strip(), teacher.strip()),
        )
        entry = dict(db.execute("SELECT * FROM entries WHERE id=?", (cursor.lastrowid,)).fetchone())
    return result([entry], response_format)


class ScheduleServer(MCPServer):
    async def call_tool(self, name, arguments, context=None):
        try:
            return await super().call_tool(name, arguments, context)
        except UnexpectedToolError:
            return failure("Не удалось обработать запрос. Проверьте параметры и повторите вызов.")
        except ToolError:
            return failure("Некорректные параметры. Проверьте имя инструмента, обязательные поля, типы и enum; удалите лишние поля. Передайте handle=main или handle=second.")


tools = []
for fn in [schedule_search, schedule_get, schedule_free, schedule_add]:
    tool = Tool.from_function(fn, structured_output=False)
    tool.fn_metadata.arg_model.model_config["extra"] = "forbid"
    tool.fn_metadata.arg_model.model_rebuild(force=True)
    tool.parameters = tool.fn_metadata.arg_model.model_json_schema()
    tools.append(tool)

server = ScheduleServer("schedule-journal", version="1.0.0", tools=tools)

if __name__ == "__main__":
    server.run(transport="stdio")
