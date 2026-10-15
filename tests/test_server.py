import asyncio
import json
import subprocess
import sys

import pytest
from mcp import Client

import server as app


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "journal.db")


def call(name, args):
    async def run():
        async with Client(app.server, mode="2026-07-28") as client:
            return await client.call_tool(name, args)
    return asyncio.run(run())


def content(result):
    return json.loads(result.content[0].text)


def test_search_success():
    result = call("schedule_search", {"handle": "main", "date": "2026-10-19", "group": "A", "query": "матем"})
    assert not result.is_error
    assert content(result)[0]["id"] == 1


def test_search_error():
    result = call("schedule_search", {"handle": "main", "date": "19.10.2026", "group": "A", "query": ""})
    assert result.is_error
    assert "YYYY-MM-DD" in result.content[0].text


def test_get_success():
    result = call("schedule_get", {"handle": "main", "entry_id": 2, "response_format": "detailed"})
    assert not result.is_error
    assert content(result)[0]["room"] == "305"


def test_get_error():
    result = call("schedule_get", {"handle": "main", "entry_id": 999})
    assert result.is_error
    assert "schedule_search" in result.content[0].text


def test_free_success():
    result = call("schedule_free", {"handle": "main", "date": "2026-10-19", "group": "A", "duration": 60})
    assert not result.is_error
    assert content(result) == [{"start": "08:00", "end": "09:00"}, {"start": "12:30", "end": "20:00"}]


def test_free_error():
    result = call("schedule_free", {"handle": "missing", "date": "2026-10-19", "group": "A", "duration": 60})
    assert result.is_error
    assert "handle=main" in result.content[0].text


def new_entry(**changes):
    args = {"handle": "main", "date": "2026-10-19", "group": "A", "start": "14:00", "duration": 60,
            "title": "Химия", "kind": "lecture", "room": "201", "teacher": "Сидоров"}
    return args | changes


def test_add_success():
    result = call("schedule_add", new_entry())
    assert not result.is_error
    entry_id = content(result)[0]["id"]
    saved = call("schedule_get", {"handle": "main", "entry_id": entry_id, "response_format": "detailed"})
    assert content(saved)[0]["teacher"] == "Сидоров"
    other = call("schedule_get", {"handle": "second", "entry_id": entry_id})
    assert other.is_error


def test_add_error():
    result = call("schedule_add", new_entry(start="09:30"))
    assert result.is_error
    assert "schedule_free" in result.content[0].text


@pytest.mark.parametrize("changes", [{"group": "C"}, {"response_format": "long"}, {"extra": 1}, {"entry_id": "wrong"}])
def test_schema_validation(changes):
    args = {"handle": "main", "entry_id": 1} | changes
    result = call("schedule_get", args)
    assert result.is_error
    assert "Проверьте" in result.content[0].text


def test_schema_descriptions():
    tools = asyncio.run(app.server.list_tools())
    assert len(tools) == 4
    for tool in tools:
        assert tool.name.startswith("schedule_")
        assert "Не использовать" in tool.description
        assert tool.input_schema["additionalProperties"] is False
        for field in tool.input_schema["properties"].values():
            assert field["description"]
        assert tool.input_schema["properties"]["response_format"]["enum"] == ["concise", "detailed"]


def test_formats():
    concise = call("schedule_get", {"handle": "main", "entry_id": 1})
    detailed = call("schedule_get", {"handle": "main", "entry_id": 1, "response_format": "detailed"})
    assert len(concise.content[0].text) < len(detailed.content[0].text)
    assert "room" not in content(concise)[0] and "room" in content(detailed)[0]


def test_stateless_protocol(tmp_path):
    meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientInfo": {"name": "test", "version": "1"},
            "io.modelcontextprotocol/clientCapabilities": {}}
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": meta}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": meta}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"_meta": meta, "name": "schedule_get", "arguments": {"handle": "main", "entry_id": 1}}},
    ]
    process = subprocess.Popen([sys.executable, "server.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    responses = {}
    try:
        for request in requests:
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            response = json.loads(process.stdout.readline())
            responses[response["id"]] = response
    finally:
        process.terminate()
        process.wait(timeout=5)
    assert responses[1]["result"]["supportedVersions"] == ["2026-07-28"]
    assert len(responses[2]["result"]["tools"]) == 4
    assert responses[3]["result"]["isError"] is False
    assert all(r["result"]["resultType"] == "complete" for r in responses.values())
