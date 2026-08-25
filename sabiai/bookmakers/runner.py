from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

from .execution import BuildExecutionPlan


@dataclass(frozen=True, slots=True)
class BuildExecutionResult:
    bookmaker_slug: str
    success: bool
    booking_code: str | None
    return_code: int | None
    message: str
    stdout: str = ""
    stderr: str = ""


class BookmakerCommandRunner:
    """Run a previously validated booking-code build plan without using a shell."""

    _allowed_scripts = {
        "sportybet": "scripts/sportybet_book.py",
        "bet9ja": "scripts/bet9ja_book.py",
    }
    _code = re.compile(r"^[A-Za-z0-9_-]{4,40}$")
    _non_codes = {"MANUAL_CODE_NEEDED", "DRY_RUN_CODE_PLACEHOLDER"}

    def execute(
        self,
        plan: BuildExecutionPlan,
        *,
        repo_root: str | Path,
        dry_run: bool = False,
        timeout_seconds: int = 120,
    ) -> BuildExecutionResult:
        if not plan.ready:
            return BuildExecutionResult(
                plan.bookmaker_slug,
                False,
                None,
                None,
                f"Build plan is not ready: {plan.reason}",
            )
        if not plan.command:
            return BuildExecutionResult(
                plan.bookmaker_slug,
                False,
                None,
                None,
                "No registered build command is available.",
            )
        if not plan.legs:
            return BuildExecutionResult(
                plan.bookmaker_slug,
                False,
                None,
                None,
                "Build plan has no ticket legs.",
            )

        expected_script = self._allowed_scripts.get(plan.bookmaker_slug)
        command = shlex.split(plan.command)
        if not expected_script or len(command) != 2:
            return BuildExecutionResult(
                plan.bookmaker_slug,
                False,
                None,
                None,
                "The registered bookmaker command is not on the V2 allow-list.",
            )
        if command[0] not in {"python", "python3"} or command[1] != expected_script:
            return BuildExecutionResult(
                plan.bookmaker_slug,
                False,
                None,
                None,
                "The registered bookmaker command does not match the V2 allow-list.",
            )

        root = Path(repo_root).expanduser().resolve()
        script = (root / expected_script).resolve()
        try:
            script.relative_to(root)
        except ValueError:
            return BuildExecutionResult(
                plan.bookmaker_slug,
                False,
                None,
                None,
                "Bookmaker script resolved outside the repository root.",
            )
        if not script.is_file():
            return BuildExecutionResult(
                plan.bookmaker_slug,
                False,
                None,
                None,
                f"Bookmaker builder not found: {expected_script}",
            )

        payload = [dict(leg) for leg in plan.legs]
        # The release runtime prepares Playwright and its browser inside the V2
        # virtualenv. Reusing the current interpreter keeps the builder inside
        # that accepted runtime even when PATH still resolves ``python3`` to the
        # host interpreter (for example from systemd or an OpenClaw worker).
        argv = [sys.executable, expected_script, "--legs", json.dumps(payload, ensure_ascii=False)]
        if dry_run:
            argv.append("--dry-run")

        try:
            completed = subprocess.run(
                argv,
                cwd=str(root),
                text=True,
                capture_output=True,
                timeout=max(5, int(timeout_seconds)),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return BuildExecutionResult(
                plan.bookmaker_slug,
                False,
                None,
                None,
                "Bookmaker ticket builder timed out.",
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
            )
        except OSError as exc:
            return BuildExecutionResult(
                plan.bookmaker_slug,
                False,
                None,
                None,
                f"Bookmaker ticket builder could not start: {exc}",
            )

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        booking_code = self._extract_code(stdout) if plan.expects_booking_code and not dry_run else None
        if completed.returncode != 0:
            return BuildExecutionResult(
                plan.bookmaker_slug,
                False,
                booking_code,
                completed.returncode,
                "Bookmaker ticket builder returned an error.",
                stdout=stdout,
                stderr=stderr,
            )
        if dry_run:
            return BuildExecutionResult(
                plan.bookmaker_slug,
                True,
                None,
                completed.returncode,
                "Dry-run completed; no booking code was requested.",
                stdout=stdout,
                stderr=stderr,
            )
        if plan.expects_booking_code and not booking_code:
            return BuildExecutionResult(
                plan.bookmaker_slug,
                False,
                None,
                completed.returncode,
                "Ticket builder completed but no booking code could be verified.",
                stdout=stdout,
                stderr=stderr,
            )
        return BuildExecutionResult(
            plan.bookmaker_slug,
            True,
            booking_code,
            completed.returncode,
            "Ticket builder completed successfully.",
            stdout=stdout,
            stderr=stderr,
        )

    def _extract_code(self, stdout: str) -> str | None:
        for line in reversed((stdout or "").splitlines()):
            candidate = line.strip()
            if not candidate or candidate in self._non_codes:
                continue
            if self._code.fullmatch(candidate):
                return candidate
        return None
