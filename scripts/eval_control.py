"""Evaluate the synthetic control set, including exact source/side/quote checks."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.agent import run


def evaluate():
    base = ROOT / "data" / "control"
    result = run(list((base / "before").glob("*.txt")), list((base / "after").glob("*.txt")), use_llm=False)
    expected = json.loads((base / "expected.json").read_text())
    passed = 0
    for check in expected["checks"]:
        found = [e for f in result["findings"] if f["type"] == check["type"] for e in f["evidence"]
                 if e["verified"] and e["clause"] == check["clause"] and check["quote"] in e["quote"]
                 and Path(e["doc"]).parent.name == check["side"]]
        passed += bool(found)
        print(f"{'OK' if found else 'MISS'} {check['type']}: {check['side']} / {check['clause']} / {check['quote']}")
    print(f"{passed}/{len(expected['checks'])} проверок пройдено; данные синтетические.")
    return passed == len(expected["checks"])


if __name__ == "__main__":
    raise SystemExit(0 if evaluate() else 1)
