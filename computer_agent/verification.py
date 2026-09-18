"""Independent postcondition verification (M2).

See `docs/DECISIONS.md` D-018, `docs/ARCHITECTURE.md` "Verification
contract", `docs/BUILD_SPEC.md` "Gate M2".

Execution success is not task success. Nothing in this module accepts an
executor/adapter return value, a model assertion, or a fixture's claimed
outcome: `judge()`/`verify()` see only a `VerificationSpec` and observed
state (a JSON-like value captured by an observation channel separate from
dispatch). Predicates are three-valued (TRUE/FALSE/UNKNOWN, Kleene logic);
any UNKNOWN that could matter yields `INCONCLUSIVE`, never success.

Observed state is plain data (dicts/lists/scalars). An observer marks data
it could not read reliably with an `Indeterminate` value -- for the whole
observation (`UNAVAILABLE`) or any subtree (e.g. a field reported as
"syncing..." or by conflicting sources). A missing key is *determinate*
absence; an `Indeterminate` is "don't know".
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Mapping, Sequence


class Tri(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class VerificationOutcome(str, Enum):
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    VERIFIED_FAILURE = "VERIFIED_FAILURE"
    INCONCLUSIVE = "INCONCLUSIVE"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    UNEXPECTED_SIDE_EFFECT = "UNEXPECTED_SIDE_EFFECT"


@dataclass(frozen=True, eq=False)
class Indeterminate:
    """Observed value that cannot be trusted. Never equal to anything, itself included."""

    reason: str

    def __eq__(self, other: object) -> bool:
        return False

    __hash__ = object.__hash__


UNAVAILABLE = Indeterminate("observation unavailable")

Path = tuple[Any, ...]
_MISSING = object()


def _get(state: Any, path: Path) -> Any:
    cur = state
    for key in path:
        if isinstance(cur, Indeterminate):
            return cur
        if isinstance(cur, Mapping):
            if key not in cur:
                return _MISSING
            cur = cur[key]
        elif isinstance(cur, (list, tuple)) and isinstance(key, int) and -len(cur) <= key < len(cur):
            cur = cur[key]
        else:
            return _MISSING
    return cur


def _indeterminate(value: Any) -> bool:
    if isinstance(value, Indeterminate):
        return True
    if isinstance(value, Mapping):
        return any(_indeterminate(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_indeterminate(v) for v in value)
    return False


def _tri(ok: bool) -> Tri:
    return Tri.TRUE if ok else Tri.FALSE


@dataclass(frozen=True)
class PredicateResult:
    predicate: str
    value: Tri
    detail: str = ""


class Predicate:
    """Base: subclasses implement `_eval(before, after) -> Tri` over determinate reads."""


    def evaluate(self, before: Any, after: Any) -> PredicateResult:
        try:
            value = self._eval(before, after)
        except _Unknown as exc:
            return PredicateResult(repr(self), Tri.UNKNOWN, str(exc))
        return PredicateResult(repr(self), value)

    def _eval(self, before: Any, after: Any) -> Tri:  # pragma: no cover - abstract
        raise NotImplementedError

    @staticmethod
    def _read(state: Any, path: Path, which: str) -> Any:
        value = _get(state, path)
        if _indeterminate(value):
            raise _Unknown(f"{which} state at {path!r} is indeterminate")
        return value


class _Unknown(Exception):
    pass


def _count(collection: Any, where: Mapping[str, Any] | None) -> int:
    if collection is _MISSING:
        return 0
    items = collection.values() if isinstance(collection, Mapping) else collection
    if not isinstance(items, (list, tuple)) and not isinstance(collection, Mapping):
        raise _Unknown(f"count target is not a collection: {type(collection).__name__}")
    if where is None:
        return len(list(items))
    return sum(1 for it in items if isinstance(it, Mapping) and all(it.get(k, _MISSING) == v for k, v in where.items()))


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


# -- primitives -----------------------------------------------------------------


@dataclass(frozen=True)
class Eq(Predicate):
    path: Path
    value: Any

    def _eval(self, before, after):
        return _tri(self._read(after, self.path, "after") == self.value)


@dataclass(frozen=True)
class Ne(Predicate):
    path: Path
    value: Any

    def _eval(self, before, after):
        return _tri(self._read(after, self.path, "after") != self.value)


@dataclass(frozen=True)
class Exists(Predicate):
    path: Path

    def _eval(self, before, after):
        return _tri(self._read(after, self.path, "after") is not _MISSING)


@dataclass(frozen=True)
class Absent(Predicate):
    path: Path

    def _eval(self, before, after):
        return _tri(self._read(after, self.path, "after") is _MISSING)


@dataclass(frozen=True)
class Contains(Predicate):
    """Collection at `path` contains `member` (list element, mapping key, or substring)."""

    path: Path
    member: Any

    def _eval(self, before, after):
        coll = self._read(after, self.path, "after")
        if isinstance(coll, (list, tuple, Mapping, str)):
            return _tri(self.member in coll)
        return Tri.FALSE


@dataclass(frozen=True)
class OneOf(Predicate):
    """Value at `path` is a member of `options`."""

    path: Path
    options: tuple[Any, ...]

    def _eval(self, before, after):
        return _tri(self._read(after, self.path, "after") in self.options)


@dataclass(frozen=True)
class InRange(Predicate):
    path: Path
    lo: float
    hi: float

    def _eval(self, before, after):
        n = _number(self._read(after, self.path, "after"))
        return _tri(n is not None and self.lo <= n <= self.hi)


@dataclass(frozen=True)
class Count(Predicate):
    """lo <= number of items at `path` (optionally only items whose fields match `where`) <= hi."""

    path: Path
    lo: int
    hi: int
    where: Mapping[str, Any] | None = None

    def _eval(self, before, after):
        n = _count(self._read(after, self.path, "after"), self.where)
        return _tri(self.lo <= n <= self.hi)


@dataclass(frozen=True)
class CountDelta(Predicate):
    """lo <= count(after) - count(before) <= hi."""

    path: Path
    lo: int
    hi: int
    where: Mapping[str, Any] | None = None

    def _eval(self, before, after):
        b = _count(self._read(before, self.path, "before"), self.where)
        a = _count(self._read(after, self.path, "after"), self.where)
        return _tri(self.lo <= a - b <= self.hi)


@dataclass(frozen=True)
class Delta(Predicate):
    """lo <= after[path] - before[path] <= hi for numeric values."""

    path: Path
    lo: float
    hi: float

    def _eval(self, before, after):
        b = _number(self._read(before, self.path, "before"))
        a = _number(self._read(after, self.path, "after"))
        return _tri(a is not None and b is not None and self.lo <= a - b <= self.hi)


@dataclass(frozen=True)
class Transition(Predicate):
    """before[path] == from_value and after[path] == to_value."""

    path: Path
    from_value: Any
    to_value: Any

    def _eval(self, before, after):
        b = self._read(before, self.path, "before")
        a = self._read(after, self.path, "after")
        return _tri(b == self.from_value and a == self.to_value)


@dataclass(frozen=True)
class Unchanged(Predicate):
    """Invariant: the value (or subtree) at `path` is identical before and after."""

    path: Path

    def _eval(self, before, after):
        return _tri(self._read(before, self.path, "before") == self._read(after, self.path, "after"))


@dataclass(frozen=True)
class UnchangedExcept(Predicate):
    """Invariant: the mapping at `path` is identical before/after except for keys in `allowed`.

    Added or removed keys outside `allowed` count as changes -- this is what
    catches wrong-object, duplicate-record and collateral mutations.
    """

    path: Path
    allowed: frozenset[Any]

    def _eval(self, before, after):
        b = self._read(before, self.path, "before")
        a = self._read(after, self.path, "after")
        if not isinstance(b, Mapping) or not isinstance(a, Mapping):
            return _tri(b == a)
        keys = (set(b) | set(a)) - set(self.allowed)
        return _tri(all(b.get(k, _MISSING) == a.get(k, _MISSING) for k in keys))


@dataclass(frozen=True)
class And(Predicate):
    parts: tuple[Predicate, ...]

    def __post_init__(self):
        if not self.parts:
            raise ValueError("And() needs at least one predicate")

    def _eval(self, before, after):
        values = [p.evaluate(before, after).value for p in self.parts]
        if Tri.FALSE in values:
            return Tri.FALSE
        if Tri.UNKNOWN in values:
            raise _Unknown("And: a conjunct is UNKNOWN")
        return Tri.TRUE


@dataclass(frozen=True)
class Or(Predicate):
    parts: tuple[Predicate, ...]

    def __post_init__(self):
        if not self.parts:
            raise ValueError("Or() needs at least one predicate")

    def _eval(self, before, after):
        values = [p.evaluate(before, after).value for p in self.parts]
        if Tri.TRUE in values:
            return Tri.TRUE
        if Tri.UNKNOWN in values:
            raise _Unknown("Or: a disjunct is UNKNOWN")
        return Tri.FALSE


@dataclass(frozen=True)
class Check(Predicate):
    """Bounded domain callback, for postconditions the primitives cannot express.

    `fn(before, after)` receives deep copies of observed state only and must
    be deterministic and side-effect free. Returning anything other than a
    bool -- or raising -- is UNKNOWN, never TRUE.
    """

    name: str
    fn: Callable[[Any, Any], Any] = field(compare=False)

    def __repr__(self) -> str:
        return f"Check({self.name!r})"

    def _eval(self, before, after):
        if _indeterminate(before) or _indeterminate(after):
            raise _Unknown(f"{self.name}: indeterminate input")
        try:
            result = self.fn(copy.deepcopy(before), copy.deepcopy(after))
        except Exception as exc:  # a crashing callback is not evidence
            raise _Unknown(f"{self.name} raised {type(exc).__name__}") from None
        if not isinstance(result, bool):
            raise _Unknown(f"{self.name} returned non-bool {result!r}")
        return _tri(result)


# -- spec / judgement ---------------------------------------------------------------


@dataclass(frozen=True)
class VerificationSpec:
    """`success`: the required effects (each one a separately judged sub-effect).
    `invariants`: prohibited-effect / must-remain-true checks."""

    success: tuple[Predicate, ...]
    invariants: tuple[Predicate, ...] = ()

    def __post_init__(self):
        if not self.success:
            raise ValueError("a VerificationSpec with no success predicate would verify vacuously")


@dataclass(frozen=True)
class VerificationResult:
    outcome: VerificationOutcome
    reason: str
    success_results: tuple[PredicateResult, ...] = ()
    invariant_results: tuple[PredicateResult, ...] = ()
    observations_used: int = 0
    history: tuple[VerificationOutcome, ...] = ()


def evaluate(spec: VerificationSpec, before: Any, after: Any) -> VerificationResult:
    """Judge one (before, after) pair. Precedence: side effect > unknown > success/failure/partial."""
    succ = tuple(p.evaluate(before, after) for p in spec.success)
    inv = tuple(p.evaluate(before, after) for p in spec.invariants)

    def result(outcome: VerificationOutcome, reason: str) -> VerificationResult:
        return VerificationResult(outcome, reason, succ, inv, 1, (outcome,))

    if any(r.value == Tri.FALSE for r in inv):
        broken = [r.predicate for r in inv if r.value == Tri.FALSE]
        return result(VerificationOutcome.UNEXPECTED_SIDE_EFFECT, f"invariant violated: {broken}")
    if any(r.value == Tri.UNKNOWN for r in succ + inv):
        unknown = [r.detail for r in succ + inv if r.value == Tri.UNKNOWN]
        return result(VerificationOutcome.INCONCLUSIVE, f"evidence indeterminate: {unknown}")
    held = sum(r.value == Tri.TRUE for r in succ)
    if held == len(succ):
        return result(VerificationOutcome.VERIFIED_SUCCESS, "all required effects observed; invariants hold")
    if held == 0:
        return result(VerificationOutcome.VERIFIED_FAILURE, "no required effect observed")
    return result(VerificationOutcome.PARTIAL_SUCCESS, f"{held}/{len(succ)} required effects observed")


def judge(spec: VerificationSpec, before: Any, observations: Sequence[Any]) -> VerificationResult:
    """Deterministic verdict over an ordered sequence of post-action observations.

    Success must be *confirmed*: two consecutive observations that both
    evaluate to VERIFIED_SUCCESS with identical observed state. A success
    seen once and then contradicted, or seen only on the last observation,
    is not success. An invariant violation is terminal immediately. Otherwise
    the verdict is the last observation's evaluation (this lets a delayed
    effect arrive without re-executing anything).
    """
    if not observations:
        return VerificationResult(VerificationOutcome.INCONCLUSIVE, "no post-action observation")
    history: list[VerificationOutcome] = []
    prev: tuple[Any, VerificationResult] | None = None
    last: VerificationResult | None = None
    for i, after in enumerate(observations, start=1):
        last = evaluate(spec, before, after)
        history.append(last.outcome)
        done = last.outcome == VerificationOutcome.UNEXPECTED_SIDE_EFFECT or (
            last.outcome == VerificationOutcome.VERIFIED_SUCCESS
            and prev is not None
            and prev[1].outcome == VerificationOutcome.VERIFIED_SUCCESS
            and prev[0] == after
        )
        if done:
            reason = last.reason + (" (confirmed by consecutive identical observations)"
                                    if last.outcome == VerificationOutcome.VERIFIED_SUCCESS else "")
            return replace(last, reason=reason, observations_used=i, history=tuple(history))
        prev = (after, last)
    assert last is not None
    if last.outcome == VerificationOutcome.VERIFIED_SUCCESS:
        return replace(last, outcome=VerificationOutcome.INCONCLUSIVE,
                     reason="success observed but not confirmed by a second identical observation",
                     observations_used=len(observations), history=tuple(history))
    return replace(last, observations_used=len(observations), history=tuple(history))


def is_terminal(result: VerificationResult) -> bool:
    """True when more observations cannot change `judge`'s verdict."""
    return result.outcome == VerificationOutcome.UNEXPECTED_SIDE_EFFECT or (
        result.outcome == VerificationOutcome.VERIFIED_SUCCESS
    )


def verify(
    spec: VerificationSpec,
    before: Any,
    observe: Callable[[], Any],
    *,
    max_observations: int = 4,
) -> tuple[VerificationResult, list[Any]]:
    """Poll the independent observation channel (bounded) and `judge` the sequence.

    Returns the verdict and the observations it was based on, so a caller
    can persist them and later re-derive the identical verdict with
    `judge()` (crash recovery). Pacing between polls is the observer's job.
    Deliberately has no parameter through which an executor's claimed
    result could arrive.
    """
    observations: list[Any] = []
    result = judge(spec, before, observations)
    for _ in range(max_observations):
        observations.append(observe())
        result = judge(spec, before, observations)
        if is_terminal(result):
            break
    return result, observations
