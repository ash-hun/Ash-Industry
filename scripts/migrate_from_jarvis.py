"""[scripts] jarvis-agent 로 쌓인 상태(홈 디렉터리, .env, docker 볼륨, Postgres 이름)를 Ash Industry 이름으로 옮긴다."""

import re
import sys
import shutil
import argparse
import subprocess
from pathlib import Path
from collections.abc import Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
OLD_HOME, NEW_HOME = Path("~/.jarvis"), Path("~/.ash")
# compose 볼륨 이름은 <프로젝트>_<볼륨>. 프로젝트 이름은 기본으로 저장소 디렉터리 이름이다
VOLUME_RENAMES = (("jarvis_data", "ash_data"), ("postgres_data", "postgres_data"), ("mcp_data", "mcp_data"))
ENV_RULES = (
    (re.compile(r"^(\s*#?\s*)JARVIS_", re.M), r"\1ASH_"),
    (re.compile(r"postgresql://jarvis:jarvis@"), "postgresql://ash:ash@"),
    (re.compile(r"(:5432)/jarvis\b"), r"\1/ash"),
    (re.compile(r"(~|/root)/\.jarvis\b"), r"\1/.ash"),
    (re.compile(r"\bjarvis-(backend|frontend|mcp|ion)\b"), r"ash-\1"),
)
# DB 에서 읽은 이름을 SQL 에 그대로 넣기 전에 모양을 확인한다(인젝션 방지)
IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
COPY_IMAGE = "alpine:3.20"
MIGRATOR_ROLE = "ash_migrator"
# pg_class.relkind 마다 이름을 바꿀 때 쓰는 문
RELKIND_STATEMENT = {"r": "TABLE", "p": "TABLE", "i": "INDEX", "I": "INDEX", "S": "SEQUENCE", "v": "VIEW"}
LIST_RELATIONS_SQL = (
    "SELECT c.relname::text || ':' || c.relkind::text FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'public'"
)
ENSURE_MIGRATOR_SQL = (
    f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{MIGRATOR_ROLE}') "
    f"THEN CREATE ROLE {MIGRATOR_ROLE} SUPERUSER LOGIN; END IF; END $$"
)
HAS_OLD_DB_SQL = "SELECT count(*) FROM pg_database WHERE datname = 'jarvis'"
HAS_NEW_DB_SQL = "SELECT count(*) FROM pg_database WHERE datname = 'ash'"
RENAME_ROLE_SQL = "ALTER ROLE jarvis RENAME TO ash; ALTER ROLE ash PASSWORD 'ash'"

Run = Callable[[list[str]], subprocess.CompletedProcess[str]]


def rename_env_text(text: str) -> str:
    """.env 의 JARVIS_ 키와 옛 이름이 든 값(DSN, 경로, 서비스 주소)을 새 이름으로. 두 번 적용해도 같다. 순수 함수."""
    for pattern, repl in ENV_RULES:
        text = pattern.sub(repl, text)
    return text


def relation_renames(rows: Iterable[str]) -> list[tuple[str, str, str]]:
    """`이름:relkind` 줄에서 jarvis 가 든 관계의 (문, 옛 이름, 새 이름). 새 이름이 이미 있으면 건너뛴다. 순수 함수."""
    kinds = dict(row.rsplit(":", 1) for row in rows if ":" in row)
    plan: list[tuple[str, str, str]] = []
    for name in sorted(kinds):
        statement = RELKIND_STATEMENT.get(kinds[name])
        if "jarvis" not in name or statement is None or not IDENTIFIER.match(name):
            continue
        new = name.replace("jarvis", "ash")
        if new not in kinds:
            plan.append((statement, name, new))
    return plan


def volume_plan(existing: Iterable[str], old_project: str, new_project: str) -> list[tuple[str, str]]:
    """옮길 볼륨 쌍. 옛 볼륨이 있는 것만 고른다(새 볼륨이 비었는지는 실행 때 본다). 순수 함수."""
    have = set(existing)
    return [
        (f"{old_project}_{old}", f"{new_project}_{new}")
        for old, new in VOLUME_RENAMES
        if f"{old_project}_{old}" in have
    ]


def copy_home(src: Path, dst: Path) -> bool:
    """dst 가 없을 때만 src 를 복사한다. 임시 디렉터리에 다 쓴 뒤 이름을 바꿔, 중간에 죽어도 다시 돌리면 된다."""
    src, dst = src.expanduser(), dst.expanduser()
    if dst.exists() or not src.is_dir():
        return False
    tmp = dst.with_name(dst.name + ".migrating")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(src, tmp, symlinks=True)
    tmp.rename(dst)
    return True


def copy_env(old_env: Path, new_env: Path) -> bool:
    """새 .env 가 없을 때만 옛 .env 를 이름을 바꿔 쓴다. 비밀값이 들어 있어 내용은 출력하지 않는다."""
    if new_env.exists() or not old_env.is_file():
        return False
    new_env.write_text(rename_env_text(old_env.read_text(encoding="utf-8")), encoding="utf-8")
    new_env.chmod(0o600)
    return True


