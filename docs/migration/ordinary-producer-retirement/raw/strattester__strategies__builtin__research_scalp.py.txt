from .research_common import HypothesisSpec

def scalp_hypotheses():
    """Candidate scalp entries. SPEC_ONLY until a causal generator is attached."""
    return (
      HypothesisSpec("SCALP_LEVEL_IMPULSE","scalp",
        {"setup":"level_impulse","requires":("level","volatility","volume_expansion")}),
      HypothesisSpec("SCALP_LEVEL_IMPULSE_DELTA","scalp",
        {"setup":"level_impulse","confirm":("volume_expansion","delta"),"requires":("level","public_trade_aggregates")}),
      HypothesisSpec("SCALP_SWEEP_RECLAIM","scalp",
        {"setup":"liquidity_sweep","confirm":"return_inside","entry":"reclaim"},
        execution_status="EXECUTABLE",signal_generator="strattester.research.scalp_entries:sweep_reclaim_entries"),
      HypothesisSpec("SCALP_FAILED_BREAKOUT","scalp",
        {"setup":"failed_breakout","entry":"return_inside_level","direction":"reversal"}),
      HypothesisSpec("SCALP_BREAKOUT_RETEST_VOLUME","scalp",
        {"setup":"breakout_retest","confirm":"volume_expansion","direction":"continuation"},
        execution_status="EXECUTABLE",signal_generator="strattester.research.scalp_entries:breakout_retest_volume_entries"),
      HypothesisSpec("SCALP_VOL_EXPANSION_CONTINUATION","scalp",
        {"setup":"compression_expansion","confirm":"volume_expansion","direction":"continuation"},
        execution_status="EXECUTABLE",signal_generator="strattester.research.scalp_entries:volatility_expansion_entries"),
      HypothesisSpec("SCALP_POC_RECLAIM","scalp",
        {"setup":"poc_reclaim","confirm":"delta","direction":"reversion_or_continuation"},
        execution_status="EXECUTABLE",signal_generator="strattester.research.scalp_entries:poc_reclaim_entries"),
      HypothesisSpec("SCALP_OI_DELTA_IMPULSE","scalp",
        {"setup":"impulse","confirm":("open_interest","delta","volume_expansion")}),
    )
