import logging
from typing import Dict, List, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class CriterionScore(BaseModel):
    score: int
    max_score: int
    reason: str

class ConfluenceResult(BaseModel):
    total_score: int
    individual_scores: Dict[str, CriterionScore]
    is_tradeable: bool
    details: List[str]

class ConfluenceScorer:
    def __init__(self):
        self.min_trade_score = 80

    def score(self, analysis_data: dict) -> ConfluenceResult:
        """
        Evaluate market conditions against 10 strict criteria.
        Expects analysis_data with keys:
        - direction: 'LONG' or 'SHORT'
        - htf_regime: MarketRegime string
        - structure_aligned: bool
        - has_ob_or_fvg: bool
        - liquidity_swept: bool
        - price_zone: 'PREMIUM', 'DISCOUNT', 'EQUILIBRIUM'
        - in_ote: bool
        - rsi: float
        - cvd: float
        - in_killzone: bool
        - news_blackout: bool
        - rr_ratio: float
        """
        scores = {}
        total = 0
        details = []
        
        try:
            direction = analysis_data.get('direction', 'LONG')
            
            # 1. HTF Regime alignment (15 pts)
            regime = analysis_data.get('htf_regime', '')
            if (direction == 'LONG' and 'BULLISH' in regime) or \
               (direction == 'SHORT' and 'BEARISH' in regime):
                scores['regime'] = CriterionScore(score=15, max_score=15, reason=f"Regime aligns with {direction}")
            else:
                scores['regime'] = CriterionScore(score=0, max_score=15, reason=f"Regime {regime} conflicts with {direction}")

            # 2. Structure alignment (15 pts)
            if analysis_data.get('structure_aligned'):
                scores['structure'] = CriterionScore(score=15, max_score=15, reason="LTF structure aligned (BOS/CHoCH)")
            else:
                scores['structure'] = CriterionScore(score=0, max_score=15, reason="LTF structure not aligned")

            # 3. Order Block / FVG (12 pts)
            if analysis_data.get('has_ob_or_fvg'):
                scores['ob_fvg'] = CriterionScore(score=12, max_score=12, reason="Valid OB/FVG present at entry")
            else:
                scores['ob_fvg'] = CriterionScore(score=0, max_score=12, reason="No OB/FVG at entry")

            # 4. Liquidity Sweep (12 pts)
            if analysis_data.get('liquidity_swept'):
                scores['liquidity'] = CriterionScore(score=12, max_score=12, reason="Recent liquidity sweep confirmed")
            else:
                scores['liquidity'] = CriterionScore(score=0, max_score=12, reason="No clear liquidity sweep")

            # 5. Price Zone (10 pts)
            zone = analysis_data.get('price_zone', '')
            if (direction == 'LONG' and zone == 'DISCOUNT') or \
               (direction == 'SHORT' and zone == 'PREMIUM'):
                scores['zone'] = CriterionScore(score=10, max_score=10, reason=f"Price in correct zone ({zone})")
            else:
                scores['zone'] = CriterionScore(score=0, max_score=10, reason=f"Price in wrong zone ({zone})")

            # 6. OTE Zone (8 pts)
            if analysis_data.get('in_ote'):
                scores['ote'] = CriterionScore(score=8, max_score=8, reason="Price is in Optimal Trade Entry (0.618-0.786)")
            else:
                scores['ote'] = CriterionScore(score=0, max_score=8, reason="Price outside OTE")

            # 7. RSI filter (8 pts)
            rsi = analysis_data.get('rsi', 50)
            if (direction == 'LONG' and rsi < 70) or \
               (direction == 'SHORT' and rsi > 30):
                scores['rsi'] = CriterionScore(score=8, max_score=8, reason="RSI not overextended against trade")
            else:
                scores['rsi'] = CriterionScore(score=0, max_score=8, reason="RSI overextended")

            # 8. CVD filter (8 pts)
            cvd = analysis_data.get('cvd', 0.0)
            if (direction == 'LONG' and cvd > 0) or \
               (direction == 'SHORT' and cvd < 0):
                scores['cvd'] = CriterionScore(score=8, max_score=8, reason="CVD delta confirms direction")
            else:
                scores['cvd'] = CriterionScore(score=0, max_score=8, reason="CVD delta opposes direction")

            # 9. Killzone (6 pts)
            if analysis_data.get('in_killzone'):
                scores['killzone'] = CriterionScore(score=6, max_score=6, reason="Session is within killzone")
            else:
                scores['killzone'] = CriterionScore(score=0, max_score=6, reason="Outside active trading session")

            # 10. News Blackout (6 pts)
            if not analysis_data.get('news_blackout'):
                scores['news'] = CriterionScore(score=6, max_score=6, reason="No conflicting news events")
            else:
                scores['news'] = CriterionScore(score=0, max_score=6, reason="Upcoming news blackout period")

            # Tally
            for k, v in scores.items():
                total += v.score
                details.append(f"{k}: {v.score}/{v.max_score} - {v.reason}")

            rr_ratio = analysis_data.get('rr_ratio', 0.0)
            min_rr = analysis_data.get('min_rr', 2.0)
            
            is_tradeable = (total >= self.min_trade_score) and (rr_ratio >= min_rr)

            return ConfluenceResult(
                total_score=total,
                individual_scores=scores,
                is_tradeable=is_tradeable,
                details=details
            )
            
        except Exception as e:
            logger.error(f"Error computing confluence score: {e}")
            return ConfluenceResult(
                total_score=0,
                individual_scores={},
                is_tradeable=False,
                details=[f"Error evaluating confluence: {str(e)}"]
            )
