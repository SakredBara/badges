#!/usr/bin/env python3
"""Publish one compliment to each recognized user's wall."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Iterable

DEFAULT_API_URL = "https://egorod.online"
DEFAULT_INTERVAL = 21.0  # The wall endpoint currently permits three requests/minute.
COMPLIMENTS = (
    "Ты замечательный человек — приятно видеть тебя здесь!",
    "Спасибо, что делаешь это место чуточку добрее!",
    "У тебя отлично получается вдохновлять окружающих!",
    "Рад знакомству — оставайся таким же классным человеком!",
    "Твоя искренность и доброта заслуживают признания!",
)


class WallError(RuntimeError):
    """The wall API rejected a post."""


def load_user_ids(path: Path) -> list[int]:
    """Read a JSON array of positive, unique user IDs."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"не удалось прочитать {path}: {exc}") from exc

    if not isinstance(raw, list):
        raise ValueError("файл признанных пользователей должен содержать JSON-массив")

    result: list[int] = []
    seen: set[int] = set()
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"некорректный ID пользователя: {value!r}")
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def load_sent_ids(path: Path) -> set[int]:
    """Read the durable set of users who have already received a post."""
    if not path.exists():
        return set()
    return set(load_user_ids(path))


def save_sent_ids(path: Path, user_ids: set[int]) -> None:
    """Atomically persist sent IDs so an interrupted write cannot lose history."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(sorted(user_ids), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def encode_multipart(content: str, boundary: str) -> bytes:
    return (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="content"\r\n\r\n'
        f"{content}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")


def publish_compliment(
    user_id: int,
    content: str,
    token: str,
    api_url: str = DEFAULT_API_URL,
) -> dict:
    """Create a wall post using the API's multipart request format."""
    boundary = f"----iishnov-wall-{random.getrandbits(64):016x}"
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}/api/users/{user_id}/wall",
        data=encode_multipart(content, boundary),
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "iishnov-wall-compliments/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise WallError(f"API вернул HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise WallError(f"ошибка обращения к API: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("post"), dict):
        raise WallError("API вернул неожиданный ответ")
    return payload


def send_pending(
    recognized_ids: Iterable[int],
    sent_ids: set[int],
    state_path: Path,
    send: Callable[[int, str], object],
    interval: float = DEFAULT_INTERVAL,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Post once per user, recording each success before moving to the next."""
    pending = [user_id for user_id in recognized_ids if user_id not in sent_ids]
    for index, user_id in enumerate(pending):
        compliment = COMPLIMENTS[user_id % len(COMPLIMENTS)]
        send(user_id, compliment)
        sent_ids.add(user_id)
        save_sent_ids(state_path, sent_ids)
        print(f"Комплимент отправлен пользователю {user_id}")
        if index + 1 < len(pending):
            sleep(interval)
    return len(pending)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Оставить по одному комплименту на стенах признанных пользователей."
    )
    parser.add_argument("users", type=Path, help="JSON-файл с ID признанных людей")
    parser.add_argument(
        "--state", type=Path, default=Path(".wall-compliments-sent.json"),
        help="файл учёта отправленных сообщений",
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token = os.environ.get("EGOROD_TOKEN")
    if not token:
        print("Переменная окружения EGOROD_TOKEN не задана", file=sys.stderr)
        return 2
    if args.interval < 0:
        print("Интервал не может быть отрицательным", file=sys.stderr)
        return 2

    try:
        recognized_ids = load_user_ids(args.users)
        sent_ids = load_sent_ids(args.state)
        count = send_pending(
            recognized_ids,
            sent_ids,
            args.state,
            lambda user_id, content: publish_compliment(
                user_id, content, token, args.api_url
            ),
            args.interval,
        )
    except (ValueError, WallError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Готово. Новых сообщений: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
