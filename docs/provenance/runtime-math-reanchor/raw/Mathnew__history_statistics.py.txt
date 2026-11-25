"""Math-owned domain statistics with bounded deterministic research inputs.

No provider, order, persistence, or strategy policy is implemented here.
"""
import math
import random
import statistics


def _finite_mean(values):
    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError("bootstrap values must be finite")
    try:
        result = math.fsum(values) / len(values)
    except OverflowError:
        result = statistics.mean(values)
    if not math.isfinite(result):
        raise ValueError("bootstrap mean must be finite and representable")
    return result


def _finite_observation(value):
    if isinstance(value, (bool, str, bytes, bytearray)):
        raise ValueError("bootstrap values must be numeric")
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("bootstrap values must be finite and numeric") from exc
    if not math.isfinite(value):
        raise ValueError("bootstrap values must be finite")
    return value


def _indexed(observations):
    result = {}
    for identifier, value in observations:
        if identifier is None:
            continue
        if identifier in result:
            raise ValueError("duplicate observation identifier in paired bootstrap")
        result[identifier] = _finite_observation(value)
    return result


def paired_observation_bootstrap(base, variant, runs=1000, seed=17):
    """Bootstrap paired differences over iterables of (identifier, value)."""
    if isinstance(runs, bool) or not isinstance(runs, int) or runs < 1:
        raise ValueError("runs must be a positive integer")
    b = _indexed(base)
    v = _indexed(variant)
    ids = sorted(set(b) & set(v), key=str)
    if len(ids) < 2:
        return {"paired": len(ids), "delta_mean": None, "ci95": None}
    diffs = [v[i] - b[i] for i in ids]
    delta_mean = _finite_mean(diffs)
    rng = random.Random(seed)
    means = [_finite_mean([diffs[rng.randrange(len(diffs))] for _ in diffs]) for _ in range(runs)]
    means.sort()
    lo = means[int(.025 * (runs - 1))]
    hi = means[int(.975 * (runs - 1))]
    return {"paired": len(ids), "delta_mean": delta_mean, "ci95": [lo, hi],
            "positive_supported": lo > 0, "negative_supported": hi < 0}


def block_observation_bootstrap(observations, block_size=20, runs=1000, seed=23):
    """Bootstrap the mean of ordered numeric observations in contiguous blocks."""
    if isinstance(block_size, bool) or not isinstance(block_size, int) or block_size < 1:
        raise ValueError("block_size must be a positive integer")
    if isinstance(runs, bool) or not isinstance(runs, int) or runs < 1:
        raise ValueError("runs must be a positive integer")
    values = [_finite_observation(value) for value in observations]
    if len(values) < max(2, block_size):
        return {"samples": len(values), "ci95": None}
    blocks = [values[i:i + block_size] for i in range(0, len(values), block_size)
              if len(values[i:i + block_size]) == block_size]
    rng = random.Random(seed)
    means = []
    for _ in range(runs):
        sample = []
        while len(sample) < len(values):
            sample.extend(blocks[rng.randrange(len(blocks))])
        means.append(_finite_mean(sample[:len(values)]))
    means.sort()
    return {"samples": len(values), "blocks": len(blocks),
            "ci95": [means[int(.025 * (runs - 1))], means[int(.975 * (runs - 1))]]}


# Explicit host-independent arithmetic for caller-declared numerical screening.
# This additive ABI does not change either existing observation bootstrap.
from typing import NamedTuple
SCREENING_NUMERIC_ABI = 'math.numeric.screening.ordered-binary64.v1'

class NumericSampleSummary(NamedTuple):
    count: int
    positive: int
    negative: int
    total: float
    mean: float
    positive_fraction: float

class ProfitFactorObservation(NamedTuple):
    kind: str
    value: int | float | None

class NumericFoldObservation(NamedTuple):
    samples: int
    expectancy: int | float
    profit_factor: ProfitFactorObservation

class NumericFoldSummary(NamedTuple):
    folds: int
    samples: int
    profitable: int
    losing: int
    mean_expectancy: float
    mean_profit_factor: float | None
    eligible_factors: int
    excluded_factors: int
    no_loss_factors: int

    @property
    def profitable_fraction(self):
        folds, profitable, _ = _screen_fold_counts(self)
        return profitable / folds if folds else 0.0

    @property
    def losing_fraction(self):
        folds, _, losing = _screen_fold_counts(self)
        return losing / folds if folds else 0.0


