r"""
День 13. Агент с формализованным состоянием задачи.

Каждая команда — отдельный запуск процесса. Состояние читается из tasks/<id>.json
и туда же пишется. Между командами в памяти не остаётся ничего: если продолжение
работает, значит оно работает за счёт состояния, а не за счёт живого контекста.

    py -3 .\agent.py new "цель задачи"
    py -3 .\agent.py plan   <id>      # planning: составить план шагов
    py -3 .\agent.py step   <id>      # execution: выполнить один текущий шаг
    py -3 .\agent.py run    <id>      # выполнять шаги подряд до конца/паузы
    py -3 .\agent.py check  <id>      # validation: проверить результат
    py -3 .\agent.py pause  <id> [--reason "..."]
    py -3 .\agent.py resume <id>
    py -3 .\agent.py status <id>
    py -3 .\agent.py list

Флаги: --mock (без API), --model gpt-4o-mini
"""
from __future__ import annotations

import argparse
import json

import llm
from state import TaskState, TransitionError, list_tasks

PLANNER_SYSTEM = """Ты планировщик. Разбей задачу на 4-6 конкретных шагов.
Ответ строго JSON без markdown: {"steps": ["шаг 1", "шаг 2", ...]}"""

WORKER_SYSTEM = """Ты исполнитель. Тебе дана сводка состояния задачи и текущий шаг.
Выполни ТОЛЬКО текущий шаг и верни результат: 3-6 предложений по делу.
Не переспрашивай условия задачи — всё нужное уже в сводке."""

CHECKER_SYSTEM = """Ты проверяющий. По сводке задачи оцени, выполнена ли цель.
Ответ строго JSON без markdown: {"verdict": "pass"|"fail", "issues": ["..."]}"""


def _ask(args):
    return llm.make_ask(model=args.model, mock=args.mock)


def _parse_json(text: str) -> dict:
    s = (text or "").strip()
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1:
        return {}
    try:
        return json.loads(s[a : b + 1])
    except json.JSONDecodeError:
        return {}


def _guard(task: TaskState) -> bool:
    if task.status == "paused":
        print(f"Задача на паузе (этап {task.stage}). Продолжить: py -3 .\\agent.py resume {task.id}")
        return False
    if task.status == "finished":
        print(f"Задача завершена {task.updated_at}.")
        return False
    return True


# --------------------------------------------------------------------------- #
def cmd_new(args) -> None:
    task = TaskState.create(args.goal)
    task.set_expected("agent", "составить план (команда plan)")
    task.save()
    print(f"Создана {task.id}")
    print(f"Этап: {task.stage} | ожидается: {task.expected_actor} — {task.expected_action}")


def cmd_plan(args) -> None:
    task = TaskState.load(args.id)
    if not _guard(task):
        return
    if task.stage != "planning":
        print(f"Этап {task.stage}, планирование уже пройдено.")
        return

    text, usage = _ask(args)([
        {"role": "system", "content": PLANNER_SYSTEM},
        {"role": "user", "content": task.goal},
    ])
    steps = _parse_json(text).get("steps", [])
    if not steps:
        print("Модель не вернула план. Повтори команду.")
        return

    task.set_steps(steps)
    task.advance("execution")
    cur = task.current()
    task.set_expected("agent", f"выполнить шаг {cur['n']}: {cur['title']}")
    task.save()

    print(f"План на {len(steps)} шагов:")
    for s in task.steps:
        print(f"  {s['n']}. {s['title']}")
    print(f"\nЭтап: {task.stage} | ожидается: {task.expected_action}")
    print(f"[tokens: {usage['prompt_tokens']}/{usage['completion_tokens']}]")


def cmd_step(args) -> None:
    task = TaskState.load(args.id)
    if not _guard(task):
        return
    if task.stage != "execution":
        print(f"Шаги выполняются на этапе execution, сейчас {task.stage}.")
        return
    cur = task.current()
    if not cur:
        print("Шаги закончились. Дальше: py -3 .\\agent.py check " + task.id)
        return

    # вот здесь и происходит «без повторных объяснений»: в модель уходит
    # компактная сводка состояния, а не весь прошлый диалог
    brief = task.resume_brief()
    text, usage = _ask(args)([
        {"role": "system", "content": WORKER_SYSTEM},
        {"role": "user", "content": f"{brief}\n\nВыполни шаг {cur['n']}: {cur['title']}"},
    ])

    task.complete_current(text.strip())
    nxt = task.current()
    if nxt:
        task.set_expected("agent", f"выполнить шаг {nxt['n']}: {nxt['title']}")
    else:
        task.advance("validation")
        task.set_expected("agent", "проверить результат (команда check)")
    task.save()

    print(f"Шаг {cur['n']}. {cur['title']} — готово")
    print(text.strip()[:400])
    print(f"\nПрогресс: {task.progress()} | этап: {task.stage} | далее: {task.expected_action}")
    print(f"[tokens: {usage['prompt_tokens']}/{usage['completion_tokens']} | сводка: {len(brief)} симв.]")


