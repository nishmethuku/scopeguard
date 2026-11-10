from .baselines import AllowAll, BlockAll, ClassifierGuard, NoGuard, PromptOnly
from .base import Guard, GuardContext, HistEntry
from .judge import HeuristicJudge, LLMJudge
from .rules import RuleGuard
from .scopeguard import ScopeGuard

GUARD_IDS = ["none", "prompt_only", "classifier", "l1", "l2", "l1+l2", "l1+l2+ask", "block_all", "allow_all"]


def make_guard(name: str, judge_provider=None, **kw):
    judge = LLMJudge(judge_provider) if judge_provider is not None else None
    if name in ("none",):
        return NoGuard()
    if name == "prompt_only":
        return PromptOnly()
    if name == "classifier":
        return ClassifierGuard(**kw)
    if name == "l1":
        return ScopeGuard(layer1=True, layer2=False, ask=False)
    if name == "l2":
        return ScopeGuard(layer1=False, layer2=True, ask=False, judge=judge)
    if name == "l1+l2":
        return ScopeGuard(layer1=True, layer2=True, ask=False, judge=judge)
    if name == "l1+l2+ask":
        return ScopeGuard(layer1=True, layer2=True, ask=True, judge=judge)
    if name == "block_all":
        return BlockAll()
    if name == "allow_all":
        return AllowAll()
    raise ValueError(f"unknown guard '{name}'")
