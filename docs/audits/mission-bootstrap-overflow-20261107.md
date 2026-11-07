# Finite bootstrap evidence correction

Base: 7a19ab40c30efef431bb16f0ddc91960608bf597. Scope: existing Grid diagnostic statistics, not a new research engine or a replacement for the Math runtime.

Finite inputs could produce infinite paired differences or overflow a sum before division. Two base trades of -1e308 versus two variant trades of 1e308 returned delta_mean=Infinity, ci95=[Infinity,Infinity], positive_supported=true. Block resampling of two 1e308 values also returned infinite bounds although their mean is representable.

The initial eight-case regression suite produced six failures. A first divide-before-sum correction exposed subnormal loss: two further tests failed. The final implementation uses finite validation, compensated summation, and the standard-library exact-ratio mean fallback when the intermediate sum overflows. Unrepresentable paired differences are refused; representable large and subnormal means are retained. Original inputs, seed behavior, public fields, cost interpretation and dataset contracts are unchanged.

Local verification: 21 tests, zero skips, across the two existing statistics test modules and ten new numerical regressions. Initial RED, intermediate RED and GREEN logs are retained by Integration Owner. The additional Windows/Ubuntu workflow runs ten stdlib-only regressions after primary Git raw-source admission; it does not replace or skip existing required CI. Hosted results require separate exact-head evidence.

These diagnostics do not prove positive strategy expectancy, IID/trade independence, cost completeness, multiple-comparison correction, out-of-sample validity, live fills or physical/native acceptance. Missing instrument/cost/data capability profiles stay unavailable. No exchange requests, orders, policy changes or physical installation are introduced.
