r"""Генерирует RESULTS.md из output/metrics.json. Запуск: py -3 .\report.py"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).parent
METRICS = BASE / "output" / "metrics.json"
RESULTS = BASE / "RESULTS.md"


def main() -> None:
    if not METRICS.exists():
        raise SystemExit("Нет output/metrics.json — сначала запусти demo.py")
    d = json.loads(METRICS.read_text(encoding="utf-8"))
    o: list[str] = []

    o.append("# День 13. Состояние задачи (Task State Machine) — результаты\n")
    o.append(f"Режим: {'MOCK (без API)' if d['mock'] else 'реальный API'} · "
             f"дата: {d['created_at']}\n")

    o.append("\n## 1. Автомат\n")
    o.append("```")
    o.append("STAGE:   planning -> execution -> validation -> done")
    o.append("                        ^             |")
    o.append("                        +-------------+   (не прошло проверку)")
    o.append("STATUS:  active <-> paused -> finished")
    o.append("```")
    o.append("\nПауза — флаг поверх этапа, а не отдельный этап: иначе при остановке "
             "терялась бы точка возврата.\n")

    o.append("\n## 2. Итог прогона\n")
    o.append("| Параметр | Значение |")
    o.append("|---|---|")
    o.append(f"| Задача | `{d['task_id']}` |")
    o.append(f"| Цель | {d['goal']} |")
    o.append(f"| Финальный этап | {d['final_stage']} |")
    o.append(f"| Финальный статус | {d['final_status']} |")
    o.append(f"| Шагов выполнено | {d['steps_done']}/{d['steps_total']} |")
    o.append(f"| Пауз | {d['pauses']} |")
    o.append(f"| Событий в истории | {d['history_events']} |")

    o.append("\n## 3. Цена продолжения\n")
    o.append("| Способ | Символов | Токенов (оценка) |")
    o.append("|---|---|---|")
    o.append(f"| Сводка состояния (`resume_brief`) | {d['brief_chars']} | {d['brief_tokens_est']} |")
    o.append(f"| Полный пересказ задачи и истории | {d['full_chars']} | {d['full_tokens_est']} |")
    o.append(f"\nЭкономия на каждом запросе после паузы: **{d['saving_pct']}%**. "
             "Это и есть смысл формализованного состояния: продолжение стоит "
             "фиксированно и не растёт вместе с историей.\n")

    o.append("\n## 4. История переходов\n")
    o.append("| Время | Событие | Детали |")
    o.append("|---|---|---|")
    for h in d["history"]:
        o.append(f"| {h['ts']} | {h['event']} | {h['detail']} |")

    o.append("\n## 5. Что проверено\n")
    o.append("- Переходы идут только по разрешённым рёбрам; `check` в середине "
             "`execution` отклоняется.\n")
    o.append("- Пауза срабатывает на любом этапе, а команды работы на паузе "
             "отклоняются с подсказкой, как продолжить.\n")
    o.append("- Каждая команда — новый процесс: контекст в памяти не переживает "
             "команду, продолжение идёт исключительно из `tasks/<id>.json`.\n")
    o.append("- В модель после паузы уходит сводка состояния, а не прошлый диалог: "
             "повторно объяснять задачу не требуется ни пользователю, ни агенту.\n")

    RESULTS.write_text("\n".join(o), encoding="utf-8")
    print(f"Готово: {RESULTS}")


if __name__ == "__main__":
    main()
