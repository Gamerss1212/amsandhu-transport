"""Rule language: the text a strategy definition uses for entries, filters and exits.

    cross_above(ema(close,9), ema(close,21)) and close > vwap() and rvol(20) > 1.5
    persist(close > tf("1h", ema(close,50)), 3) or rsi(close,2) < 5
    close > opening_range(15).high + 0.1 * atr(14)

Grammar (lowest to highest precedence): `or`, `and`, `not`, comparisons (> < >= <= == !=),
+ -, * /, unary minus, postfix `.output` and `[k]` (value k bars ago), primaries (numbers,
"strings", price sources, function and indicator calls, parentheses). `$name` is replaced by a
strategy or bot parameter before parsing.

Every expression evaluates to a Series aligned with the base Frame (or a scalar). Truth values
are 1.0 / 0.0, and None means "unknown" (an input is warming up or missing). Logic is
three-valued: `False and None` is False, `True and None` is None; a rule that is None never
triggers an order and is reported as unknown.

Multi-timeframe and multi-instrument values use tf("1h", expr), sym("SPY", expr) and
on("okx:BTC-USDT-SWAP", "1h", expr). The other series is aligned to the base bar by taking the
last bar that had COMPLETED by the time the base bar completed, so no value from a still-open
higher-timeframe bar is ever used.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from mab import indicators as ind
from mab.clock import tf_ms, is_equity
from mab.frame import Frame

SOURCES = {"open", "high", "low", "close", "volume", "hl2", "hlc3", "ohlc4", "time",
           "buy_vol", "sell_vol", "n_trades", "bid", "ask", "bid_depth", "ask_depth", "funding", "oi"}


class ExprError(ValueError):
    pass


# ============================================================================ AST

@dataclass(frozen=True)
class Node:
    def key(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class Num(Node):
    v: float
    def key(self): return repr(float(self.v)) if not float(self.v).is_integer() else str(int(self.v))


@dataclass(frozen=True)
class Str(Node):
    v: str
    def key(self): return '"' + self.v + '"'


@dataclass(frozen=True)
class Src(Node):
    name: str
    def key(self): return self.name


@dataclass(frozen=True)
class Call(Node):
    name: str
    args: Tuple[Node, ...]
    kwargs: Tuple[Tuple[str, Node], ...]
    output: Optional[str] = None
    def key(self):
        parts = [a.key() for a in self.args] + [f"{k}={v.key()}" for k, v in self.kwargs]
        return f"{self.name}({','.join(parts)})" + (f".{self.output}" if self.output else "")


@dataclass(frozen=True)
class Lag(Node):
    x: Node
    k: int
    def key(self): return f"{self.x.key()}[{self.k}]"


@dataclass(frozen=True)
class Bin(Node):
    op: str
    a: Node
    b: Node
    def key(self): return f"({self.a.key()} {self.op} {self.b.key()})"


@dataclass(frozen=True)
class Cmp(Node):
    op: str
    a: Node
    b: Node
    def key(self): return f"{self.a.key()} {self.op} {self.b.key()}"


@dataclass(frozen=True)
class Logic(Node):
    op: str               # "and" | "or"
    items: Tuple[Node, ...]
    def key(self): return "(" + f" {self.op} ".join(i.key() for i in self.items) + ")"


@dataclass(frozen=True)
class Not(Node):
    x: Node
    def key(self): return f"not {self.x.key()}"


@dataclass(frozen=True)
class Neg(Node):
    x: Node
    def key(self): return f"-{self.x.key()}"


# ============================================================================ parser

_TOKEN = re.compile(r"""
    (?P<ws>\s+) |
    (?P<num>\d+\.\d*|\.\d+|\d+(?:[eE][-+]?\d+)?) |
    (?P<str>"[^"]*"|'[^']*') |
    (?P<op>>=|<=|==|!=|[><+\-*/(),.\[\]=]) |
    (?P<id>[A-Za-z_][A-Za-z0-9_]*)
