"""DIVIDEND_SEED isolates dividend draws from the shared random stream.

Without it, agent and order shuffling consume draws from the same generator as
dividends, so the number of orders an LLM submits changes the dividend path.
"""
import random

import pytest

from market.state.services.dividend_service import DividendCalculator
from market.state.services.shock_service import generate_dividend_shocks
from services.random_streams import set_dividend_seed

DIVIDEND_PARAMS = {
    "base_dividend": 1.4,
    "dividend_variation": 1.0,
    "dividend_probability": 0.5,
}
SHOCKS = {"systematic_volatility": 0.2, "styles": {"growth": {"volatility": 0.1}}}


def dividend_path(rounds, shuffles_per_round):
    """Draw a dividend path while other code consumes the shared stream."""
    calc = DividendCalculator(DIVIDEND_PARAMS)
    path = []
    for n in shuffles_per_round[:rounds]:
        random.shuffle(list(range(n)))  # order processing between dividends
        shocks = generate_dividend_shocks(SHOCKS, enabled=True)
        realization = calc.calculate_dividend(
            systematic_shock=shocks["systematic"], style_shock=shocks["styles"]["growth"]
        )
        path.append(realization.total_dividend)
    return path


@pytest.fixture(autouse=True)
def reset_stream():
    yield
    set_dividend_seed(None)


def test_dividend_seed_gives_same_path_despite_different_order_flow():
    random.seed(42)
    set_dividend_seed(7)
    few_orders = dividend_path(15, [3] * 15)

    random.seed(42)
    set_dividend_seed(7)
    many_orders = dividend_path(15, [3, 9, 1, 12, 5] * 3)

    assert few_orders == many_orders


def test_different_dividend_seeds_give_different_paths():
    set_dividend_seed(1)
    path_1 = dividend_path(15, [3] * 15)
    set_dividend_seed(2)
    path_2 = dividend_path(15, [3] * 15)

    assert path_1 != path_2


def test_unset_dividend_seed_keeps_shared_stream_behaviour():
    random.seed(42)
    few_orders = dividend_path(15, [3] * 15)
    random.seed(42)
    many_orders = dividend_path(15, [3, 9, 1, 12, 5] * 3)

    # Original behaviour: order flow shifts the shared stream, so paths diverge.
    assert few_orders != many_orders