def _screen_fold_counts(record):
    # A public NamedTuple may be manually fabricated: validate before arithmetic.
    if type(record) is not NumericFoldSummary:
        raise ValueError('SCREENING_EXACT_FOLD_SUMMARY_REQUIRED')
    folds, profitable, losing = record.folds, record.profitable, record.losing
    if type(folds) is not int or type(profitable) is not int or type(losing) is not int:
        raise ValueError('SCREENING_LITERAL_FOLD_COUNTS_REQUIRED')
    if not 0 <= folds <= 128 or not 0 <= profitable <= folds or not 0 <= losing <= folds:
        raise ValueError('SCREENING_FOLD_COUNT_BOUNDS')
    return folds, profitable, losing

class IIDMeanInterval(NamedTuple):
    lower: float
    mean: float
    upper: float

def _screen_number(value):
    if type(value) is not int and type(value) is not float:
        raise ValueError('SCREENING_LITERAL_BINARY64_REQUIRED')
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError('SCREENING_FINITE_BINARY64_REQUIRED') from exc
    if not math.isfinite(number) or type(value) is int and number != value:
        raise ValueError('SCREENING_FINITE_LOSSLESS_BINARY64_REQUIRED')
    return number

def _screen_values(values, maximum=4096):
    if (type(values) is not tuple and type(values) is not list) or len(values) > maximum:
        raise ValueError('SCREENING_BOUNDED_LITERAL_SEQUENCE_REQUIRED')
    return tuple(_screen_number(value) for value in values)

def _ordered_binary64_total(values):
    total = 0.0
    for value in values:
        total = total + value
        if not math.isfinite(total):
            raise ValueError('SCREENING_NONFINITE_RESULT')
    return total

def numeric_sample_summary(values):
    """Summarize <=4096 literal signed observations, never trade objects.

    ORDERED_BINARY64_V1 intentionally uses sequential additions on every host.
    No metadata, grouping, units, source attestation or promotion is inferred.
    """
    values = _screen_values(values)
    count = len(values)
    total = _ordered_binary64_total(values)
    positive = negative = 0
    for value in values:
        positive += value > 0
        negative += value < 0
    return NumericSampleSummary(count, positive, negative, total,
        total / count if count else 0.0, positive / count if count else 0.0)

def numeric_fold_summary(rows, *, min_expectancy=0.0, min_profit_factor=1.05,
                         factor_policy='ALL_FINITE_V1'):
    """Pure fold arithmetic/comparisons with caller-selected thresholds.

    Rows must be exact NumericFoldObservation records. NO_LOSSES is a separate
    factor tag with no numeric infinity. An empty eligible factor mean is None,
    never a fabricated zero. Legacy >=1e100 exclusion requires its named policy.
    Status, reason codes, fold selection and acceptance remain caller policy.
    """
    if (type(rows) is not tuple and type(rows) is not list) or len(rows) > 128:
        raise ValueError('SCREENING_FOLD_LIMIT')
    minimum_e = _screen_number(min_expectancy)
    minimum_pf = _screen_number(min_profit_factor)
    if minimum_pf < 0 or type(factor_policy) is not str or factor_policy not in ('ALL_FINITE_V1','LEGACY_LT_1E100_V1'):
        raise ValueError('SCREENING_NUMERIC_FACTOR_POLICY_REQUIRED')
    admitted = []
    samples = 0
    for row in rows:
        if type(row) is not NumericFoldObservation or type(row.samples) is not int or not 0 <= row.samples <= 4096:
            raise ValueError('SCREENING_EXACT_FOLD_RECORD_REQUIRED')
        samples += row.samples
        if samples > 4096:
            raise ValueError('SCREENING_SAMPLE_BUDGET')
        expectancy = _screen_number(row.expectancy)
        factor = row.profit_factor
        if type(factor) is not ProfitFactorObservation or type(factor.kind) is not str:
            raise ValueError('SCREENING_EXACT_FACTOR_RECORD_REQUIRED')
        if factor.kind == 'FINITE':
            value = _screen_number(factor.value)
            if value < 0:
                raise ValueError('SCREENING_NONNEGATIVE_FACTOR_REQUIRED')
        elif factor.kind == 'NO_LOSSES' and factor.value is None:
            value = None
        else:
            raise ValueError('SCREENING_CLOSED_FACTOR_TAG_REQUIRED')
        admitted.append((expectancy, value))
    profitable = losing = excluded = no_losses = 0
    factors = []
    for expectancy, factor in admitted:
        profitable += expectancy > minimum_e and (factor is None or factor >= minimum_pf)
        losing += expectancy < 0 or factor is not None and factor < 1.0
        if factor is None:
            no_losses += 1
            excluded += 1
        elif factor_policy == 'LEGACY_LT_1E100_V1' and factor >= 1e100:
            excluded += 1
        else:
            factors.append(factor)
    count = len(admitted)
    mean_e = _ordered_binary64_total(tuple(e for e, _ in admitted)) / count if count else 0.0
    mean_pf = _ordered_binary64_total(factors) / len(factors) if factors else None
    return NumericFoldSummary(count, samples, profitable, losing, mean_e,
        mean_pf, len(factors), excluded, no_losses)