""", re.VERBOSE)


def substitute(text: str, params: Dict[str, Any]) -> str:
    def rep(m):
        k = m.group(1)
        if k not in params:
            raise ExprError(f"parameter ${k} is not defined")
        v = params[k]
        if isinstance(v, str):
            return '"' + v + '"'
        if isinstance(v, bool):
            return "1" if v else "0"
        return repr(v)
    return re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)", rep, text)


def tokenize(text: str) -> List[Tuple[str, str]]:
    out, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise ExprError(f"unexpected character {text[pos]!r} at {pos} in: {text}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        val = m.group(kind)
        if kind == "id" and val in ("and", "or", "not", "true", "false"):
            kind = "kw"
        out.append((kind, val))
    out.append(("end", ""))
    return out


class Parser:
    def __init__(self, text: str):
        self.text = text
        self.toks = tokenize(text)
        self.i = 0

    def peek(self, k=0):
        return self.toks[self.i + k]

    def take(self, kind=None, val=None):
        t = self.toks[self.i]
        if (kind and t[0] != kind) or (val is not None and t[1] != val):
            raise ExprError(f"expected {val or kind}, found {t[1] or 'end of rule'} in: {self.text}")
        self.i += 1
        return t

    def parse(self) -> Node:
        n = self.or_()
        if self.peek()[0] != "end":
            raise ExprError(f"unexpected {self.peek()[1]!r} in: {self.text}")
        return n

    def or_(self):
        items = [self.and_()]
        while self.peek() == ("kw", "or"):
            self.take(); items.append(self.and_())
        return items[0] if len(items) == 1 else Logic("or", tuple(items))

    def and_(self):
        items = [self.not_()]
        while self.peek() == ("kw", "and"):
            self.take(); items.append(self.not_())
        return items[0] if len(items) == 1 else Logic("and", tuple(items))

    def not_(self):
        if self.peek() == ("kw", "not"):
            self.take()
            return Not(self.not_())
        return self.cmp()

    def cmp(self):
        a = self.sum()
        t = self.peek()
        if t[0] == "op" and t[1] in (">", "<", ">=", "<=", "==", "!="):
            self.take()
            return Cmp(t[1], a, self.sum())
        return a

    def sum(self):
        a = self.term()
        while self.peek()[0] == "op" and self.peek()[1] in ("+", "-"):
            op = self.take()[1]
            a = Bin(op, a, self.term())
        return a

    def term(self):
        a = self.unary()
        while self.peek()[0] == "op" and self.peek()[1] in ("*", "/"):
            op = self.take()[1]
            a = Bin(op, a, self.unary())
        return a

    def unary(self):
        if self.peek() == ("op", "-"):
            self.take()
            x = self.unary()
            return Num(-x.v) if isinstance(x, Num) else Neg(x)
        return self.postfix()

    def postfix(self):
        x = self.primary()
        while True:
            t = self.peek()
            if t == ("op", "."):
                self.take()
                name = self.take("id")[1]
                if not isinstance(x, Call) or x.output:
                    raise ExprError(f".{name} can only follow an indicator call in: {self.text}")
                x = Call(x.name, x.args, x.kwargs, name)
            elif t == ("op", "["):
                self.take()
                k = self.take("num")[1]
                self.take("op", "]")
                if "." in k or int(k) < 0:
                    raise ExprError(f"lag must be a non-negative whole number of bars in: {self.text}")
                x = Lag(x, int(k))
            else:
                return x

    def primary(self):
        kind, val = self.peek()
        if kind == "num":
            self.take(); return Num(float(val))
        if kind == "str":
            self.take(); return Str(val[1:-1])
        if kind == "kw" and val in ("true", "false"):
            self.take(); return Num(1.0 if val == "true" else 0.0)
        if (kind, val) == ("op", "("):
            self.take()
            x = self.or_()
            self.take("op", ")")
            return x
        if kind == "id":
            self.take()
            if self.peek() == ("op", "("):
                self.take()
                args, kwargs = [], []
                if self.peek() != ("op", ")"):
                    while True:
                        if self.peek()[0] == "id" and self.peek(1) == ("op", "="):
                            k = self.take()[1]; self.take()
                            kwargs.append((k, self.or_()))
                        else:
                            if kwargs:
                                raise ExprError(f"positional argument after keyword in: {self.text}")
                            args.append(self.or_())
                        if self.peek() == ("op", ","):
                            self.take(); continue
                        break
                self.take("op", ")")
                if val not in FUNCS and val not in ind.REGISTRY:
                    raise ExprError(f"unknown function or indicator {val!r} in: {self.text}")
                return Call(val, tuple(args), tuple(kwargs))
            if val in SOURCES:
                return Src(val)
            raise ExprError(f"unknown name {val!r} (price sources: {', '.join(sorted(SOURCES))}) in: {self.text}")
        raise ExprError(f"unexpected {val or 'end of rule'!r} in: {self.text}")


_PARSE_CACHE: Dict[str, Node] = {}


def parse(text: str, params: Optional[Dict[str, Any]] = None) -> Node:
    t = substitute(text, params or {})
    n = _PARSE_CACHE.get(t)
    if n is None:
        n = _PARSE_CACHE[t] = Parser(t).parse()
        validate(n)
    return n


# ============================================================================ evaluation

Resolver = Callable[[str, str, str], Optional[Frame]]


def _scalar(v) -> bool:
    return not isinstance(v, list)


def _bcast(v, n):
    return v if isinstance(v, list) else [v] * n


def _truth(v) -> Optional[bool]:
    if v is None:
        return None
    return bool(v)


class Evaluator:
    """Evaluates parsed rules on one base Frame; results are cached on the Frame."""

    def __init__(self, frame: Frame, resolver: Optional[Resolver] = None, events: Optional["Events"] = None):
        self.f = frame
        self.resolver = resolver
        self.events = events

    def series(self, node: Node) -> List:
        v = self.eval(node)
        return _bcast(v, self.f.n)

    def eval(self, node: Node):
        k = node.key()
        cache = self.f.cache
        if k in cache and not isinstance(node, (Num, Str)):
            return cache[k]
        v = self._eval(node)
        if not isinstance(node, (Num, Str)):
            cache[k] = v
        return v

    def _eval(self, node: Node):
        f = self.f
        n = f.n
        if isinstance(node, Num):
            return float(node.v)
        if isinstance(node, Str):
            return node.v
        if isinstance(node, Src):
            return list(f.col(node.name)) if node.name != "time" else [float(t) for t in f.t]
        if isinstance(node, Lag):
            return ind.shift(self.series(node.x), node.k)
        if isinstance(node, Neg):
            x = self.eval(node.x)
            return -x if _scalar(x) else [None if v is None else -v for v in x]
        if isinstance(node, Bin):
            a, b = self.eval(node.a), self.eval(node.b)
            op = node.op
            fn = {"+": lambda p, q: p + q, "-": lambda p, q: p - q, "*": lambda p, q: p * q,
                  "/": lambda p, q: p / q if q else None}[op]
            if _scalar(a) and _scalar(b):
                return fn(a, b)
            a, b = _bcast(a, n), _bcast(b, n)
            return [None if p is None or q is None else fn(p, q) for p, q in zip(a, b)]
        if isinstance(node, Cmp):
            a, b = _bcast(self.eval(node.a), n), _bcast(self.eval(node.b), n)
            op = {">": lambda p, q: p > q, "<": lambda p, q: p < q, ">=": lambda p, q: p >= q,
                  "<=": lambda p, q: p <= q, "==": lambda p, q: p == q, "!=": lambda p, q: p != q}[node.op]
            return [None if p is None or q is None else (1.0 if op(p, q) else 0.0) for p, q in zip(a, b)]
        if isinstance(node, Not):
            x = self.series(node.x)
            return [None if v is None else (0.0 if v else 1.0) for v in x]
        if isinstance(node, Logic):
            cols = [self.series(x) for x in node.items]
            out = []
            for vals in zip(*cols):
                if node.op == "and":
                    if any(v is not None and not v for v in vals):
                        out.append(0.0)
                    elif any(v is None for v in vals):
                        out.append(None)
                    else:
                        out.append(1.0)
                else:
                    if any(v is not None and v for v in vals):
                        out.append(1.0)
                    elif any(v is None for v in vals):
                        out.append(None)
                    else:
                        out.append(0.0)
            return out
        if isinstance(node, Call):
            return self._call(node)
        raise ExprError(f"cannot evaluate {node}")

    # ------------------------------------------------------------------ calls
    def _call(self, node: Call):
        if node.name in ind.REGISTRY:
            spec = ind.REGISTRY[node.name]
            args = list(node.args)
            x = None
            if spec.series_input:
                if not args:
                    raise ExprError(f"{node.name} needs a series as its first argument")
                x = self.series(args.pop(0))
            names = [p for p, _ in spec.params]
            if len(args) > len(names):
                raise ExprError(f"{node.name} takes at most {len(names)} parameters")
            params = {}
            for p, a in zip(names, args):
                params[p] = self._const(a, node)
            for k, a in node.kwargs:
                params[k] = self._const(a, node)
            full_key = Call(node.name, node.args, node.kwargs).key()
            res = self.f.cache.get("ind:" + full_key)
            if res is None:
                res = ind.compute(node.name, self.f, x, **params)
                self.f.cache["ind:" + full_key] = res
            out = node.output or spec.outputs[0]
            if out not in res:
                raise ExprError(f"{node.name} has no output {out!r}; outputs: {', '.join(spec.outputs)}")
            return res[out]
        fn = FUNCS[node.name]
        return fn(self, node)

    def _const(self, a: Node, node: Call):
        if isinstance(a, (Num, Str)):
            return a.v if isinstance(a, Str) else (int(a.v) if float(a.v).is_integer() else a.v)
        raise ExprError(f"{node.name}: indicator parameters must be constants, got {a.key()}")

    # ------------------------------------------------------------------ cross-series alignment
    def other(self, venue: str, instrument: str, tf: str, node: Node) -> List:
        key = f"align:{venue}:{instrument}:{tf}:{node.key()}"
        if key in self.f.cache:
            return self.f.cache[key]
        if (venue, instrument, tf) == (self.f.venue, self.f.instrument, self.f.tf):
            out = self.series(node)
        else:
            if self.resolver is None:
                raise ExprError(f"no data resolver for {venue}:{instrument}/{tf}")
            g = self.resolver(venue, instrument, tf)
            if g is None or g.n == 0:
                out = [None] * self.f.n
            else:
                vals = Evaluator(g, self.resolver, self.events).series(node)
                out = align(self.f, g, vals)
        self.f.cache[key] = out
        return out


def align(base: Frame, other: Frame, vals: Sequence) -> List:
    """For each base bar, the value from the last `other` bar that had completed by the base bar's end."""
    out = [None] * base.n
    j = -1
    for i in range(base.n):
        end = base.t[i] + base.step
        while j + 1 < other.n and other.t[j + 1] + other.step <= end:
            j += 1
        if j >= 0:
            out[i] = vals[j]
    return out


