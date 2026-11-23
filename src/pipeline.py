import os
import sys
import csv
import re
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from typing import Optional, List, Tuple
from src.playbook_loader import Playbook
from src.extractor import FactExtractor
from src.decision_engine import evaluate_thread

LABEL_REGEX = re.compile(r'^(ACCEPT|COUNTER|REJECT|ESCALATE):[A-Z0-9_]+:(\d+)?$')

def run_pipeline(
    threads_path: Optional[str] = None,
    output_path: Optional[str] = None,
    cache_dir: Optional[str] = None,
    playbook_dir: Optional[str] = None,
    force_refresh: bool = False
) -> Tuple[Path, List[Tuple[str, str]]]:
    """Runs the procurement desk pipeline on a threads CSV, saving predictions to output_path."""
    repo_root = REPO_ROOT
    
    # 1. Resolve paths
    if threads_path is None:
        t_path = repo_root / "data" / "threads.csv"
        if not t_path.exists():
            t_path = repo_root / "threads.csv"
    else:
        t_path = Path(threads_path)
        
    if output_path is None:
        out_path = repo_root / "outputs" / "submission.csv"
    else:
        out_path = Path(output_path)
        
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 2. Load dependencies
    playbook = Playbook.load_from_disk(playbook_dir)
    extractor = FactExtractor(cache_dir=cache_dir)

    # 3. Read input threads
    with open(t_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        threads = list(reader)

    # 4. Generate predictions
    predictions: List[Tuple[str, str]] = []
    for row in threads:
        tid = row["thread_id"]
        facts = extractor.extract(row, force_refresh=force_refresh)
        label = evaluate_thread(row, facts, playbook)
        
        # Validation on each label
        if not LABEL_REGEX.match(label):
            raise ValueError(f"Generated invalid label format for {tid}: '{label}'")
        if label.startswith("COUNTER:"):
            parts = label.split(":")
            if len(parts) != 3 or not parts[2].isdigit() or int(parts[2]) <= 0:
                raise ValueError(f"COUNTER label must end with a positive integer price: '{label}'")
        else:
            if not label.endswith(":"):
                raise ValueError(f"Non-COUNTER label must have trailing colon: '{label}'")

        predictions.append((tid, label))

    # 5. Write outputs
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["thread_id", "label"])
        writer.writerows(predictions)

    return out_path, predictions

if __name__ == "__main__":
    refresh = "--refresh" in sys.argv or "-f" in sys.argv or True  # Default to True so cache stays synced
    out_file, preds = run_pipeline(force_refresh=refresh)
    print(f"Generated {len(preds)} predictions to {out_file}")