def iid_observation_mean_bootstrap(values, *, runs=1000, seed=17, confidence=.95):
    """Bounded seeded IID mean CI with explicit linear quantiles.

    ORDERED_BINARY64_V1 preserves the old Python3.11 addition/draw/quantile
    order, independently of host Python. Existing paired/block APIs are intact.
    <=4096 observations, <=1000 runs and <=1000000 observation draws.
    """
    values = _screen_values(values)
    confidence = _screen_number(confidence)
    if (not values or type(runs) is not int or not 1 <= runs <= 1000 or
            type(seed) is not int or not 0 <= seed <= 2**31 - 1 or
            not 0.0 < confidence < 1.0 or len(values) * runs > 1000000):
        raise ValueError('SCREENING_BOOTSTRAP_BUDGET_OR_POLICY')
    count = len(values)
    mean = _ordered_binary64_total(values) / count
    rng = random.Random(seed)
    means = []
    for _ in range(runs):
        draw = tuple(values[rng.randrange(count)] for _ in values)
        means.append(_ordered_binary64_total(draw) / count)
    means.sort()
    alpha = (1.0 - confidence) / 2.0
    def quantile(q):
        position = (runs - 1) * q
        low = int(position)
        high = min(low + 1, runs - 1)
        fraction = position - low
        result = means[low] * (1.0 - fraction) + means[high] * fraction
        if not math.isfinite(result):
            raise ValueError('SCREENING_NONFINITE_QUANTILE')
        return result
    return IIDMeanInterval(quantile(alpha), mean, quantile(1.0 - alpha))


class NumericProfitLossSummary(NamedTuple):
    numeric: NumericSampleSummary
    gross_profit: float
    gross_loss: float
    profit_factor: ProfitFactorObservation
    max_drawdown: float
    max_consecutive_losses: int

def project_decimal_observations(values):
    """Explicit DECIMAL_TO_BINARY64_V1 descriptive projection, not accounting.

    Exact plain finite Decimal inputs only; <=4096 values. Rounding to nearest
    binary64 is intentional and may lose decimal precision. Nonzero underflow
    and nonfinite overflow refuse. The caller's Decimal context is untouched.
    No currency, PnL source, availability or trading authority is inferred.
    """
    from decimal import Decimal
    if (type(values) is not tuple and type(values) is not list) or len(values)>4096:
        raise ValueError('DECIMAL_PROJECTION_BOUNDED_LITERAL_BATCH_REQUIRED')
    captured=tuple(values)
    for value in captured:
        if type(value) is not Decimal or not value.is_finite():
            raise ValueError('DECIMAL_PROJECTION_PLAIN_FINITE_DECIMAL_REQUIRED')
    out=[]
    for value in captured:
        try:number=float(value)
        except (OverflowError,ValueError) as exc:
            raise ValueError('DECIMAL_PROJECTION_RANGE') from exc
        if not math.isfinite(number) or number==0.0 and not value.is_zero():
            raise ValueError('DECIMAL_PROJECTION_NONFINITE_OR_NONZERO_UNDERFLOW')
        out.append(number)
    return tuple(out)

def _ordered_equity_summary(values):
    """Ordered binary64 equity, drawdown and loss streak for admitted values."""
    equity=peak=drawdown=0.0
    streak=maximum_streak=0
    for value in values:
        equity=equity+value
        if not math.isfinite(equity):raise ValueError('PROFIT_LOSS_NONFINITE_EQUITY')
        peak=max(peak,equity)
        distance=peak-equity
        if not math.isfinite(distance):raise ValueError('PROFIT_LOSS_NONFINITE_DRAWDOWN')
        drawdown=max(drawdown,distance)
        if value<0:
            streak+=1;maximum_streak=max(maximum_streak,streak)
        else:streak=0
    return drawdown,maximum_streak

def numeric_profit_loss_summary(values):
    """ORDERED_BINARY64_V1 arithmetic for declared signed outcome values.

    This generic unit-preserving view does not simulate fills, interpret trade
    objects/metadata, infer currency, or replace exact accounting. NO_LOSSES
    is explicit rather than a nonfinite infinity. Derived overflow refuses.
    """
    values=_screen_values(values)
    numeric=numeric_sample_summary(values)
    profit=_ordered_binary64_total(tuple(value for value in values if value>0))
    loss=-_ordered_binary64_total(tuple(value for value in values if value<0))
    if loss>0:
        ratio=profit/loss
        if not math.isfinite(ratio):raise ValueError('PROFIT_LOSS_NONFINITE_FACTOR')
        factor=ProfitFactorObservation('FINITE',ratio)
    elif profit>0:factor=ProfitFactorObservation('NO_LOSSES',None)
    else:factor=ProfitFactorObservation('FINITE',0.0)
    drawdown,maximum_streak=_ordered_equity_summary(values)
    return NumericProfitLossSummary(numeric,profit,loss,factor,drawdown,maximum_streak)

