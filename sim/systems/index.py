"""Buildings by kind (the original keeps typed lists too, e.g. its house list built once a day,
docs/logic/time-core.md §9): of(g, kind, ...) is the list of those buildings in id order, cached per
occ_version (every build, demolish and stall change bumps it). Treat the lists as read-only."""


def of(g, *kinds):
    c = getattr(g, "_kinds", None)
    v = services.occ_version(g)
    if c is None or c[0] != v:
        c = g._kinds = (v, {})
    out = c[1].get(kinds)
    if out is None:
        ks = set(kinds)
        out = c[1][kinds] = [b for b in g.buildings.values() if b.kind in ks]
    return out


def keyed(g, key):
    """Buildings with catalog key `key`, id order (same cache)."""
    c = getattr(g, "_kinds", None)
    v = services.occ_version(g)
    if c is None or c[0] != v:
        c = g._kinds = (v, {})
    out = c[1].get(("key", key))
    if out is None:
        out = c[1][("key", key)] = [b for b in g.buildings.values() if b.key == key]
    return out


from . import services  # noqa: E402  (circular: imported last)