# ============================================================================ functions

FUNCS: Dict[str, Callable] = {}


def fn(name, arity=None, doc=""):
    def deco(f):
        f.doc = doc
        f.arity = arity
        FUNCS[name] = f
        return f
    return deco


def _args(ev: Evaluator, node: Call, n: int) -> list:
    if len(node.args) != n:
        raise ExprError(f"{node.name} takes {n} argument(s)")
    return list(node.args)


def _int(ev, node, a) -> int:
    if not isinstance(a, Num):
        raise ExprError(f"{node.name}: window length must be a constant")
    return int(a.v)


@fn("cross_above", 2, "a crosses above b on this bar: a > b now and a <= b on the previous bar")
def _cross_above(ev, node):
    a, b = (ev.series(x) for x in _args(ev, node, 2))
    return _cross(a, b, True)


@fn("cross_below", 2, "a crosses below b on this bar: a < b now and a >= b on the previous bar")
def _cross_below(ev, node):
    a, b = (ev.series(x) for x in _args(ev, node, 2))
    return _cross(a, b, False)


def _cross(a, b, up):
    out = [None] * len(a)
    for i in range(1, len(a)):
        if None in (a[i], b[i], a[i - 1], b[i - 1]):
            continue
        out[i] = 1.0 if ((a[i] > b[i] and a[i - 1] <= b[i - 1]) if up else (a[i] < b[i] and a[i - 1] >= b[i - 1])) else 0.0
    return out


