"""The pipeline: select the checks for an event, order them, run them in turn and merge what they decide.

The steps, in order: select, order, run and chain the rewrites, resolve conflicts, stop on a refusal, hold
the time budget, fail open on a check that raises, and merge. docs/design/architecture.md, section 3, is the
design.
"""
import hashlib
import logging
import traceback
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from ioguard.checks.base import Check, Cost
from ioguard.checks.registry import Registry
from ioguard.lib.config import Config
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Rewrite, RewriteError, Verdict, apply_one, conflict_with
from ioguard.lib.events import Event
from ioguard.lib.results import Code, Result, render
from ioguard.lib.telemetry import TelemetryEvent, trace_from

log = logging.getLogger("ioguard.pipeline")


@dataclass(frozen=True)
class Budget:
    soft_ms: int = 300       # past this, checks that start a program are skipped
    hard_ms: int = 2000      # past this, every remaining check is skipped

    @classmethod
    def from_config(cls, config: Config) -> "Budget":
        return cls(config.get("pipeline.soft_ms"), config.get("pipeline.hard_ms"))


@dataclass(frozen=True)
class Outcome:
    verdict: Verdict
    tool_input: Mapping[str, Any]            # after every rewrite
    rewrites: tuple[Rewrite, ...]
    decisions: tuple[Decision, ...]
    context: tuple[str, ...]
    user_message: str | None
    classifier_note: str | None
    output_replacement: Mapping[str, Any] | None
    skipped: tuple[str, ...]                 # check ids the budget skipped
    errors: tuple[str, ...]                  # check ids that raised


def order(checks: tuple[Check, ...]) -> tuple[Check, ...]:
    """Sort by layer, cost and id, then move each check after every check its after set names."""
    pending = sorted(checks, key=lambda check: (check.meta.layer, check.meta.cost, check.meta.id))
    present = {check.meta.id for check in checks}
    placed: list[Check] = []
    while pending:
        done = {check.meta.id for check in placed}
        ready = next(check for check in pending if (check.meta.after & present) <= done)
        pending.remove(ready)
        placed.append(ready)
    return tuple(placed)


def lines_of(decision: Decision) -> tuple[str, ...]:
    """A decision's lines for the model: its results rendered, then its context. A refusal's results render
    as the refusal's reason instead."""
    results = () if decision.verdict is Verdict.DENY else tuple(render(result) for result in decision.results)
    return results + decision.context


