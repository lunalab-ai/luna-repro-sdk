"""CPU-only synthetic selection. Default execution never connects or publishes."""
from pathlib import Path
import uuid
import luna_repro as repro


def main():
    target = [0.0, 1.0, 2.0]
    predicted = [value + 0.5 for value in target]
    metrics = {"MAE": sum(abs(a - b) for a, b in zip(target, predicted)) / len(target)}
    comparison = list(zip(target, predicted))
    failed_check = {"passed": False, "maximum_error": 0.5}
    # Public synthetic ID, never a real project. Configure performs no network I/O.
    repro.configure("12345678-1234-5678-1234-567812345678")
    selected = repro.select(namespace={"metrics": metrics, "comparison": comparison, "failed_check": failed_check},
                            purpose="error comparison", title="Synthetic CPU selection", show=False)
    selected.option("comparison", columns=["target", "predicted"])
    destination = Path(".luna-repro") / "selection-demo" / uuid.uuid4().hex
    selected.preview(destination / "preview.html")
    selected.save(destination / "selected.json")
    selected.save_rule(destination / "selection-rule.json")
    print("Local preview:", destination / "preview.html")
    print("No connection or publication. Synthetic MAE =", metrics["MAE"])
    return selected


if __name__ == "__main__":
    main()
