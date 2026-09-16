r"""
День 13. Состояние задачи как конечный автомат.

Два независимых измерения:

  STAGE  (этап работы)     planning -> execution -> validation -> done
                                          ^              |
                                          +--------------+   (validation -> execution: доработка)

  STATUS (жизненный цикл)  active <-> paused,  затем finished

Пауза — НЕ отдельный этап. Иначе, встав на паузу в execution, мы потеряли бы
информацию о том, куда возвращаться. Поэтому пауза это флаг поверх этапа.

Состояние целиком лежит в tasks/<id>.json и читается заново при каждом запуске:
процесс можно закрыть в любой момент, задача продолжится с того же шага.
"""
from __future__ import annotations

import json
import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

TASKS_DIR = Path(__file__).parent / "tasks"

STAGES = ["planning", "execution", "validation", "done"]

ALLOWED: dict[str, list[str]] = {
    "planning": ["execution"],
    "execution": ["validation"],
    "validation": ["done", "execution"],  # не прошло проверку — назад в работу
    "done": [],
}

# кто должен сделать следующий ход
ACTORS = ("agent", "user", "none")


class TransitionError(Exception):
    pass


def now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


@dataclass
class Step:
    n: int
    title: str
    stage: str = "execution"
    status: str = "pending"  # pending | done | failed
    result: str = ""


@dataclass
class TaskState:
    id: str
    goal: str
    stage: str = "planning"
    status: str = "active"  # active | paused | finished
    steps: list[dict[str, Any]] = field(default_factory=list)
    current_step: int = 0  # индекс в steps
    expected_actor: str = "agent"
    expected_action: str = "составить план"
    notes: list[str] = field(default_factory=list)
    history: list[dict[str, str]] = field(default_factory=list)
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)

    # ------------------------------------------------------------------ #
    # переходы
    # ------------------------------------------------------------------ #
    def log(self, event: str, detail: str = "") -> None:
        self.history.append({"ts": now(), "event": event, "detail": detail})

    def advance(self, to_stage: str) -> None:
        if self.status == "paused":
            raise TransitionError("Задача на паузе — сначала resume")
        if to_stage not in ALLOWED.get(self.stage, []):
            raise TransitionError(
                f"Недопустимый переход {self.stage} -> {to_stage}. "
                f"Разрешено: {ALLOWED.get(self.stage) or 'ничего, задача завершена'}"
            )
        self.log("stage", f"{self.stage} -> {to_stage}")
        self.stage = to_stage
        if to_stage == "done":
            self.status = "finished"
            self.set_expected("none", "задача завершена")
        self.touch()

    def pause(self, reason: str = "") -> None:
        if self.status != "active":
            raise TransitionError(f"Нельзя поставить на паузу из статуса {self.status}")
        self.status = "paused"
        self.log("pause", reason or f"на этапе {self.stage}")
        self.touch()

    def resume(self) -> None:
        if self.status != "paused":
            raise TransitionError(f"Задача не на паузе (статус {self.status})")
        self.status = "active"
        self.log("resume", f"продолжение с этапа {self.stage}, шаг {self.current_step + 1}")
        self.touch()

    def set_expected(self, actor: str, action: str) -> None:
        if actor not in ACTORS:
            raise ValueError(f"Неизвестный actor: {actor}")
        self.expected_actor = actor
        self.expected_action = action
        self.touch()

    # ------------------------------------------------------------------ #
    # шаги
    # ------------------------------------------------------------------ #
    def set_steps(self, titles: list[str]) -> None:
        self.steps = [asdict(Step(n=i + 1, title=t)) for i, t in enumerate(titles)]
        self.current_step = 0
        self.log("plan", f"{len(titles)} шагов")
        self.touch()

    def current(self) -> dict[str, Any] | None:
        if 0 <= self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def complete_current(self, result: str) -> None:
        step = self.current()
        if not step:
            raise TransitionError("Нет текущего шага")
        step["status"] = "done"
        step["result"] = result
        self.log("step", f"{step['n']}. {step['title']} — готово")
        self.current_step += 1
        self.touch()

    def remaining(self) -> list[dict[str, Any]]:
        return [s for s in self.steps if s["status"] != "done"]

    def progress(self) -> str:
        done = sum(1 for s in self.steps if s["status"] == "done")
        return f"{done}/{len(self.steps)}"

    # ------------------------------------------------------------------ #
    # контекст для продолжения
    # ------------------------------------------------------------------ #
    def resume_brief(self, max_results: int = 3) -> str:
        """Компактная сводка для модели: цель + что сделано + где стоим.

        Это и есть ответ на «продолжение без повторных объяснений»: пользователю
        не нужно пересказывать задачу, а модели не нужен весь прошлый диалог.
        """
        lines = [f"Задача: {self.goal}",
                 f"Этап: {self.stage} | статус: {self.status} | прогресс: {self.progress()}"]
        if self.steps:
            lines.append("План:")
            for s in self.steps:
                mark = "x" if s["status"] == "done" else " "
                lines.append(f"  [{mark}] {s['n']}. {s['title']}")
        done_steps = [s for s in self.steps if s["status"] == "done"][-max_results:]
        if done_steps:
            lines.append("Результаты последних шагов:")
            for s in done_steps:
                lines.append(f"  {s['n']}. {s['result'][:300]}")
        if self.notes:
            lines.append("Заметки: " + "; ".join(self.notes[-3:]))
        cur = self.current()
        if cur:
            lines.append(f"Текущий шаг: {cur['n']}. {cur['title']}")
        lines.append(f"Ожидается: {self.expected_actor} — {self.expected_action}")
        return "\n".join(lines)

    def full_history_context(self) -> str:
        """Наивная альтернатива: пересказать вообще всё. Нужна только для сравнения
        в отчёте — показать, во сколько раз дороже обходиться без состояния."""
        lines = [f"Задача: {self.goal}"]
        for s in self.steps:
            lines.append(f"Шаг {s['n']}: {s['title']}")
            if s["result"]:
                lines.append(f"Результат: {s['result']}")
        lines += [f"{h['ts']} {h['event']}: {h['detail']}" for h in self.history]
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # диск
    # ------------------------------------------------------------------ #
    def touch(self) -> None:
        self.updated_at = now()

    def path(self) -> Path:
        return TASKS_DIR / f"{self.id}.json"

    def save(self) -> Path:
        TASKS_DIR.mkdir(exist_ok=True)
        p = self.path()
        p.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    @classmethod
    def load(cls, task_id: str) -> "TaskState":
        p = TASKS_DIR / f"{task_id}.json"
        if not p.exists():
            raise FileNotFoundError(f"Задача не найдена: {p}")
        return cls(**json.loads(p.read_text(encoding="utf-8")))

    @classmethod
    def create(cls, goal: str, task_id: str | None = None) -> "TaskState":
        TASKS_DIR.mkdir(exist_ok=True)
        if not task_id:
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            task_id = f"task-{stamp}"
        task = cls(id=task_id, goal=goal)
        task.log("created", goal)
        task.save()
        return task


def list_tasks() -> list[dict[str, str]]:
    TASKS_DIR.mkdir(exist_ok=True)
    out = []
    for p in sorted(TASKS_DIR.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        out.append({
            "id": d["id"], "stage": d["stage"], "status": d["status"],
            "goal": d["goal"][:50],
            "progress": f"{sum(1 for s in d['steps'] if s['status'] == 'done')}/{len(d['steps'])}",
        })
    return out
