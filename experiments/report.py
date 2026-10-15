import csv
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "tmp/matplotlib")
import matplotlib
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def read_csv(name):
    with Path("results", name).open() as stream:
        return list(csv.DictReader(stream))


def main():
    fonts = Path(matplotlib.get_data_path()) / "fonts/ttf"
    pdfmetrics.registerFont(TTFont("DejaVu", str(fonts / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuBold", str(fonts / "DejaVuSans-Bold.ttf")))
    body = ParagraphStyle("body", fontName="DejaVu", fontSize=9.1, leading=12, spaceAfter=4)
    heading = ParagraphStyle("heading", parent=body, fontName="DejaVuBold", fontSize=11, leading=14, spaceBefore=7, spaceAfter=6)
    title = ParagraphStyle("title", parent=heading, fontSize=15, leading=19)
    story = []

    def paragraph(text, style=body):
        story.append(Paragraph(text, style))

    def table(rows, widths):
        wrapped = [[Paragraph(str(cell), body) for cell in row] for row in rows]
        item = Table(wrapped, colWidths=widths, repeatRows=1)
        item.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf1f5")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c6cbd1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(item)
        story.append(Spacer(1, 4 * mm))

    selection = read_csv("selection.csv")
    loops = read_csv("loops.csv")
    protocol = json.loads(Path("logs/protocol.json").read_text())
    paragraph("ДЗ 2. Журнал расписания", title)
    paragraph("Задание 2. MCP-сервер", heading)
    paragraph(
        "Реализованы schedule_search, schedule_get, schedule_free и schedule_add. "
        "Состояние хранится в SQLite; handle (main или second) передаётся каждым вызовом. "
        "MCP 2026-07-28: stateless, server/discover, _meta в запросах. "
        "У параметров есть description, закрытые значения заданы enum, лишние поля запрещены. "
        "Ошибки возвращают isError=true и подсказку. concise возвращает основные поля, detailed - все данные."
    )
    paragraph(
        f"Проверка: {protocol['pytest_passed']} теста pytest прошли. MCP Inspector 2.10.1 "
        "проверил каталог, успешные вызовы всех четырёх инструментов и ошибку неизвестного id. "
        "Логи: logs/pytest.txt, logs/inspector.jsonl. Размеры ответов приведены в README."
    )
    paragraph("Задание 3А. Выбор инструмента", heading)
    paragraph(
        "Qwen3-0.6B, MLX, 4 бита, thinking выключен; temperature=0.7, top_p=0.8, top_k=20, "
        "лимит ответа 160 токенов. Пул: 4 своих + 96 сгенерированных инструментов, из них 24 близких по смыслу. "
        "30 размеченных запросов, N=5/20/50/100, 3 запуска (seed=42/43/44). Всего 720 попыток. "
        "Наборы вложены и содержат четыре целевых инструмента; их состав одинаков для A и B."
    )
    paragraph(
        "A получает все N описаний. Для B локальный поиск автоматически выбирает top-5 по косинусной близости "
        "эмбеддингов paraphrase-multilingual-MiniLM-L12-v2. Модель получает описание поиска, выдачу и пять описаний. "
        "Оценивается имя инструмента в текстовом ответе. 95%-е интервалы: 10 000 бутстрэп-выборок запросов; "
        "три повтора каждого запроса сохраняются вместе. Ошибки и незавершённые попытки считаются неверными."
    )
    story.append(Image("results/accuracy.png", width=160 * mm, height=90.7 * mm))
    rows = [["N", "A: верно / 90", "B: верно / 90", "Recall@5", "Токены A / B"]]
    for n in [5, 20, 50, 100]:
        a = next(r for r in selection if r["n"] == str(n) and r["variant"] == "A")
        b = next(r for r in selection if r["n"] == str(n) and r["variant"] == "B")
        rows.append([n, a["correct"], b["correct"], f"{float(b['recall_at_5']):.1%}", f"{float(a['mean_input_tokens']):.0f} / {float(b['mean_input_tokens']):.0f}"])
    table(rows, [13 * mm, 35 * mm, 35 * mm, 29 * mm, 48 * mm])
    story.append(PageBreak())
    paragraph("Задание 3Б. Петли", title)
    paragraph(
        "20 задач по поиску занятия за одну из двух дат, по 3 повтора, 3 условия: всего 180 эпизодов. "
        "Первая дата намеренно не содержит искомого занятия, вторая содержит. schedule_search в 50% вызовов "
        "скрывает результат и возвращает []. Другие вызовы возвращают результат настоящего инструмента. "
        "Для одинаковых задач и повторов используется одинаковый seed генератора неисправностей."
    )
    paragraph(
        "Максимум 8 шагов на эпизод. Петля: не менее трёх одинаковых выполненных вызовов подряд либо A-B-A-B. "
        "LoopGuard взят из лекции: 3 одинаковых вызова в окне 6, чередование действий, 6 неизменных наблюдений. "
        "Первый сигнал передаётся модели; второй останавливает эпизод. В третьем условии пустой ответ заменён "
        "на «Ничего не найдено; попробуйте другое значение date», guard выключен."
    )
    paragraph(
        "Успех засчитывается только при финальном правильном id, который до этого действительно наблюдался. "
        "Шаг включает каждый запрос модели, в том числе неправильный JSON. Токены эпизода - сумма входных "
        "и выходных токенов всех его запросов, включая повторно переданную историю."
    )
    names = {"empty": "Пустой ответ", "guard": "Пустой + guard", "hint": "Подсказка"}
    rows = [["Условие", "Эпизоды", "Петли", "Шаги", "Токены", "Успех"]]
    for row in loops:
        rows.append([names[row["condition"]], f"{row['logged']} / {row['expected']}",
                     f"{float(row['loop_rate']):.1%}", f"{float(row['mean_steps']):.2f}",
                     f"{float(row['mean_tokens']):.0f}", f"{float(row['success_rate']):.1%}"])
    table(rows, [44 * mm, 23 * mm, 23 * mm, 21 * mm, 25 * mm, 24 * mm])
    paragraph("Выводы", heading)
    a100 = next(r for r in selection if r["n"] == "100" and r["variant"] == "A")
    b100 = next(r for r in selection if r["n"] == "100" and r["variant"] == "B")
    paragraph(
        f"При N=100 точность A составила {float(a100['accuracy']):.1%}, B - {float(b100['accuracy']):.1%}. "
        f"Входной контекст B меньше в {float(a100['mean_input_tokens']) / float(b100['mean_input_tokens']):.1f} раза. "
        "Поиск уменьшает контекст, но пропуск правильного инструмента ограничивает итоговую точность."
    )
    guard = next(r for r in loops if r["condition"] == "guard")
    hint = next(r for r in loops if r["condition"] == "hint")
    paragraph(
        f"Успех guard - {float(guard['success_rate']):.1%}, подсказки - {float(hint['success_rate']):.1%}. "
        f"Средние шаги: guard {float(guard['mean_steps']):.2f}, подсказка {float(hint['mean_steps']):.2f}. "
        "Долю петель и затраты нужно оценивать отдельно: guard сигнализирует после возникновения повторов, "
        "поэтому обнаруженная петля остаётся в метрике даже после остановки. Различия здесь описательные, "
        "без проверки статистической значимости для условий с петлями."
    )
    if all(float(r["success_rate"]) == 0 for r in loops):
        paragraph(
            f"Подсказка сильнее снижает долю петель: {float(hint['loop_rate']):.1%} против "
            f"{float(guard['loop_rate']):.1%} с guard. Guard сильнее ограничивает шаги и токены. "
            "Ни один способ не повысил долю успеха: "
            "модель не завершала задачу через finish даже после получения верной записи. "
            "По этому прогону можно сравнивать петли и расходы, но нельзя утверждать улучшение успешности."
        )
    paragraph("Полнота данных и бюджет", heading)
    paragraph(
        f"Сохранены {protocol['selection_logged']} / 720 попыток выбора и {protocol['loops_logged']} / 180 эпизодов. "
        f"Ошибки API: выбор - {protocol['selection_errors']}, петли - {protocol['loop_errors']}; "
        f"остановки по лимиту шагов - {protocol['step_limit_episodes']}. Все включены в знаменатели. "
        "Использование токенов получено из usage локального сервера; точные значения и интервалы - results/*.csv. "
        "Эмбеддинги вычисляются локально: их токены записаны отдельно и не входят во входной контекст LLM. "
        "Расходы на API: $0, ключи не используются."
    )
    paragraph(
        f"Первоначальный запуск с другим парсером: {protocol['parser_before_logged']} / 180 эпизодов записаны, "
        "успех 0/180; остальные незавершены. Парсер отвергал JSON в Markdown, инструменты не исполнялись. "
        "Этот запуск сохранён в logs/parser_before_loops.jsonl и показан отдельно: после исправления "
        "повторён полный протокол. Неудачи основного прогона включены в таблицу выше."
    )
    paragraph("Три угрозы валидности", heading)
    paragraph(
        "1. Синтетический пул и только 30 вручную размеченных запросов: реальные формулировки и инструменты могут отличаться.<br/>"
        "2. Одна маленькая модель, 4-битная квантизация и выбор имени текстом: выводы нельзя переносить на другие модели и native tool calling.<br/>"
        "3. Задачи с петлями намеренно начинаются с пустой даты; подсказка особенно полезна в такой среде. "
        "Совпадение seed неисправностей не делает траектории одинаковыми после изменения действий."
    )
    Path("output/pdf").mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate("output/pdf/report.pdf", pagesize=A4, rightMargin=25 * mm, leftMargin=25 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm)
    doc.build(story)


if __name__ == "__main__":
    main()
