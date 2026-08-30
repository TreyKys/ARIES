import logging

logger = logging.getLogger(__name__)

class Council:
    """
    The 10-Member Multi-Agent Decision Engine (7 Original + 3 Departments).
    Requires unanimous YES (or ABSENT) votes to execute a trade.
    """
    def __init__(self, settings):
        self.settings = settings
        self.consecutive_losses = 0
        self.peak_equity = settings.STARTING_CAPITAL
        self.current_equity = settings.STARTING_CAPITAL
        
    def vote(self, state: dict) -> dict:
        if not state.get('ready'):
            return {'approved': False, 'reason': 'Bullpen Not Ready'}
            
        votes = {}
        direction = 'LONG' if state['macro_trend'] == 'BULLISH' else 'SHORT'
        
        # 1. The Risk Manager (The Anchor)
        current_dd = (self.peak_equity - self.current_equity) / self.peak_equity
        if current_dd >= 0.15:
            votes['RiskManager'] = {'vote': 'NO', 'reason': 'Tier 3 Drawdown - Hard Halt'}
        else:
            base_risk = 0.015
            allocated_risk = base_risk * 0.5 if current_dd > 0.05 else base_risk
            votes['RiskManager'] = {'vote': 'YES', 'allocated_risk': allocated_risk}

        # 2. The Trend Follower
        if state['macro_trend'] == state['structure_15m']:
            votes['TrendFollower'] = {'vote': 'YES', 'direction': direction}
        else:
            votes['TrendFollower'] = {'vote': 'NO', 'reason': 'Macro and Structure misalignment'}
            
        # 3. The Mean Reversionist
        rsi = state['rsi_5m']
        if state['regime'] == 'ASIAN_RANGE':
            if (direction == 'LONG' and rsi < 40) or (direction == 'SHORT' and rsi > 60):
                votes['MeanReversionist'] = {'vote': 'YES'}
            else:
                votes['MeanReversionist'] = {'vote': 'NO', 'reason': 'No extreme reading for Asian session'}
        elif state['regime'] == 'NY_OVERLAP':
            if (direction == 'LONG' and rsi > 50) or (direction == 'SHORT' and rsi < 50):
                votes['MeanReversionist'] = {'vote': 'YES'}
            else:
                votes['MeanReversionist'] = {'vote': 'NO', 'reason': 'Lack of momentum'}
        else:
            votes['MeanReversionist'] = {'vote': 'NO', 'reason': 'Chop regime'}

        # 4. Cost Gatekeeper
        sl_dist = state['atr_1m'] * 2
        tp_dist = sl_dist * 1.2
        if tp_dist > 2.5 * state['total_cost']:
            votes['Accountant'] = {'vote': 'YES', 'sl_dist': sl_dist, 'tp_dist': tp_dist}
        else:
            votes['Accountant'] = {'vote': 'NO', 'reason': 'Negative EV against spread/commission'}

        # 5. The Psychologist
        if self.consecutive_losses >= 3:
            votes['Psychologist'] = {'vote': 'NO', 'reason': 'Algorithmic Tilt Protection (3+ losses)'}
        else:
            votes['Psychologist'] = {'vote': 'YES'}

        # 6. The Contrarian
        retail = state['retail_long_ratio']
        if direction == 'LONG' and retail > 0.75:
            votes['Contrarian'] = {'vote': 'NO', 'reason': 'Retail greed exhaustion'}
        elif direction == 'SHORT' and retail < 0.25:
            votes['Contrarian'] = {'vote': 'NO', 'reason': 'Retail capitulation detected'}
        else:
            votes['Contrarian'] = {'vote': 'YES'}

        # 7. DEPARTMENT: The Macro Desk
        macro_dept = state.get('macro_desk', {})
        if macro_dept.get('is_shield_active'):
            votes['MacroDesk'] = {'vote': 'NO', 'reason': macro_dept.get('reason')}
        else:
            votes['MacroDesk'] = {'vote': 'YES'}

        # 8. DEPARTMENT: The Historian (Vector RAG)
        historian = state.get('historian', {})
        if historian.get('has_precedent'):
            if historian.get('win_rate') < 50.0:
                votes['Historian'] = {'vote': 'NO', 'reason': f"Historical precedent win rate too low ({historian.get('win_rate')}%)"}
            else:
                votes['Historian'] = {'vote': 'YES'}
        else:
            # If no history, abstain (doesn't veto)
            votes['Historian'] = {'vote': 'ABSENT', 'reason': 'No matching vector precedent'}

        # 9. DEPARTMENT: Order Flow & Liquidity
        order_flow = state.get('order_flow', {})
        of_bias = order_flow.get('bias', 'NEUTRAL')
        if (direction == 'LONG' and of_bias == 'BEARISH_SWEEP'):
             votes['OrderFlow'] = {'vote': 'NO', 'reason': 'Order book heavily skewed for downside sweep'}
        elif (direction == 'SHORT' and of_bias == 'BULLISH_SWEEP'):
             votes['OrderFlow'] = {'vote': 'NO', 'reason': 'Order book heavily skewed for upside sweep'}
        else:
             votes['OrderFlow'] = {'vote': 'YES'}


        # Tally Votes (ABSENT does not veto)
        rejections = [k for k, v in votes.items() if v['vote'] == 'NO']
        approved = len(rejections) == 0
        
        confidence = 100 if approved else max(0, 100 - (len(rejections) * 15))
        
        return {
            'approved': approved,
            'direction': direction if approved else None,
            'confidence': round(confidence, 1),
            'rejections': [votes[k]['reason'] for k in rejections],
            'allocated_risk': votes.get('RiskManager', {}).get('allocated_risk', 0.015),
            'sl_dist': votes.get('Accountant', {}).get('sl_dist', 0.0),
            'tp_dist': votes.get('Accountant', {}).get('tp_dist', 0.0),
            'votes_log': votes
        }
