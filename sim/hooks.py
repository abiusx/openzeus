"""Named hooks: a module outside the core (the campaign module, sim/campaign; later packs) attaches a function to the
game by name, so the core calls it without importing it (docs/campaign-format.md "The campaign module").

    attach(g, "day", "sim.campaign.goals:day")    stored in the save as plain strings (g.hooks)
    call(g, "day")                                systems.run_day, at the end of every day

Absent in open play (no g.hooks): nothing is called and the state is unchanged.
"""
import importlib

_FN = {}


def attach(g, when, ref):
    hs = g.sd("hooks", {})
    lst = hs.setdefault(when, [])
    if ref not in lst:
        lst.append(ref)


def detach(g, when, ref):
    hs = g.__dict__.get("hooks") or {}
    if ref in hs.get(when, ()):
        hs[when].remove(ref)


def call(g, when):
    for ref in g.hooks.get(when, ()):
        fn = _FN.get(ref)
        if fn is None:
            mod, _, name = ref.partition(":")
            fn = _FN[ref] = getattr(importlib.import_module(mod), name)
        fn(g)
