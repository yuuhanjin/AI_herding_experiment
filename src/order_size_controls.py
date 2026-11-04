"""Explicit replication intervention: legacy, prompt-only, or enforced per-order cap.

Never silently clip orders. Forced margin liquidations are exempt to avoid
preventing risk reduction; this is not a per-round or total-position limit.
"""
MODES = ('legacy', 'prompt', 'enforced')

def validate_policy(cap, mode):
    if type(cap) is not int or cap < 1:
        raise ValueError('max_order_size must be a positive integer')
    if mode not in MODES:
        raise ValueError('order_size_mode must be legacy, prompt, or enforced')

def prompt_instruction(cap, mode):
    validate_policy(cap, mode)
    if mode == 'legacy':
        return ''
    return (f"\n\nORDER SIZE LIMIT: max_order_size = {cap} shares per individual order. "
            f"For every Buy or Sell, market or limit order, quantity must be an integer from 1 to {cap}. "
            "This is a per-order limit, not a total position or per-round volume limit. "
            "To Hold or Cancel, return an empty orders list.")

def rejection_reason(order, agent):
    if getattr(agent, 'order_size_mode', 'legacy') != 'enforced' or getattr(order, 'is_margin_call', False):
        return None
    cap = agent.max_order_size
    validate_policy(cap, 'enforced')
    if order.quantity > cap:
        return f'MAX_ORDER_SIZE_EXCEEDED: requested {order.quantity}, cap {cap} shares per order'
    return None