class Run:
    """One pipeline run over one event: the running input and everything decided so far."""

    def __init__(self, event: Event, ctx: Context) -> None:
        self.event, self.ctx = event, ctx
        self.tool_input = event.tool_input
        self.applied: list[Rewrite] = []
        self.decisions: list[Decision] = []
        self.skipped: list[str] = []
        self.errors: list[str] = []
        self.messages: list[str] = []
        self.warnings: list[Result] = []
        self.trace = trace_from(event.tool_use_id, None)

    def record(self, **fields: Any) -> None:
        event, ctx = self.event, self.ctx
        suffix = None if event.file_path is None else event.file_path.suffix or None
        ctx.telemetry.record(TelemetryEvent(
            ts=ctx.clock.now(), session=event.session_id, event=event.kind.value,
            surface=event.surface.value, platform=ctx.platform.os, project=ctx.project_name(event.cwd),
            tool=event.tool_name or None, tool_use_id=event.tool_use_id, agent_id=event.agent_id,
            prompt_id=event.prompt_id, trace=self.trace, cmd_head=event.command, file_ext=suffix, **fields))

    def result(self, code: Code, message: str) -> Result:
        return Result.of(code, message, self.event.tool_name, self.ctx.platform.os)

    def skip(self, check: Check) -> None:
        self.skipped.append(check.meta.id)
        self.record(check=check.meta.id, code=Code.BUDGET_EXCEEDED.value, severity="warning")

    def fail(self, check: Check, error: BaseException) -> None:
        """Log a check that raised, and name it to the user once per session."""
        check_id = check.meta.id
        self.errors.append(check_id)
        trace = "".join(traceback.format_exception(error))
        log.warning("GUARD_ERROR in check %s:\n%s", check_id, trace)
        self.record(check=check_id, code=Code.GUARD_ERROR.value, severity="warning",
                    error=f"{type(error).__name__} {hashlib.sha256(trace.encode()).hexdigest()[:12]}")
        if self.ctx.session.first_time(f"guard_error:{check_id}"):
            message = (f"io-guard's {check_id} check failed with {type(error).__name__}, so io-guard "
                       f"skipped it and let the call go on.")
            self.messages.append(render(self.result(Code.GUARD_ERROR, message)))

    def chain(self, check: Check, decision: Decision) -> Decision:
        """Apply the decision's rewrite to the running input, or drop it as a conflict."""
        rewrite = decision.rewrite
        if not rewrite.fields <= check.meta.writes:
            undeclared = sorted(rewrite.fields - check.meta.writes)
            raise RewriteError(f"{check.meta.id} rewrites {undeclared}, which its CheckMeta.writes lacks.")
        earlier = conflict_with(rewrite, self.applied)
        if earlier is not None:
            shared = ", ".join(sorted(rewrite.fields & earlier.fields))
            message = (f"The {rewrite.check_id} fix shares {shared} with the {earlier.check_id} fix, so "
                       f"io-guard kept the {earlier.check_id} fix only.")
            self.warnings.append(self.result(Code.REWRITE_CONFLICT, message))
            self.record(check=rewrite.check_id, code=Code.REWRITE_CONFLICT.value, severity="warning")
            return replace(decision, rewrite=None)
        self.tool_input = apply_one(rewrite, self.tool_input)
        self.applied.append(rewrite)
        return decision

    def step(self, check: Check, budget: Budget, started: float) -> bool:
        """Run one check. False when a refusal ends the run."""
        elapsed_ms = (self.ctx.clock.monotonic() - started) * 1000
        expensive = check.meta.cost >= Cost.EXPENSIVE
        if elapsed_ms >= budget.hard_ms or (elapsed_ms >= budget.soft_ms and expensive):
            self.skip(check)
            return True
        current = self.event if self.tool_input is self.event.tool_input else \
            self.event.with_tool_input(self.tool_input)
        before = self.ctx.clock.monotonic()
        try:
            decision = check.run(current, self.ctx)
            if decision.rewrite is not None:
                decision = self.chain(check, decision)
        except Exception as error:
            self.fail(check, error)
            return True
        decision = replace(decision, latency_ms=(self.ctx.clock.monotonic() - before) * 1000)
        self.decisions.append(decision)
        if decision.verdict > Verdict.OBSERVE:
            first = decision.results[0] if decision.results else None
            self.record(check=check.meta.id, latency_ms=decision.latency_ms,
                        code=None if first is None else first.code.value,
                        severity=None if first is None else first.severity.value,
                        fixed=() if decision.rewrite is None else (decision.rewrite.code.value,))
        return decision.verdict is not Verdict.DENY

    def outcome(self) -> Outcome:
        decisions = self.decisions
        notes = [decision.classifier_note for decision in decisions if decision.classifier_note]
        messages = [decision.user_message for decision in decisions if decision.user_message] + self.messages
        return Outcome(
            verdict=max((decision.verdict for decision in decisions), default=Verdict.OBSERVE),
            tool_input=self.tool_input,
            rewrites=tuple(self.applied),
            decisions=tuple(decisions),
            context=tuple(line for decision in decisions for line in lines_of(decision))
            + tuple(render(warning) for warning in self.warnings),
            user_message="\n".join(messages) or None,
            classifier_note="\n".join(notes) or None,
            output_replacement=next((decision.output_replacement for decision in decisions
                                     if decision.output_replacement is not None), None),
            skipped=tuple(self.skipped),
            errors=tuple(self.errors),
        )


class Pipeline:
    def __init__(self, registry: Registry, budget: Budget | None = None) -> None:
        self.registry = registry
        self.budget = budget

    def order(self, checks: tuple[Check, ...]) -> tuple[Check, ...]:
        return order(checks)

    def run(self, event: Event, ctx: Context) -> Outcome:
        budget = self.budget or Budget.from_config(ctx.config)
        run = Run(event, ctx)
        started = ctx.clock.monotonic()
        for check in self.order(self.registry.select(event, ctx)):
            if not run.step(check, budget, started):
                break
        outcome = run.outcome()
        run.record(latency_ms=(ctx.clock.monotonic() - started) * 1000, skipped=outcome.skipped,
                   fixed=tuple(rewrite.code.value for rewrite in outcome.rewrites))
        return outcome