class DockerMigration:
    """볼륨 복사와 Postgres 이름 바꾸기. 명령은 리스트 인자로만 부른다(shell 을 거치지 않는다)."""

    def __init__(self, run: Run, old_project: str, new_project: str) -> None:
        self._run = run
        self._old = old_project
        self._new = new_project

    def old_stack_running(self) -> bool:
        out = self._run(["docker", "ps", "-q", "--filter", f"label=com.docker.compose.project={self._old}"])
        return bool(out.stdout.strip())

    def copy_volumes(self, apply: bool) -> list[str]:
        listed = self._run(["docker", "volume", "ls", "--format", "{{.Name}}"]).stdout.split()
        done: list[str] = []
        for old, new in volume_plan(listed, self._old, self._new):
            if new in listed and not self._volume_empty(new):
                continue
            done.append(f"{old} -> {new}")
            if apply:
                self._run(["docker", "volume", "create", new])
                self._run([
                    "docker", "run", "--rm", "-v", f"{old}:/from:ro", "-v", f"{new}:/to", COPY_IMAGE,
                    "sh", "-c", "cp -a /from/. /to/",
                ])
        return done

    def rename_postgres(self, apply: bool) -> list[str]:
        """새 스택의 postgres 컨테이너 하나만 떠 있을 때 부른다. 다른 연결이 있으면 DB 이름을 바꿀 수 없다.

        어디서 죽어도 다시 돌리면 된다. 단계마다 이미 끝났는지 보고 넘어간다.
        """
        renamed_role = self._psql("ash", "postgres", "SELECT 1").returncode == 0
        steps: list[str] = []
        if not renamed_role:
            steps += ["database jarvis -> ash", "role jarvis -> ash (password reset)"]
            if apply:
                self._psql_ok("jarvis", "postgres", ENSURE_MIGRATOR_SQL)
                if self._count(HAS_OLD_DB_SQL) and not self._count(HAS_NEW_DB_SQL):
                    self._psql_ok(MIGRATOR_ROLE, "postgres", "ALTER DATABASE jarvis RENAME TO ash")
                # 역할 이름을 바꾸면 MD5 암호가 지워진다. 같은 트랜잭션에서 compose 기본 DSN(ash:ash)에 맞춘다
                self._psql_ok(MIGRATOR_ROLE, "postgres", RENAME_ROLE_SQL)
        if apply:
            self._psql_ok("ash", "postgres", f"DROP ROLE IF EXISTS {MIGRATOR_ROLE}")
        user, db = ("ash", "ash") if apply or renamed_role else ("jarvis", "jarvis")
        listed = self._psql(user, db, LIST_RELATIONS_SQL)
        # 목록을 못 읽으면 바꿀 것이 없다고 말하지 않고 멈춘다(실측: 연산자 모호로 조용히 빈 목록이었다)
        if listed.returncode != 0:
            raise RuntimeError(f"관계 목록 조회 실패: {listed.stderr.strip()[:200]}")
        for statement, old, new in relation_renames(listed.stdout.split()):
            steps.append(f"{old} -> {new}")
            if apply:
                self._psql_ok("ash", "ash", f"ALTER {statement} IF EXISTS {old} RENAME TO {new}")
        return steps

    def _volume_empty(self, volume: str) -> bool:
        probe = ["sh", "-c", "ls -A /v | head -n 1"]
        out = self._run(["docker", "run", "--rm", "-v", f"{volume}:/v:ro", COPY_IMAGE, *probe])
        return not out.stdout.strip()

    def _count(self, sql: str) -> int:
        out = self._psql(MIGRATOR_ROLE, "postgres", sql).stdout.strip()
        return int(out) if out.isdigit() else 0

    def _psql(self, user: str, db: str, sql: str) -> subprocess.CompletedProcess[str]:
        return self._run([
            "docker", "compose", "-p", self._new, "exec", "-T", "postgres",
            "psql", "-U", user, "-d", db, "-tAc", sql,
        ])

    def _psql_ok(self, user: str, db: str, sql: str) -> None:
        out = self._psql(user, db, sql)
        if out.returncode != 0:
            raise RuntimeError(f"psql 실패: {sql.split()[0]} {sql.split()[1]} ({out.stderr.strip()[:200]})")


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=600, cwd=ROOT, check=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-dir", default=str(ROOT.parent / "jarvis_agent"), help="옛 저장소 경로(.env 를 읽는다)")
    parser.add_argument("--old-project", default="jarvis_agent", help="옛 compose 프로젝트 이름")
    parser.add_argument("--new-project", default=ROOT.name, help="새 compose 프로젝트 이름")
    parser.add_argument("--step", choices=["home", "env", "volumes", "postgres"], action="append",
                        help="이 단계만. 여러 번 줄 수 있다. 없으면 home, env, volumes")
    parser.add_argument("--apply", action="store_true", help="실제로 바꾼다. 없으면 계획만 출력한다")
    opts = parser.parse_args(argv)
    steps = opts.step or ["home", "env", "volumes"]
    verb = "적용" if opts.apply else "계획"

    if "home" in steps:
        planned = OLD_HOME.expanduser().is_dir() and not NEW_HOME.expanduser().exists()
        moved = copy_home(OLD_HOME, NEW_HOME) if opts.apply else planned
        print(f"[home] {verb}: {'~/.jarvis -> ~/.ash' if moved else '할 일 없음'}")
    if "env" in steps:
        old_env, new_env = Path(opts.old_dir).expanduser() / ".env", ROOT / ".env"
        planned = old_env.is_file() and not new_env.exists()
        copied = copy_env(old_env, new_env) if opts.apply else planned
        print(f"[env] {verb}: {'.env 를 ASH_ 이름으로 복사' if copied else '할 일 없음'}")
    docker = DockerMigration(run_command, opts.old_project, opts.new_project)
    if "volumes" in steps:
        if docker.old_stack_running():
            msg = f"[volumes] 옛 스택({opts.old_project})이 떠 있다. `docker compose down` 뒤에 다시 실행한다"
            print(msg, file=sys.stderr)
            return 1
        for line in docker.copy_volumes(opts.apply) or ["할 일 없음"]:
            print(f"[volumes] {verb}: {line}")
    if "postgres" in steps:
        for line in docker.rename_postgres(opts.apply) or ["할 일 없음"]:
            print(f"[postgres] {verb}: {line}")
    if not opts.apply:
        print("계획만 출력했다. 바꾸려면 --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
