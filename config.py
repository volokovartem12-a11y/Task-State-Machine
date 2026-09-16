r"""
Приватное хранение ключа.

Порядок поиска:
  1. файл .env рядом со скриптом   (основной способ, в .gitignore)
  2. переменная окружения AITUNNEL_API_KEY
  3. скрытый ввод с клавиатуры (getpass) — символы не отображаются

Записать ключ один раз:
    py -3 .\config.py --set-key
Проверить, что он на месте (покажет только маску):
    py -3 .\config.py --check
"""
from __future__ import annotations

import argparse
import getpass
import os
import stat
from pathlib import Path

BASE = Path(__file__).parent
ENV_PATH = BASE / ".env"
DEFAULT_MODEL = "gpt-4o-mini"


def _read_env_file() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    data: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def mask(key: str) -> str:
    return f"{key[:11]}...{key[-4:]}" if len(key) > 18 else "***"


def get_api_key(interactive: bool = True) -> str:
    key = _read_env_file().get("AITUNNEL_API_KEY") or os.environ.get("AITUNNEL_API_KEY")
    if key:
        return key
    if not interactive:
        raise RuntimeError("Ключ не найден. Выполни: py -3 .\\config.py --set-key")
    key = getpass.getpass("Ключ AITunnel (ввод скрыт): ").strip()
    if not key:
        raise RuntimeError("Пустой ключ")
    return key


def get_model() -> str:
    return _read_env_file().get("AITUNNEL_MODEL") or os.environ.get(
        "AITUNNEL_MODEL", DEFAULT_MODEL
    )


def set_key() -> None:
    """Скрытый ввод + запись в .env. В терминале ключ не появляется."""
    key = getpass.getpass("Ключ AITunnel (ввод скрыт): ").strip()
    if not key:
        print("Пустой ключ, ничего не записано.")
        return
    model = input(f"Модель [{DEFAULT_MODEL}]: ").strip() or DEFAULT_MODEL

    env = _read_env_file()
    env["AITUNNEL_API_KEY"] = key
    env["AITUNNEL_MODEL"] = model
    ENV_PATH.write_text(
        "\n".join(f"{k}={v}" for k, v in env.items()) + "\n", encoding="utf-8"
    )
    try:  # на Windows ACL это не меняет, но на *nix закрывает файл от чужих
        ENV_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    print(f"Записано в {ENV_PATH.name}: {mask(key)}, модель {model}")
    print("Файл .env уже в .gitignore — в репозиторий не попадёт.")


def check() -> None:
    env = _read_env_file()
    src = ".env" if env.get("AITUNNEL_API_KEY") else (
        "переменная окружения" if os.environ.get("AITUNNEL_API_KEY") else None
    )
    if not src:
        print("Ключ НЕ найден. Выполни: py -3 .\\config.py --set-key")
        return
    key = env.get("AITUNNEL_API_KEY") or os.environ["AITUNNEL_API_KEY"]
    print(f"Ключ найден ({src}): {mask(key)}")
    print(f"Модель: {get_model()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--set-key", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.set_key:
        set_key()
    elif args.check:
        check()
    else:
        parser.print_help()
