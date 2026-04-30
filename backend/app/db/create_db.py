from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


DEFAULT_DUMP_PATH = Path(__file__).with_name("dump.sql")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PostgreSQL DB 생성 후 dump.sql을 psql로 복원합니다.")
    parser.add_argument("--db-name", default=os.getenv("POSTGRES_DB", "libraian"))
    parser.add_argument("--user", default=os.getenv("POSTGRES_USER", os.getenv("USER", "")))
    parser.add_argument("--host", default=os.getenv("POSTGRES_HOST", "localhost"))
    parser.add_argument("--port", default=os.getenv("POSTGRES_PORT", "5432"))
    parser.add_argument("--dump-path", type=Path, default=DEFAULT_DUMP_PATH)
    parser.add_argument("--drop", action="store_true", help="기존 DB를 삭제하고 다시 생성")
    return parser.parse_args()


def command_env() -> dict[str, str]:
    env = os.environ.copy()
    if os.getenv("POSTGRES_PASSWORD"):
        env["PGPASSWORD"] = os.environ["POSTGRES_PASSWORD"]
    return env


def require_cli(*names: str) -> None:
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        raise SystemExit(
            "PostgreSQL CLI를 찾을 수 없습니다: "
            + ", ".join(missing)
            + "\nmacOS 예시:\n"
            + "  brew install libpq\n"
            + "  brew link --force libpq"
        )


def run(command: list[str], capture: bool = False) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(command))
    try:
        return subprocess.run(
            command,
            check=True,
            env=command_env(),
            text=True,
            capture_output=capture,
        )
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            print(exc.stdout)
        if exc.stderr:
            print(exc.stderr)
        raise SystemExit(
            "\nPostgreSQL 명령 실행에 실패했습니다. "
            "DB 서버 실행 여부, 사용자명, 비밀번호, 포트를 확인하세요.\n"
            "예: POSTGRES_USER=postgres POSTGRES_PASSWORD=your_password "
            "python3 backend/app/db/create_db.py"
        ) from exc


def psql_command(args: argparse.Namespace, db_name: str) -> list[str]:
    return [
        "psql",
        "--host",
        args.host,
        "--port",
        args.port,
        "--username",
        args.user,
        "--dbname",
        db_name,
    ]


def database_exists(args: argparse.Namespace) -> bool:
    result = run(
        psql_command(args, "postgres")
        + [
            "--tuples-only",
            "--no-align",
            "--command",
            f"SELECT 1 FROM pg_database WHERE datname = '{args.db_name}'",
        ],
        capture=True,
    )
    return result.stdout.strip() == "1"


def create_database(args: argparse.Namespace) -> None:
    if args.drop and database_exists(args):
        run([
            "dropdb",
            "--host",
            args.host,
            "--port",
            args.port,
            "--username",
            args.user,
            args.db_name,
        ])

    if database_exists(args):
        print(f"DB already exists: {args.db_name}")
        return

    run([
        "createdb",
        "--host",
        args.host,
        "--port",
        args.port,
        "--username",
        args.user,
        args.db_name,
    ])


def restore_dump(args: argparse.Namespace) -> None:
    if not args.dump_path.exists():
        raise FileNotFoundError(f"dump file not found: {args.dump_path}")

    run(psql_command(args, args.db_name) + ["--file", str(args.dump_path)])


def main() -> None:
    args = parse_args()
    require_cli("psql", "createdb", "dropdb")
    create_database(args)
    restore_dump(args)
    print(f"Done. Restored {args.dump_path} into database '{args.db_name}'.")


if __name__ == "__main__":
    main()
