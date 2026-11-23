import csv
from pathlib import Path
import pytest
from src.playbook_loader import Playbook
from src.extractor import FactExtractor
from src.decision_engine import evaluate_thread

REPO_ROOT = Path(__file__).resolve().parent.parent

def load_samples():
    threads_path = REPO_ROOT / "data" / "sample_threads.csv"
    if not threads_path.exists():
        threads_path = REPO_ROOT / "sample_threads.csv"
        
    answers_path = REPO_ROOT / "data" / "sample_answers.csv"
    if not answers_path.exists():
        answers_path = REPO_ROOT / "sample_answers.csv"
        
    with open(answers_path, "r", encoding="utf-8") as f:
        answers = dict(csv.reader(f))
        
    with open(threads_path, "r", encoding="utf-8") as f:
        threads = list(csv.DictReader(f))
        
    cases = []
    for t in threads:
        tid = t["thread_id"]
        expected = answers[tid]
        cases.append((tid, t, expected))
    return cases

CASES = load_samples()

@pytest.fixture(scope="session")
def playbook():
    return Playbook.load_from_disk(str(REPO_ROOT / "playbook"))

@pytest.fixture(scope="session")
def extractor():
    return FactExtractor(cache_dir=str(REPO_ROOT / "cache"))

@pytest.mark.parametrize("thread_id,thread_row,expected_label", CASES, ids=[c[0] for c in CASES])
def test_worked_example(thread_id, thread_row, expected_label, playbook, extractor):
    facts = extractor.extract(thread_row)
    actual_label = evaluate_thread(thread_row, facts, playbook)
    assert actual_label == expected_label, (
        f"Mismatch for thread {thread_id}!\n"
        f"Expected: {expected_label}\n"
        f"Actual:   {actual_label}\n"
        f"Facts:    {facts.model_dump()}\n"
    )
