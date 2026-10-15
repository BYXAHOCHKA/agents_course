import json
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from experiments.model import Model


EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
SYSTEM = "Выбери один инструмент для запроса. Ответь только его именем, без пояснений."


def main():
    tools = json.loads(Path("data/tools.json").read_text())
    queries = json.loads(Path("data/queries.json").read_text())
    assert len(tools) == 100 and len(queries) == 30
    names = [tool["name"] for tool in tools]
    targets = {query["tool"] for query in queries}
    assert targets <= set(names) and len(targets) <= 5
    required = [i for i, name in enumerate(names) if name in targets]
    distractors = [i for i, name in enumerate(names) if name not in targets]
    random.Random(42).shuffle(distractors)
    order = required + distractors
    embedder = SentenceTransformer("tmp/models/embeddings", device="cpu")
    descriptions = [tool["name"] + ": " + tool["description"] for tool in tools]
    vectors = embedder.encode(descriptions, normalize_embeddings=True)
    query_vectors = embedder.encode([q["text"] for q in queries], normalize_embeddings=True)
    model = Model()
    Path("logs").mkdir(exist_ok=True)
    with Path("logs/selection.jsonl").open("w") as output:
        for n in [5, 20, 50, 100]:
            pool = order[:n]
            for query_index, query in enumerate(queries):
                scores = vectors[pool] @ query_vectors[query_index]
                found = [pool[i] for i in np.argsort(-scores)[:5]]
                for repeat in range(3):
                    for variant in ["A", "B"]:
                        candidates = (pool if variant == "A" else found).copy()
                        random.Random(42 + query_index * 3 + repeat).shuffle(candidates)
                        search_note = ""
                        if variant == "B":
                            search_note = (
                                "tool_search: ищет top-5 инструментов по эмбеддингам описаний. "
                                "Поиск уже выполнен для запроса. Результат: "
                                + ", ".join(names[i] for i in found)
                                + ".\n"
                            )
                        messages = [
                            {"role": "system", "content": SYSTEM},
                            {
                                "role": "user",
                                "content": search_note
                                + "Инструменты:\n"
                                + "\n".join(descriptions[i] for i in candidates)
                                + "\nЗапрос: " + query["text"],
                            },
                        ]
                        row = {
                            "query_id": query["id"], "n": n, "variant": variant,
                            "repeat": repeat, "seed": 42 + repeat,
                            "model": model.name, "embedding_model": EMBEDDING_MODEL,
                            "started_at": datetime.now(timezone.utc).isoformat(),
                            "embedding_input_tokens": len(embedder.tokenizer.encode(query["text"])) if variant == "B" else 0,
                            "correct_tool": query["tool"],
                            "pool": [names[i] for i in pool],
                            "top5": [names[i] for i in found],
                            "scores": [float(scores[pool.index(i)]) for i in found],
                            "recall_at_5": query["tool"] in [names[i] for i in found],
                            "messages": messages, "success": False,
                            "input_tokens": None, "output_tokens": None,
                        }
                        try:
                            result = model.call(messages, row["seed"])
                            row.update(result)
                            predicted = result["text"].strip().strip("`\"'")
                            row["predicted_tool"] = predicted
                            row["success"] = (
                                predicted == query["tool"]
                                and predicted in [names[i] for i in candidates]
                                and result["finish_reason"] != "length"
                            )
                        except Exception as error:
                            row["error"] = type(error).__name__
                        output.write(json.dumps(row, ensure_ascii=False) + "\n")
                        output.flush()
            print(f"N={n}: завершено", flush=True)


if __name__ == "__main__":
    main()
