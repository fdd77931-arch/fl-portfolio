"""Build the current vector index, then optionally verify the full live pipeline."""
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from .api import grounded_answer, verify_answer
from .knowledge import Catalog
from .models import Bailian, ModelUnavailable, Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    backend = Path(__file__).resolve().parents[1]
    load_dotenv(backend / ".env")
    models = Bailian(Settings.from_env())
    try:
        if not models.configured:
            parser.exit(2, "Set DASHSCOPE_API_KEY and the region-specific compatible endpoints.\n")
        catalog = Catalog(os.getenv("HEALTH_AI_DB", str(backend / "var" / "knowledge.db")))
        print(f"Indexed {catalog.reindex(models)} new or changed chunks.")
        if args.smoke:
            question = "养成什么睡眠习惯有助于改善睡眠卫生？"
            evidence, _ = catalog.retrieve(question, models, float(os.getenv("HEALTH_AI_MIN_RERANK_SCORE", "0.55")))
            answer = grounded_answer(models.chat_service(question, [
                {"id": entry.id, "text": entry.text, "title": entry.title} for entry in evidence
            ]), evidence) if evidence else None
            if not answer or not verify_answer(models, question, answer):
                parser.exit(3, "Live smoke question produced no grounded answer.\n")
            print("Bailian embedding, rerank, chat and validated citations passed.")
    except ModelUnavailable as error:
        parser.exit(4, f"Model Studio: {error}\n")
    finally:
        models.client.close()


if __name__ == "__main__":
    main()
