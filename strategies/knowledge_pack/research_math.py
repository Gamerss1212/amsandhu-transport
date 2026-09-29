"""Offline educational arithmetic. No network, wallets, signing, or trading.

Constant-product examples assume an input fee retained by the pool, ordinary
transfers, no virtual reserves, and no concurrent state changes. Decimal math
does not reproduce protocol-specific integer rounding or concentrated pools.
"""
from decimal import Decimal, localcontext, ROUND_FLOOR


def dec(value):
    """Accept exact decimal inputs, rejecting floats, booleans, and nonfinite values."""
    if isinstance(value, (float, bool)) or not isinstance(value, (str, int, Decimal)):
        raise TypeError('Use a decimal string, integer, or Decimal.')
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError('Value must be finite.')
    return result


def nonnegative(value, name):
    result = dec(value)
    if result < 0:
        raise ValueError(name + ' must be nonnegative.')
    return result


def positive(value, name):
    result = dec(value)
    if result <= 0:
        raise ValueError(name + ' must be positive.')
    return result


def fee_fraction(fee_bps):
    fee = nonnegative(fee_bps, 'fee_bps')
    if fee >= 10000:
        raise ValueError('Fee must be below 10000 basis points.')
    return fee / Decimal(10000)


def cp_swap_exact_input(reserve_in, reserve_out, amount_in, fee_bps):
    """Continuous-unit constant-product example, with input fee retained in reserve."""
    with localcontext() as ctx:
        ctx.prec = 50
        x = positive(reserve_in, 'reserve_in')
        y = positive(reserve_out, 'reserve_out')
        q = nonnegative(amount_in, 'amount_in')
        f = fee_fraction(fee_bps)
        fee = q * f
        effective = q - fee
        out = y * effective / (x + effective)
        return {
            'amount_in': q, 'amount_out': out, 'fee_in_input_units': fee,
            'reserve_in_after': x + q, 'reserve_out_after': y - out,
        }


def cp_immediate_round_trip(quote_reserve, token_reserve, quote_input, fee_bps):
    """Buy tokens, then sell the received amount against the updated pool state."""
    with localcontext() as ctx:
        ctx.prec = 50
        start = positive(quote_input, 'quote_input')
        buy = cp_swap_exact_input(quote_reserve, token_reserve, start, fee_bps)
        sell = cp_swap_exact_input(buy['reserve_out_after'], buy['reserve_in_after'],
                                   buy['amount_out'], fee_bps)
        end = sell['amount_out']
        return {'quote_input': start, 'tokens_received': buy['amount_out'],
                'quote_returned': end, 'quote_loss': start - end,
                'retention_fraction': end / start,
                'buy': buy, 'sell': sell}


def multiplicative_break_even_return(entry_fee_bps, exit_fee_bps):
    """Required gross return when each leg retains (1-fee) of its proceeds.

    This deliberately omits fixed fees, impact, financing, taxes, and failed
    attempts. Do not add these fees again if already included in route outputs.
    """
    with localcontext() as ctx:
        ctx.prec = 50
        keep = (1 - fee_fraction(entry_fee_bps)) * (1 - fee_fraction(exit_fee_bps))
        return 1 / keep - 1


def expectancy_r(win_probability, mean_win_r, mean_loss_r, cost_r):
    """Hypothetical expectancy; supplied probabilities are not estimated here."""
    p = nonnegative(win_probability, 'win_probability')
    if p > 1:
        raise ValueError('Probability exceeds one.')
    w = nonnegative(mean_win_r, 'mean_win_r')
    loss = nonnegative(mean_loss_r, 'mean_loss_r')
    cost = nonnegative(cost_r, 'cost_r')
    return p * w - (1 - p) * loss - cost


