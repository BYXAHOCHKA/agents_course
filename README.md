# Журнал расписания

Задания 2 и 3. Локальная модель: Qwen3-0.6B.

## Установка и запуск

Нужны Mac с Apple Silicon и Python 3.12. Команды выполняются из папки проекта.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
hf download mlx-community/Qwen3-0.6B-4bit --revision 73e3e38d981303bc594367cd910ea6eb48349da8 --local-dir tmp/models/qwen3-0.6b
hf download sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 --revision e8f8c211226b894fcb81acc59f3b34ba3efd5f42 --local-dir tmp/models/embeddings --include '*.json' '*.txt' '*.safetensors' '*.model'
```

Запуск MCP-сервера: `python server.py`. Запуск тестов: `pytest -q`.

Для экспериментов запустите модель в отдельном терминале с активированным окружением:

```bash
python -m mlx_lm.server --model tmp/models/qwen3-0.6b --host 127.0.0.1 --port 8080 --chat-template-args '{"enable_thinking":false}'
```

В другом терминале:

```bash
source .venv/bin/activate
python -m experiments.selection
python -m experiments.loops
python -m experiments.analysis
```

Повторный запуск экспериментов перезаписывает основные логи.

## Размеры ответов

`response_format=concise` — краткий ответ, `detailed` — подробный. Токены посчитаны токенизатором Qwen3 для текста ответа без оболочки JSON-RPC.

Во всех примерах `handle=main`. Для поиска занятий и свободного времени: `date=2026-10-19`, `group=A`.

| Пример | concise | detailed |
| --- | ---: | ---: |
| schedule_search, query="" | 68 | 127 |
| schedule_get, entry_id=1 | 36 | 66 |
| schedule_free, duration=60 | 35 | 69 |

Полные параметры и ответы: [response_sizes.json](logs/response_sizes.json).

## Результаты

- [Отчёт](output/pdf/report.pdf) — методика, график, таблицы и выводы.
- [Ноутбук](notebooks/experiment.ipynb) — анализ с сохранёнными результатами.
- [Логи](logs/) — все запуски и проверки, включая первоначальный прогон с ошибкой парсера.
- [Настройки эксперимента](logs/protocol.json) — модели, параметры и бюджет.
