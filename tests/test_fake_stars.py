import pytest

from repo_scout import fake_stars
from repo_scout.fake_stars import best, load, score, split, table


@pytest.mark.filterwarnings("error")  # an unclosed file raises ResourceWarning
def test_load_reads_labels_and_closes_file(tmp_path):
    path = tmp_path / "labels.csv"
    path.write_text("repo,label,source\na/x,1,s\nb/y,0,s\n")
    assert load(path) == [("a/x", 1), ("b/y", 0)]


def test_split_is_stratified_deterministic_and_disjoint():
    labels = [(f"p/{i}", 1) for i in range(5)] + [(f"n/{i}", 0) for i in range(4)]
    tune, test = split(labels)
    assert split(list(reversed(labels))) == (tune, test)  # seed + sort: input order does not matter
    assert sorted(tune + test) == sorted(labels) and not set(tune) & set(test)
    assert sum(y for _, y in tune) == 2 and sum(1 - y for _, y in tune) == 2  # half of each class, rounded down


def test_score_counts_flags_and_treats_missing_history_as_unflagged(monkeypatch):
    shares = {"p1": 0.9, "p2": 0.1, "p3": None, "n1": 0.8, "n2": 0.0}
    monkeypatch.setattr(fake_stars.stars, "share", lambda h, mb: shares[h])
    labels = [("p1", 1), ("p2", 1), ("p3", 1), ("p4", 1), ("n1", 0), ("n2", 0)]
    hist = {n: n for n in shares}  # p4 has no history
    assert score(labels, hist, 0.5, 5) == {"thr": 0.5, "min_burst": 5, "tp": 1, "fp": 1, "precision": 0.5,
                                           "recall": 0.25, "fpr": 0.5}
    assert score(labels, hist, 0.95, 5)["precision"] == 0.0  # nothing flagged: no division by zero


def row(fpr, recall, thr=0.5):
    return {"thr": thr, "min_burst": 5, "tp": 0, "fp": 0, "precision": 0.0, "recall": recall, "fpr": fpr}


def test_best_minimizes_fpr_at_enough_recall_then_prefers_recall():
    rows = [row(0.01, 0.4), row(0.10, 0.6), row(0.05, 0.5), row(0.05, 0.7, thr=0.7)]
    assert best(rows) == row(0.05, 0.7, thr=0.7)


def test_best_falls_back_to_max_recall():
    assert best([row(0.0, 0.1), row(0.3, 0.4)]) == row(0.3, 0.4)


def test_table_renders_markdown_rows():
    lines = table([row(0.125, 0.5)]).splitlines()
    assert lines[0].startswith("| threshold |") and len(lines) == 3
    assert lines[2] == "| 0.5 | 5 | 0 | 0 | 0.00 | 0.50 | 0.12 |"


@pytest.mark.parametrize("labels", [[("a", 1)], [("a", 0)]])
def test_split_keeps_single_item_classes_in_test(labels):
    assert split(labels) == ([], labels)
