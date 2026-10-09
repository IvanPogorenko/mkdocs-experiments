import csv
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data/experiments.csv"
VERSION_FILE = ROOT / "data/version.txt"
CACHE = ROOT / "generated/cache.json"
RESULT = ROOT / "docs/generated/results.md"
CHART = ROOT / "docs/assets/performance.png"


def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT, text=True
        ).strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"


def main():
    start = time.perf_counter()

    dataset_version = VERSION_FILE.read_text().strip()
    source = DATA.read_bytes()
    fingerprint = hashlib.sha256(
        source + dataset_version.encode()
    ).hexdigest()

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    CHART.parent.mkdir(parents=True, exist_ok=True)

    cached = None
    if CACHE.exists():
        cached = json.loads(CACHE.read_text())

    cache_hit = (
        cached is not None
        and cached.get("fingerprint") == fingerprint
        and CHART.exists()
    )

    if cache_hit:
        rows = cached["rows"]
        print("CACHE HIT: расчёты и график не пересчитываются")
    else:
        print("CACHE MISS: выполняется расчёт")
        with DATA.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))

        for row in rows:
            row["workers"] = int(row["workers"])
            for key in ("avg_ms", "p95_ms", "rps", "errors_pct"):
                row[key] = float(row[key])

        baseline = next(r for r in rows if r["config"] == "A")
        for row in rows:
            row["time_reduction_pct"] = round(
                (baseline["avg_ms"] - row["avg_ms"])
                / baseline["avg_ms"] * 100, 1
            )
            row["throughput_growth_pct"] = round(
                (row["rps"] - baseline["rps"])
                / baseline["rps"] * 100, 1
            )

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.figure(figsize=(8, 4.5))
        plt.bar(
            [r["config"] for r in rows],
            [r["rps"] for r in rows]
        )
        plt.title("HTTP server throughput")
        plt.xlabel("Configuration")
        plt.ylabel("Requests per second")
        plt.tight_layout()
        plt.savefig(CHART, dpi=150)
        plt.close()

        CACHE.write_text(json.dumps({
            "fingerprint": fingerprint,
            "rows": rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    commit = git_commit()
    build_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    table = [
        "| Метрика | A | B | C |",
        "|---|---:|---:|---:|",
    ]
    metrics = [
        ("Среднее время ответа, мс", "avg_ms"),
        ("95-й перцентиль, мс", "p95_ms"),
        ("Пропускная способность, запросов/с", "rps"),
        ("Ошибки, %", "errors_pct"),
    ]

    for label, key in metrics:
        values = [
            str(int(r[key])) if key == "rps" else str(r[key])
            for r in rows
        ]
        table.append(f"| {label} | " + " | ".join(values) + " |")

    comparison = [
        "| Конфигурация | Снижение среднего времени, % | Прирост пропускной способности, % |",
        "|---|---:|---:|",
    ]

    for r in rows:
        comparison.append(
            f"| {r['config']} | {r['time_reduction_pct']} "
            f"| {r['throughput_growth_pct']} |"
        )


    markdown = f"""# Автоматически рассчитанные результаты

Все значения — демонстрационные, а не реальные измерения.

## Сводная таблица

{chr(10).join(table)}

## Пропускная способность

![График пропускной способности](../assets/performance.png)

## Сравнение с конфигурацией A

{chr(10).join(comparison)}

## Метаданные сборки

- Git commit: `{commit}`
- Дата сборки: `{build_date}`
- Версия набора данных: `{dataset_version}`
- SHA-256 набора данных: `{fingerprint[:12]}`
- Кэш: `{"HIT — расчёты пропущены" if cache_hit else "MISS — выполнен пересчёт"}`
"""

    RESULT.write_text(markdown, encoding="utf-8")

    elapsed = time.perf_counter() - start
    print(f"Результат: {RESULT.relative_to(ROOT)}")
    print(f"Кэш: {'HIT' if cache_hit else 'MISS'}")
    print(f"Время выполнения: {elapsed:.3f} с")


if __name__ == "__main__":
    main()