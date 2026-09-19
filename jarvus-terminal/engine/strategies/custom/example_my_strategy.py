"""A worked example. Copy this file, rename it, and write your own.

Anything in this folder is imported on startup, so a new .py here becomes a live
strategy with no other wiring. Rules of the road:

  * Return a Signal when your pattern is present, and None when it is not. None is
    the normal answer; a strategy that fires on most bars is not a strategy.
  * Use ctx.ind(name, **params) for indicators. It caches, so asking for the same
    EMA from ten strategies costs one computation.
  * Do not size the position or decide affordability. Those happen once, centrally.
  * `strength` is 0..1 and means "how textbook is this instance", not a probability.
    What the strategy is actually worth gets measured by the backtester.

Every indicator in engine/indicators.py CATALOG is available by name: supertrend,
ichimoku, adx, keltner, stochastic, cci, mfi, obv, parabolic_sar, donchian,
squeeze_momentum, vortex, aroon, and the rest.
"""

from engine.strategies import Ctx, Signal, strategy


@strategy(
    name="example_supertrend_squeeze",
    group="breakout",
    description="Supertrend is up and a volatility squeeze has just released",
)
def example_supertrend_squeeze(c: Ctx):
    st = c.ind("supertrend", period=10, multiplier=3.0)
    sq = c.ind("squeeze_momentum")
    if not st or not sq:
        return None

    line, direction = st
    if c.last(direction) != 1:                 # only with the trend
        return None

    # squeeze was on in the recent past and is off now: the release, not the coil
    was_squeezed = any(sq[-k] for k in range(2, 8) if sq[-k] is not None)
    if not was_squeezed or c.last(sq):
        return None

    if c.close[-1] <= c.open[-1]:              # want the release to be upward
        return None

    return Signal(
        direction="long",
        strength=0.75,
        reason="squeeze released upward while Supertrend was already up",
        stop_hint=c.last(line),                # Supertrend line doubles as the stop
        tags=["example", "breakout"],
    )
