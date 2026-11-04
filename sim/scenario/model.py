"""g.scenario: the episode's scheduled events, god block and scenario block (docs/logic/events.md "Ours")."""
import random


class Scenario:
    def __init__(self, source, info, gods, events, seed):
        self.source = source          # data/scenario/<map>.json's "source" (the .pak)
        self.info = info              # the scenario block: start_year, funds, raw
        self.gods = gods              # the god block (g_scenario_gods 0x00FFA450)
        self.events = events          # g_events: list of record dicts, index = ev["id"]
        self.rng = random.Random(seed * 7919 + 1)    # ours: the scenario's own stream (events.md "Ours")
        self.log = []                 # (month index, text): the engine's own log (`scenario log`)
        self.noted = set()            # record ids already logged as "no handler"