def cmd_run(args) -> None:
    """Выполняет шаги подряд. Останавливается на паузе, на смене этапа или на лимите."""
    for _ in range(args.max_steps):
        task = TaskState.load(args.id)
        if task.status != "active" or task.stage != "execution" or not task.current():
            break
        cmd_step(args)
        print("-" * 50)
    task = TaskState.load(args.id)
    print(f"Остановка: этап {task.stage}, статус {task.status}, прогресс {task.progress()}")


def cmd_check(args) -> None:
    task = TaskState.load(args.id)
    if not _guard(task):
        return
    if task.stage != "validation":
        print(f"Проверка идёт на этапе validation, сейчас {task.stage}.")
        return

    text, usage = _ask(args)([
        {"role": "system", "content": CHECKER_SYSTEM},
        {"role": "user", "content": task.resume_brief(max_results=10)},
    ])
    data = _parse_json(text)
    verdict = data.get("verdict", "fail")
    issues = data.get("issues", [])

    if verdict == "pass":
        task.advance("done")
        print("Проверка пройдена. Задача закрыта.")
    else:
        for i in issues:
            task.notes.append(f"замечание: {i}")
        task.advance("execution")          # validation -> execution разрешён
        task.steps.append({"n": len(task.steps) + 1,
                           "title": "Исправить замечания проверки",
                           "stage": "execution", "status": "pending", "result": ""})
        task.set_expected("agent", "доработать по замечаниям (команда step)")
        print("Проверка не пройдена, вернулись в execution:")
        for i in issues:
            print(f"  - {i}")
    task.save()
    print(f"Этап: {task.stage} | статус: {task.status}")
    print(f"[tokens: {usage['prompt_tokens']}/{usage['completion_tokens']}]")


def cmd_pause(args) -> None:
    task = TaskState.load(args.id)
    try:
        task.pause(args.reason)
    except TransitionError as e:
        print(e)
        return
    task.save()
    print(f"Пауза на этапе {task.stage}, шаг {task.current_step + 1}. Состояние: {task.path()}")


def cmd_resume(args) -> None:
    task = TaskState.load(args.id)
    try:
        task.resume()
    except TransitionError as e:
        print(e)
        return
    task.save()
    print("Продолжаем без повторных объяснений. Сводка, которая уйдёт в модель:\n")
    print(task.resume_brief())


def cmd_status(args) -> None:
    task = TaskState.load(args.id)
    print(task.resume_brief())
    print("\nИстория:")
    for h in task.history[-8:]:
        print(f"  {h['ts']}  {h['event']:8} {h['detail']}")


def cmd_list(args) -> None:
    rows = list_tasks()
    if not rows:
        print("Задач нет. Создать: py -3 .\\agent.py new \"цель\"")
        return
    for r in rows:
        print(f"{r['id']}  {r['stage']:10} {r['status']:8} {r['progress']:>6}  {r['goal']}")


# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None)
    parser.add_argument("--mock", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new");    p.add_argument("goal");  p.set_defaults(func=cmd_new)
    p = sub.add_parser("plan");   p.add_argument("id");    p.set_defaults(func=cmd_plan)
    p = sub.add_parser("step");   p.add_argument("id");    p.set_defaults(func=cmd_step)
    p = sub.add_parser("run");    p.add_argument("id");    p.add_argument("--max-steps", type=int, default=10); p.set_defaults(func=cmd_run)
    p = sub.add_parser("check");  p.add_argument("id");    p.set_defaults(func=cmd_check)
    p = sub.add_parser("pause");  p.add_argument("id");    p.add_argument("--reason", default=""); p.set_defaults(func=cmd_pause)
    p = sub.add_parser("resume"); p.add_argument("id");    p.set_defaults(func=cmd_resume)
    p = sub.add_parser("status"); p.add_argument("id");    p.set_defaults(func=cmd_status)
    p = sub.add_parser("list");   p.set_defaults(func=cmd_list)

    args = parser.parse_args()
    try:
        args.func(args)
    except (FileNotFoundError, TransitionError) as e:
        print(f"Ошибка: {e}")


if __name__ == "__main__":
    main()