@fn("persist", 2, "cond has been true on each of the last n bars (including this one)")
def _persist(ev, node):
    c, n = node.args
    x, k = ev.series(c), _int(ev, node, n)
    out = [None] * len(x)
    for i in range(k - 1, len(x)):
        w = x[i - k + 1:i + 1]
        if any(v is not None and not v for v in w):
            out[i] = 0.0
        elif all(v is not None for v in w):
            out[i] = 1.0
    return out


@fn("within", 2, "cond was true on at least one of the last n bars (including this one)")
def _within(ev, node):
    c, n = node.args
    x, k = ev.series(c), _int(ev, node, n)
    out = [None] * len(x)
    last = -10 ** 9
    for i, v in enumerate(x):
        if v:
            last = i
        out[i] = 1.0 if i - last < k else 0.0
    return out


@fn("count", 2, "number of the last n bars on which cond was true")
def _count(ev, node):
    c, n = node.args
    x = [1.0 if v else 0.0 for v in ev.series(c)]
    return ind.rolling_sum(x, _int(ev, node, n))


@fn("since", 1, "bars since cond was last true (0 = this bar); None if never in the buffer")
def _since(ev, node):
    x = ev.series(node.args[0])
    out, last = [None] * len(x), None
    for i, v in enumerate(x):
        if v:
            last = i
        out[i] = None if last is None else float(i - last)
    return out


@fn("valuewhen", 2, "value of x on the most recent bar where cond was true")
def _valuewhen(ev, node):
    c, xn = node.args
    cond, x = ev.series(c), ev.series(xn)
    out, cur = [None] * len(x), None
    for i, v in enumerate(cond):
        if v:
            cur = x[i]
        out[i] = cur
    return out


@fn("rising", 2, "x rose on each of the last n bars")
def _rising(ev, node):
    x, k = ev.series(node.args[0]), _int(ev, node, node.args[1])
    return [None if i < k or any(x[j] is None or x[j - 1] is None for j in range(i - k + 1, i + 1)) else
            (1.0 if all(x[j] > x[j - 1] for j in range(i - k + 1, i + 1)) else 0.0) for i in range(len(x))]


@fn("falling", 2, "x fell on each of the last n bars")
def _falling(ev, node):
    x, k = ev.series(node.args[0]), _int(ev, node, node.args[1])
    return [None if i < k or any(x[j] is None or x[j - 1] is None for j in range(i - k + 1, i + 1)) else
            (1.0 if all(x[j] < x[j - 1] for j in range(i - k + 1, i + 1)) else 0.0) for i in range(len(x))]


def _roll(fnc):
    def f(ev, node):
        if len(node.args) != 2:
            raise ExprError(f"{node.name} takes 2 arguments (series, window)")
        x, k = ev.series(node.args[0]), _int(ev, node, node.args[1])
        return fnc(x, k)
    f.arity = 2
    return f


FUNCS["highest"] = _roll(ind.rolling_max); FUNCS["highest"].doc = "highest value of x over the last n bars (inclusive)"
FUNCS["lowest"] = _roll(ind.rolling_min); FUNCS["lowest"].doc = "lowest value of x over the last n bars (inclusive)"
FUNCS["sum"] = _roll(ind.rolling_sum); FUNCS["sum"].doc = "sum of x over the last n bars"
FUNCS["mean"] = _roll(ind.sma); FUNCS["mean"].doc = "mean of x over the last n bars"
FUNCS["std"] = _roll(lambda x, k: ind.stdev(x, k, ddof=1)); FUNCS["std"].doc = "sample standard deviation over n bars"
FUNCS["zscore"] = _roll(ind.zscore); FUNCS["zscore"].doc = "(x - mean(x,n)) / std(x,n)"
FUNCS["pctrank"] = _roll(ind.percent_rank); FUNCS["pctrank"].doc = "percent of the previous n values below x"


