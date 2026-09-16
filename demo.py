r"""
День 13. Демонстрация: полный жизненный цикл задачи через ОТДЕЛЬНЫЕ процессы.

Каждый шаг сценария запускается как `py -3 agent.py ...` в новом процессе.
Между шагами в оперативной памяти не остаётся ничего — только tasks/<id>.json.
Если после паузы работа продолжается, значит её продолжает состояние.

Сценарий:
    new -> plan -> step -> ПАУЗА -> status -> resume -> run -> check
    + попытка недопустимого перехода (check в середине execution)

Запуск:
    py -3 .\demo.py --mock
    py -3 .\demo.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from state import TaskState

BASE = Path(__file__).parent
OUT = BASE / "output"

GOAL = "Подготовить отчёт по продажам за квартал для руководства"


def run(cmd: list[str], mock: bool) -> str:
    full = [sys.executable, str(BASE / "agent.py")] + (["--mock"] if mock else []) + cmd
    # Windows-консоль по умолчанию отдаёт cp1251; заставляем дочерний процесс
    # писать в utf-8, иначе кириллица в выводе ломает чтение.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    proc = subprocess.run(
        full, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, cwd=BASE,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    print(f"$ agent.py {' '.join(cmd)}")
    print(out.rstrip() + "\n" + "-" * 60)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    log: list[str] = []

    def step(title: str, cmd: list[str]) -> str:
        print(f"\n### {title}")
        log.append(f"### {title}")
        out = run(cmd, args.mock)
        log.append(out)
        return out

    # 1. создать задачу
    out = step("1. Создание задачи (stage=planning)", ["new", GOAL])
    m = re.search(r"(task-[\d\-]+)", out)
    if not m:
        print("Не удалось получить id задачи.")
        return
    tid = m.group(1)

    # 2. планирование
    step("2. planning -> execution", ["plan", tid])

    # 3. один шаг
    step("3. Выполнение одного шага", ["step", tid])

    # 4. недопустимый переход
    step("4. Попытка check в середине execution (должна быть отклонена)", ["check", tid])

    # 5. пауза посреди execution
    step("5. Пауза на этапе execution", ["pause", tid, "--reason", "конец рабочего дня"])

    # 6. попытка работать на паузе
    step("6. Попытка выполнить шаг на паузе (должна быть отклонена)", ["step", tid])

    # 7. состояние на диске
    step("7. Состояние задачи (процесс новый, контекста нет)", ["status", tid])

    # 8. продолжение
    step("8. Продолжение без повторных объяснений", ["resume", tid])

    # 9. доработать до конца
    step("9. Остальные шаги подряд", ["run", tid])

    # 10. валидация
    step("10. validation -> done", ["check", tid])

    # 11. финальное состояние
    step("11. Итоговое состояние", ["status", tid])

    # --- метрики ---
    task = TaskState.load(tid)
    brief = task.resume_brief()
    full = task.full_history_context()
    metrics = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mock": args.mock,
        "task_id": tid,
        "goal": task.goal,
        "final_stage": task.stage,
        "final_status": task.status,
        "steps_total": len(task.steps),
        "steps_done": sum(1 for s in task.steps if s["status"] == "done"),
        "history_events": len(task.history),
        "pauses": sum(1 for h in task.history if h["event"] == "pause"),
        "brief_chars": len(brief),
        "brief_tokens_est": len(brief) // 4,
        "full_chars": len(full),
        "full_tokens_est": len(full) // 4,
        "saving_pct": round((1 - len(brief) / max(len(full), 1)) * 100, 1),
        "history": task.history,
    }
    (OUT / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "demo_log.txt").write_text("\n".join(log), encoding="utf-8")

    print("\n=== ИТОГ ===")
    print(f"Задача {tid}: {task.stage}/{task.status}, шагов {task.progress()}, "
          f"пауз {metrics['pauses']}")
    print(f"Сводка для продолжения: {metrics['brief_tokens_est']} токенов "
          f"против {metrics['full_tokens_est']} у полного пересказа "
          f"(экономия {metrics['saving_pct']}%)")
    print(f"Сохранено: {OUT / 'metrics.json'}, {OUT / 'demo_log.txt'}")
    print("Дальше: py -3 .\\report.py")


if __name__ == "__main__":
    main()
