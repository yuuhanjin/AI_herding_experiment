"""Dedicated random stream for dividend draws.

By default dividends draw from the module-level `random` generator, which is
shared with agent and order shuffling. Shuffling consumes a number of draws
that depends on how many orders the LLM submits, so two runs with the same
RANDOM_SEED can realize different dividend paths.

Setting DIVIDEND_SEED gives dividends (idiosyncratic draws and factor shocks)
their own generator, so the dividend path depends only on DIVIDEND_SEED.
Leaving it unset keeps the original shared-stream behaviour, so existing
seeded runs reproduce unchanged.
"""
import random

_dividend_rng = random


def set_dividend_seed(seed):
    """Use a dedicated generator for dividends, or the shared one if seed is None."""
    global _dividend_rng
    _dividend_rng = random.Random(seed) if seed is not None else random


def dividend_rng():
    return _dividend_rng