def capped_spot_long_quantity(equity, planned_loss_fraction, entry, stop,
                             adverse_cost_per_unit, total_loss_budget,
                             stressed_exit_quantity, quantity_step='1',
                             acquisition_cost_per_unit='0'):
    """Illustrative long spot sizing with independent stop, total-loss, and depth caps.

    The total-loss cap covers acquisition notional and supplied per-unit entry
    costs. Reserve fixed transaction/custody costs outside this function. A stop
    fill is not guaranteed. No derivatives, leverage, or wallet-security model.
    """
    with localcontext() as ctx:
        ctx.prec = 50
        capital = positive(equity, 'equity')
        fraction = positive(planned_loss_fraction, 'planned_loss_fraction')
        if fraction > 1:
            raise ValueError('Loss fraction exceeds one.')
        price = positive(entry, 'entry')
        stop_price = nonnegative(stop, 'stop')
        if stop_price >= price:
            raise ValueError('Long stop must be below entry.')
        cost = nonnegative(adverse_cost_per_unit, 'adverse_cost_per_unit')
        acquisition = nonnegative(acquisition_cost_per_unit, 'acquisition_cost_per_unit')
        catastrophe = nonnegative(total_loss_budget, 'total_loss_budget')
        liquidity = nonnegative(stressed_exit_quantity, 'stressed_exit_quantity')
        step = positive(quantity_step, 'quantity_step')
        loss_per_unit = price - stop_price + cost
        risk_cap = capital * fraction / loss_per_unit
        total_loss_cap = catastrophe / (price + acquisition)
        cash_cap = capital / (price + acquisition)
        raw = min(risk_cap, total_loss_cap, liquidity, cash_cap)
        quantity = (raw / step).to_integral_value(rounding=ROUND_FLOOR) * step
        return {'quantity': quantity, 'planned_loss_cap_quantity': risk_cap,
                'total_loss_cap_quantity': total_loss_cap,
                'stressed_exit_cap_quantity': liquidity, 'cash_cap_quantity': cash_cap,
                'acquisition_notional': quantity * (price + acquisition),
                'modeled_stop_loss': quantity * loss_per_unit}


def priority_fee_lamports(compute_unit_limit, price_micro_lamports):
    """Compute-Budget-style fee only; not applicable to all transaction formats."""
    for v in (compute_unit_limit, price_micro_lamports):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError('Compute values must be nonnegative integers.')
    return (compute_unit_limit * price_micro_lamports + 999999) // 1000000


def raw_to_display(raw_amount, decimals):
    """Exact base-unit conversion. Caller must independently verify asset decimals."""
    if isinstance(raw_amount, bool) or not isinstance(raw_amount, (int, str)):
        raise TypeError('Raw amount must be an integer or decimal integer string.')
    if isinstance(raw_amount, str) and (not raw_amount or not raw_amount.isascii() or not raw_amount.isdigit()):
        raise ValueError('Raw amount must contain only ASCII digits.')
    raw = int(raw_amount)
    if raw < 0:
        raise ValueError('Raw amount must be nonnegative.')
    if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 255:
        raise ValueError('Decimals must be a verified integer from 0 through 255.')
    # Construct from digits and exponent to avoid context precision truncation.
    return Decimal((0, tuple(int(c) for c in str(raw)), -decimals))


def holder_hhi(shares):
    """HHI for a complete, normalized economic ownership distribution."""
    values = [nonnegative(x, 'share') for x in shares]
    if not values or sum(values) != Decimal(1):
        raise ValueError('Complete shares must sum exactly to one.')
    return sum(x * x for x in values)


if __name__ == '__main__':
    import json
    example = {
        'status': 'synthetic_arithmetic_only_not_a_market_backtest',
        'large_exit': cp_swap_exact_input('1000000', '10000', '1000000', '30'),
        'round_trip': cp_immediate_round_trip('10000', '1000000', '1000', '30'),
        'two_percent_each_leg_break_even': multiplicative_break_even_return('200', '200'),
        'hypothetical_expectancy_r': expectancy_r('0.45', '1.8', '1', '0.30'),
        'capped_quantity': capped_spot_long_quantity('10000', '0.005', '0.01', '0.008', '0', '100', '50000'),
        'priority_fee_example_lamports': priority_fee_lamports(200000, 1001),
    }
    print(json.dumps(example, default=str, indent=2))