class NumericTradeObservation(NamedTuple):
    gross_pnl: int | float
    net_pnl: int | float
    fees: int | float
    mae: int | float | None = None
    mfe: int | float | None = None
    r_multiple: int | float | None = None
    holding_ms: int | None = None

class NumericOptionalSummary(NamedTuple):
    count: int
    total: float
    mean: float | None

class NumericTradeSummary(NamedTuple):
    net: NumericProfitLossSummary
    gross_pnl_total: float
    fees_total: float
    mae: NumericOptionalSummary
    mfe: NumericOptionalSummary
    r_multiple: NumericOptionalSummary
    holding_ms: NumericOptionalSummary

def numeric_trade_summary(observations):
    """Describe <=4096 exact NumericTradeObservation caller declarations.

    ORDERED_BINARY64_V1 preserves order and intentional binary64 rounding,
    including subnormal mean rounding. Decimal conversion remains explicit.
    Gross PnL and fees are supplied amounts, independent of the net outcome
    partitions named gross_profit/gross_loss in NumericProfitLossSummary.
    Missing metadata has count zero and mean None, never an invented value.
    No fill, accounting identity, excursion, units or authority is inferred.
    """
    if (type(observations) is not list and type(observations) is not tuple) or len(observations)>4096:
        raise ValueError('TRADE_SUMMARY_BOUNDED_LITERAL_SEQUENCE_REQUIRED')
    captured=tuple(observations)
    for row in captured:
        if type(row) is not NumericTradeObservation:
            raise ValueError('TRADE_SUMMARY_EXACT_OBSERVATION_REQUIRED')
    # Detach the entire batch before numeric admission or any numerical helper.
    captured=tuple(tuple(row) for row in captured)
    admitted=[]
    for gross,net,fees,mae,mfe,r_multiple,holding_ms in captured:
        gross=_screen_number(gross);net=_screen_number(net);fees=_screen_number(fees)
        if fees<0:raise ValueError('TRADE_SUMMARY_NONNEGATIVE_FEES_REQUIRED')
        optional=tuple(None if value is None else _screen_number(value)
                       for value in (mae,mfe,r_multiple))
        if holding_ms is not None:
            if type(holding_ms) is not int or not 0<=holding_ms<=2**53-1:
                raise ValueError('TRADE_SUMMARY_LITERAL_HOLDING_MS_REQUIRED')
            holding_ms=_screen_number(holding_ms)
        admitted.append((gross,net,fees,*optional,holding_ms))
    admitted=tuple(admitted)
    net=numeric_profit_loss_summary(tuple(row[1] for row in admitted))
    gross=numeric_sample_summary(tuple(row[0] for row in admitted))
    fees=numeric_sample_summary(tuple(row[2] for row in admitted))
    metadata=[]
    for index in (3,4,5,6):
        values=tuple(row[index] for row in admitted if row[index] is not None)
        summary=numeric_sample_summary(values)
        metadata.append(NumericOptionalSummary(summary.count,summary.total,
                                               summary.mean if summary.count else None))
    return NumericTradeSummary(net,gross.total,fees.total,*metadata)

def permutation_drawdowns(values, *, runs=1000, seed=0):
    """Seeded permutation maximum drawdowns over caller-declared outcomes.

    A fresh original-order list is shuffled for every run by a private RNG.
    Ordered binary64 equity/peak arithmetic matches the admitted legacy model.
    <=4096 plain finite lossless values, <=1000 runs, <=1000000 value visits.
    This is a conditional record-order model, not a market, stationarity,
    risk-of-ruin, accounting, source authenticity or trading authority claim.
    Derived nonfinite equity/drawdown aborts the entire result.
    """
    if (type(values) is not list and type(values) is not tuple) or not 1<=len(values)<=4096:
        raise ValueError('PERMUTATION_BOUNDED_NONEMPTY_LITERAL_SEQUENCE_REQUIRED')
    captured=tuple(values)
    if (type(runs) is not int or not 1<=runs<=1000 or
            type(seed) is not int or not 0<=seed<=2**31-1 or
            len(captured)*runs>1000000):
        raise ValueError('PERMUTATION_BUDGET_OR_POLICY')
    admitted=tuple(_screen_number(value) for value in captured)
    rng=random.Random(seed)
    out=[]
    for _ in range(runs):
        path=list(admitted)
        rng.shuffle(path)
        drawdown,_=_ordered_equity_summary(path)
        out.append(drawdown)
    return tuple(out)
