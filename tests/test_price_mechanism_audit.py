"""Regression checks for the price metrics used in the paper audit."""

from types import SimpleNamespace

import pytest

from market.data_recorder import DataRecorder
from market.engine.services.trade_processing_service import TradeProcessingService
from market.orders.handlers.services.conversion_service import OrderConversionService


def test_unfilled_sell_can_lower_recorded_price_without_a_trade():
    converter = object.__new__(OrderConversionService)
    converter._order_book = SimpleNamespace(get_best_bid=lambda: None)
    ask = converter._calculate_aggressive_price(SimpleNamespace(side="sell"), 56.0)
    assert ask == pytest.approx(50.4)

    pricing = object.__new__(TradeProcessingService)
    pricing.order_book = SimpleNamespace(calculate_price_from_book=lambda: ask)
    assert pricing.calculate_new_price([], 56.0) == pytest.approx(50.4)


def test_market_data_labels_pre_and_post_match_quotes_separately():
    recorder = object.__new__(DataRecorder)
    recorder.market_data = []
    recorder.context = SimpleNamespace(
        current_price=50.4,
        fundamental_price=28.0,
        public_info={
            "order_book_state": {
                "best_bid": None,
                "best_ask": 50.4,
                "midpoint": None,
            },
            "last_trade": {"price": 56.0, "round": 0},
            "trade_history": [],
            "short_interest": 0,
        },
    )
    pre_match = {"best_bid": None, "best_ask": None, "market_depth": {}}

    recorder._record_market_data(0, pre_match, [], 0, "test")

    row = recorder.market_data[0]
    assert row["price"] == 50.4
    assert row["num_trades"] == 0
    assert row["best_ask"] is None  # Legacy column is pre-match.
    assert row["pre_match_best_ask"] is None
    assert row["post_match_best_ask"] == 50.4
    assert row["post_match_midpoint"] is None  # One-sided book.
    assert row["last_executed_trade_price"] is None
    assert row["last_executed_trade_round"] is None

    recorder.context.public_info["trade_history"].append({"price": 49.0, "round": 0})
    recorder._record_market_data(1, pre_match, [], 0, "test")
    assert recorder.market_data[1]["last_executed_trade_price"] == 49.0
    assert recorder.market_data[1]["last_executed_trade_round"] == 1