@fn("median", 2, "median of x over the last n bars")
def _median(ev, node):
    x, k = ev.series(node.args[0]), _int(ev, node, node.args[1])
    out = [None] * len(x)
    for i in range(k - 1, len(x)):
        w = x[i - k + 1:i + 1]
        if None in w:
            continue
        s = sorted(w)
        out[i] = s[k // 2] if k % 2 else (s[k // 2 - 1] + s[k // 2]) / 2
    return out


@fn("change", 2, "x - x[n]")
def _change(ev, node):
    return ind.diff(ev.series(node.args[0]), _int(ev, node, node.args[1]))


@fn("pct", 2, "x / x[n] - 1")
def _pct(ev, node):
    x = ev.series(node.args[0]); p = ind.shift(x, _int(ev, node, node.args[1]))
    return [None if a is None or not b else a / b - 1 for a, b in zip(x, p)]


def _map1(f):
    def g(ev, node):
        x = ev.eval(node.args[0])
        if _scalar(x):
            return None if x is None else f(x)
        return [None if v is None else f(v) for v in x]
    g.arity = 1
    return g


FUNCS["abs"] = _map1(abs); FUNCS["abs"].doc = "absolute value"
FUNCS["log"] = _map1(lambda v: math.log(v) if v > 0 else None); FUNCS["log"].doc = "natural log"
FUNCS["sqrt"] = _map1(lambda v: math.sqrt(v) if v >= 0 else None); FUNCS["sqrt"].doc = "square root"
FUNCS["sign"] = _map1(lambda v: (v > 0) - (v < 0)); FUNCS["sign"].doc = "-1, 0 or 1"


def _map2(f):
    def g(ev, node):
        a, b = (ev.series(x) for x in _args(ev, node, 2))
        return [None if p is None or q is None else f(p, q) for p, q in zip(a, b)]
    g.arity = 2
    return g


FUNCS["min"] = _map2(min); FUNCS["min"].doc = "smaller of two values"
FUNCS["max"] = _map2(max); FUNCS["max"].doc = "larger of two values"


@fn("floor_to", 2, "x rounded down to a multiple of step (round-number levels)")
def _floor_to(ev, node):
    x = ev.series(node.args[0])
    st = node.args[1]
    if not isinstance(st, Num) or st.v <= 0:
        raise ExprError("floor_to: step must be a positive constant")
    return [None if v is None else math.floor(v / st.v) * st.v for v in x]


@fn("ceil_to", 2, "x rounded up to a multiple of step")
def _ceil_to(ev, node):
    x = ev.series(node.args[0])
    st = node.args[1]
    if not isinstance(st, Num) or st.v <= 0:
        raise ExprError("ceil_to: step must be a positive constant")
    return [None if v is None else math.ceil(v / st.v) * st.v for v in x]


@fn("iff", 3, "b if cond else c")
def _iff(ev, node):
    c, a, b = (ev.series(x) for x in _args(ev, node, 3))
    return [None if k is None else (p if k else q) for k, p, q in zip(c, a, b)]


@fn("corr", 3, "rolling Pearson correlation of x and y over n bars")
def _corr(ev, node):
    return ind.rolling_corr(ev.series(node.args[0]), ev.series(node.args[1]), _int(ev, node, node.args[2]))


@fn("beta", 3, "rolling OLS slope of x on y over n bars")
def _beta(ev, node):
    return ind.rolling_beta(ev.series(node.args[0]), ev.series(node.args[1]), _int(ev, node, node.args[2]))


@fn("spread_z", 3, "z-score of log(x) - beta*log(y), beta re-estimated over n bars")
def _spread_z(ev, node):
    return ind.spread_z(ev.series(node.args[0]), ev.series(node.args[1]), _int(ev, node, node.args[2]))


@fn("rs", 3, "relative strength: (x/x[n]) / (y/y[n]) - 1")
def _rs(ev, node):
    x, y, k = ev.series(node.args[0]), ev.series(node.args[1]), _int(ev, node, node.args[2])
    px, py = ind.shift(x, k), ind.shift(y, k)
    return [None if None in (a, b, c, d) or not b or not d or not c else (a / b) / (c / d) - 1
            for a, b, c, d in zip(x, px, y, py)]


@fn("avwap", 1, "VWAP anchored at every bar where cond is true (inclusive); None before the first anchor")
def _avwap(ev, node):
    return ind.anchored_vwap(ev.f, ev.series(node.args[0]))["value"]


# ---- cross-series
def _tfarg(ev, node, a):
    if not isinstance(a, Str):
        raise ExprError(f"{node.name}: timeframe must be a quoted string like \"1h\"")
    tf_ms(a.v)
    return a.v


def _symarg(ev, a, node):
    if not isinstance(a, Str):
        raise ExprError(f"{node.name}: instrument must be a quoted string")
    if ":" in a.v:
        v, s = a.v.split(":", 1)
        return v, s
    return ev.f.venue, a.v


@fn("tf", 2, 'tf("1h", expr): expr on this instrument\'s 1h bars, aligned to completed bars')
def _tf(ev, node):
    tf = _tfarg(ev, node, node.args[0])
    return ev.other(ev.f.venue, ev.f.instrument, tf, node.args[1])


@fn("sym", 2, 'sym("SPY", expr) or sym("okx:BTC-USDT-SWAP", expr): expr on another instrument, same timeframe')
def _sym(ev, node):
    v, s = _symarg(ev, node.args[0], node)
    return ev.other(v, s, ev.f.tf, node.args[1])


@fn("on", 3, 'on("SPY", "1d", expr): another instrument and timeframe')
def _on(ev, node):
    v, s = _symarg(ev, node.args[0], node)
    return ev.other(v, s, _tfarg(ev, node, node.args[1]), node.args[2])


# ---- time and session (exchange-local for stocks, UTC for crypto)
def _col(getter, doc):
    def f(ev, node):
        return [float(v) for v in getter(ev.f)]
    f.doc = doc
    f.arity = 0
    return f


FUNCS["tod"] = _col(lambda f: f.tod, "minutes after local midnight at the bar's open (New York for stocks, UTC for crypto)")
FUNCS["hour"] = _col(lambda f: [t // 60 for t in f.tod], "local hour of the bar's open")
FUNCS["dow"] = _col(lambda f: f.dow, "weekday of the session, Monday = 0")
FUNCS["dom"] = _col(lambda f: f.dom, "day of month")
FUNCS["month"] = _col(lambda f: f.month, "month 1-12")
FUNCS["bar_in_session"] = _col(lambda f: f.bar_in_sess, "0 for the session's first bar; -1 outside the session")


@fn("minutes_since_open", 0, "minutes from the session open to this bar's open")
def _mso(ev, node):
    f = ev.f
    return [None if f.sess[i] < 0 else (f.t[i] - f.sess_open[i]) / 60_000 for i in range(f.n)]


@fn("minutes_to_close", 0, "minutes from this bar's close to the session close")
def _mtc(ev, node):
    f = ev.f
    return [None if f.sess[i] < 0 else (f.sess_close[i] - (f.t[i] + f.step)) / 60_000 for i in range(f.n)]


@fn("time_between", 2, 'time_between("09:45", "15:30"): bar opens at or after the first and before the second local time')
def _time_between(ev, node):
    a, b = (_hhmm(x, node) for x in _args(ev, node, 2))
    return [1.0 if a <= t < b else 0.0 for t in ev.f.tod]


def _hhmm(a, node):
    if not isinstance(a, Str) or not re.fullmatch(r"\d{1,2}:\d{2}", a.v):
        raise ExprError(f'{node.name}: times are quoted "HH:MM"')
    h, m = a.v.split(":")
    return int(h) * 60 + int(m)


@fn("days_to_month_end", 0, "calendar days from the session day to the last day of its month")
def _dtme(ev, node):
    import calendar as _c
    f = ev.f
    out = []
    for i in range(f.n):
        d = date.fromordinal(f.sess[i]) if f.sess[i] > 0 else None
        out.append(None if d is None else float(_c.monthrange(d.year, d.month)[1] - d.day))
    return out


@fn("is_opex", 0, "1 on the third Friday of the month (standard US monthly options expiration)")
def _opex(ev, node):
    f = ev.f
    return [1.0 if f.dow[i] == 4 and 15 <= f.dom[i] <= 21 else 0.0 for i in range(f.n)]


@fn("pre_holiday", 0, "1 on the last trading session before an exchange holiday (weekday closure); stocks only")
def _pre_holiday(ev, node):
    from mab.clock import calendar_for, is_equity
    f = ev.f
    if not is_equity(f.asset_type):
        return [0.0] * f.n
    cal = calendar_for(f.asset_type)
    cache = {}
    out = []
    for i in range(f.n):
        s = f.sess[i]
        if s < 0:
            out.append(None)
            continue
        if s not in cache:
            d = date.fromordinal(s)
            nxt = d + timedelta(days=1)
            while nxt.weekday() >= 5:
                nxt += timedelta(days=1)
            cache[s] = 0.0 if cal.is_trading_day(nxt) else 1.0
        out.append(cache[s])
    return out


@fn("event", 1, 'event("fomc"|"cpi"|"earnings"): 1 on sessions with that scheduled event; None if the event '
                'calendar is not loaded (the rule then cannot trigger)')
def _event(ev, node):
    a = node.args[0]
    if not isinstance(a, Str):
        raise ExprError("event() takes a quoted event name")
    if ev.events is None:
        return [None] * ev.f.n
    days = ev.events.days(a.v, ev.f.instrument)
    if days is None:
        return [None] * ev.f.n
    return [None if s < 0 else (1.0 if s in days else 0.0) for s in ev.f.sess]


class Events:
    """Scheduled-event calendars: name -> set of session ordinals (per instrument for earnings)."""

    def __init__(self):
        self.global_days: Dict[str, set] = {}
        self.per_instrument: Dict[str, Dict[str, set]] = {}

    def days(self, name: str, instrument: str) -> Optional[set]:
        if name in self.per_instrument:
            return self.per_instrument[name].get(instrument, set())
        return self.global_days.get(name)


# ============================================================================ validation and explanation

def validate(node: Node):
    """Static checks: known names, argument counts, constant parameters, no negative lags."""
    if isinstance(node, Call):
        if node.name in ind.REGISTRY:
            spec = ind.REGISTRY[node.name]
            n_series = 1 if spec.series_input else 0
            if len(node.args) - n_series > len(spec.params):
                raise ExprError(f"{node.name} takes at most {len(spec.params)} parameters")
            if spec.series_input and not node.args:
                raise ExprError(f"{node.name} needs a series argument")
            for a in node.args[n_series:]:
                if not isinstance(a, (Num, Str)):
                    raise ExprError(f"{node.name}: parameters must be constants")
            known = {p for p, _ in spec.params}
            for k, _ in node.kwargs:
                if k not in known:
                    raise ExprError(f"{node.name} has no parameter {k!r}")
            if node.output and node.output not in spec.outputs:
                raise ExprError(f"{node.name} has no output {node.output!r}; outputs: {', '.join(spec.outputs)}")
        else:
            f = FUNCS[node.name]
            ar = getattr(f, "arity", None)
            if ar is not None and len(node.args) != ar:
                raise ExprError(f"{node.name} takes {ar} argument(s), got {len(node.args)}")
            if node.output:
                raise ExprError(f"{node.name} has no outputs")
        for a in node.args:
            validate(a)
        for _, a in node.kwargs:
            validate(a)
    elif isinstance(node, (Bin, Cmp)):
        validate(node.a); validate(node.b)
    elif isinstance(node, Logic):
        for x in node.items:
            validate(x)
    elif isinstance(node, (Not, Neg)):
        validate(node.x)
    elif isinstance(node, Lag):
        validate(node.x)


def references(node: Node) -> Dict[str, set]:
    """Indicators, functions, sources, extra timeframes and instruments a rule needs."""
    out = {"indicators": set(), "functions": set(), "sources": set(), "timeframes": set(), "instruments": set(),
           "events": set()}

    def walk(n):
        if isinstance(n, Call):
            (out["indicators"] if n.name in ind.REGISTRY else out["functions"]).add(n.name)
            if n.name == "tf" and isinstance(n.args[0], Str):
                out["timeframes"].add(n.args[0].v)
            if n.name == "sym" and isinstance(n.args[0], Str):
                out["instruments"].add(n.args[0].v)
            if n.name == "on" and isinstance(n.args[0], Str):
                out["instruments"].add(n.args[0].v)
                if isinstance(n.args[1], Str):
                    out["timeframes"].add(n.args[1].v)
            if n.name == "event" and isinstance(n.args[0], Str):
                out["events"].add(n.args[0].v)
            for a in n.args:
                walk(a)
            for _, a in n.kwargs:
                walk(a)
        elif isinstance(n, Src):
            out["sources"].add(n.name)
        elif isinstance(n, (Bin, Cmp)):
            walk(n.a); walk(n.b)
        elif isinstance(n, Logic):
            for x in n.items:
                walk(x)
        elif isinstance(n, (Not, Neg, Lag)):
            walk(n.x)
    walk(node)
    return out


_WINDOW_FUNCS = {"persist", "within", "count", "rising", "falling", "highest", "lowest", "sum", "mean", "std",
                 "zscore", "pctrank", "median", "change", "pct", "corr", "beta", "rs"}


def session_bars(tf: str, asset_type: str = "crypto") -> int:
    """Bars in one full session: 390 minutes for US stocks, 1440 for crypto."""
    minutes = 390 if is_equity(asset_type) else 1440
    return max(1, minutes * 60_000 // tf_ms(tf))


def warmup_by_series(node: Node, base_tf: str, asset_type: str = "crypto") -> Dict[Tuple[Optional[str], str], int]:
    """Bars of history each series needs before the rule's value is stable.

    Keys are (instrument or None for the bot's own instrument, timeframe). Session-anchored
    indicators need whole sessions: the current one from its first bar plus any earlier ones
    they read (e.g. the previous session's high for pivots)."""
    need: Dict[Tuple[Optional[str], str], int] = {}

    def bump(ctx, v):
        need[ctx] = max(need.get(ctx, 1), v)

    def walk(n, ctx) -> int:
        if isinstance(n, (Num, Str)):
            return 0
        if isinstance(n, Src):
            return 1
        if isinstance(n, Lag):
            return walk(n.x, ctx) + n.k
        if isinstance(n, (Bin, Cmp)):
            return max(walk(n.a, ctx), walk(n.b, ctx))
        if isinstance(n, Logic):
            return max(walk(x, ctx) for x in n.items)
        if isinstance(n, (Not, Neg)):
            return walk(n.x, ctx)
        if isinstance(n, Call):
            if n.name in ind.REGISTRY:
                spec = ind.REGISTRY[n.name]
                args = list(n.args)
                inner = walk(args.pop(0), ctx) if (spec.series_input and args) else 0
                params = {p: d for p, d in spec.params}
                for (p, _), a in zip(spec.params, args):
                    if isinstance(a, (Num, Str)):
                        params[p] = a.v
                for k, a in n.kwargs:
                    if isinstance(a, (Num, Str)):
                        params[k] = a.v
                params = {k: (int(v) if isinstance(v, float) and v.is_integer() else v) for k, v in params.items()}
                bars = spec.warmup(params)[1]
                if spec.sessions is not None:
                    bars = max(bars, (spec.sessions(params) + 1) * session_bars(ctx[1], asset_type))
                return bars + inner
            if n.name in ("tf", "sym", "on"):
                a = n.args
                if n.name == "tf":
                    sub = (ctx[0], a[0].v)
                elif n.name == "sym":
                    sub = (a[0].v, ctx[1])
                else:
                    sub = (a[0].v, a[1].v)
                bump(sub, walk(a[-1], sub) + 1)
                return 1
            win = int(n.args[-1].v) if (n.name in _WINDOW_FUNCS and n.args and isinstance(n.args[-1], Num)) else 0
            if n.name == "spread_z" and isinstance(n.args[-1], Num):
                win = 2 * int(n.args[-1].v)
            if n.name in ("cross_above", "cross_below"):
                win = 1
            inner = max([walk(a, ctx) for a in n.args] + [0])
            return inner + win
        return 1

    root = (None, base_tf)
    bump(root, walk(node, root))
    return need


def warmup_bars(node: Node, tf: str = "1m", asset_type: str = "crypto") -> int:
    return warmup_by_series(node, tf, asset_type).get((None, tf), 1)


def _fmt(v) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        a = abs(v)
        return f"{v:.6g}" if a < 1e6 else f"{v:,.0f}"
    return str(v)


def explain(ev: Evaluator, node: Node, i: int) -> List[dict]:
    """Rule outcomes behind a decision at bar i: one row per comparison or condition."""
    rows: List[dict] = []

    def val(n):
        v = ev.eval(n)
        return v[i] if isinstance(v, list) else v

    def walk(n):
        if isinstance(n, Logic):
            for x in n.items:
                walk(x)
            return
        if isinstance(n, Cmp):
            a, b, r = val(n.a), val(n.b), val(n)
            rows.append({"rule": n.key(), "passed": None if r is None else bool(r),
                         "detail": f"{_fmt(a)} {n.op} {_fmt(b)}"})
            return
        if isinstance(n, Not):
            r = val(n)
            rows.append({"rule": n.key(), "passed": None if r is None else bool(r), "detail": ""})
            return
        if isinstance(n, Call) and n.name in ("cross_above", "cross_below"):
            a, b = n.args
            av, bv = ev.series(a), ev.series(b)
            r = val(n)
            prev = f"{_fmt(av[i-1])} vs {_fmt(bv[i-1])}" if i > 0 else "n/a"
            rows.append({"rule": n.key(), "passed": None if r is None else bool(r),
                         "detail": f"now {_fmt(av[i])} vs {_fmt(bv[i])}; previous bar {prev}"})
            return
        r = val(n)
        rows.append({"rule": n.key(), "passed": None if r is None else bool(r), "detail": _fmt(r)})

    walk(node)
    return rows


def feature_values(ev: Evaluator, node: Node, i: int, limit: int = 12) -> Dict[str, Any]:
    """Values of the indicators and sources a rule reads, at bar i (for signal records)."""
    out: Dict[str, Any] = {}

    def walk(n):
        if len(out) >= limit:
            return
        if isinstance(n, Call):
            if n.name in ind.REGISTRY or n.name in ("tf", "sym", "on", "avwap", "highest", "lowest", "mean",
                                                    "zscore", "spread_z", "corr", "beta", "rs", "change", "pct"):
                v = ev.eval(n)
                out[n.key()] = v[i] if isinstance(v, list) else v
                if n.name in ind.REGISTRY:
                    return
            for a in n.args:
                walk(a)
        elif isinstance(n, Src):
            v = ev.eval(n)
            out[n.key()] = v[i]
        elif isinstance(n, (Bin, Cmp)):
            walk(n.a); walk(n.b)
        elif isinstance(n, Logic):
            for x in n.items:
                walk(x)
        elif isinstance(n, (Not, Neg, Lag)):
            walk(n.x)
    walk(node)
    return {k: (round(v, 8) if isinstance(v, float) else v) for k, v in out.items()}
