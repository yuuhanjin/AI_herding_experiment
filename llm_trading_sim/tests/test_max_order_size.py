"""max_order_size is shown to LLM agents and enforced by clipping oversized orders."""
from types import SimpleNamespace

from agents.LLMs.services.formatting_services import AgentContext, MarketStateFormatter
from agents.agent_manager.services.agent_decision_service import AgentDecisionService


def context(cap):
    return AgentContext(agent_id="0", cash=100.0, shares=10, available_cash=100.0,
                        available_shares=10, outstanding_orders={"buy": [], "sell": []},
                        max_order_size=cap)


def test_prompt_shows_cap_only_when_set():
    assert "Maximum Order Size: 1000 shares per order" in MarketStateFormatter._format_position_info(context(1000))
    assert "Maximum Order Size" not in MarketStateFormatter._format_position_info(context(None))


class Repo:
    def __init__(self):
        self.orders = []

    def create_order(self, order):
        self.orders.append(order)


class Log:
    def __init__(self):
        self.warnings = []

    def warning(self, msg):
        self.warnings.append(msg)

    def error(self, msg):
        raise AssertionError(msg)


def service(cap):
    agent = SimpleNamespace(max_order_size=cap, positions={"DEFAULT_STOCK": 10**6})
    agents = SimpleNamespace(get_agent=lambda _id: agent)
    return AgentDecisionService(agents, Repo(), None, None, Log(), SimpleNamespace(round_number=1))


def order(qty, side="Sell"):
    return {"decision": side, "quantity": qty, "order_type": "Limit", "price_limit": 50.0}


def test_oversized_order_is_clipped_and_logged():
    svc = service(1000)
    assert svc.create_order(order(100_000), "4").quantity == 1000
    assert "clipped from 100000 to 1000" in svc.decisions_logger.warnings[0]


def test_orders_within_cap_or_uncapped_are_unchanged():
    assert service(1000).create_order(order(1000, "Buy"), "1").quantity == 1000
    assert service(None).create_order(order(5000, "Buy"), "1").quantity == 5000
