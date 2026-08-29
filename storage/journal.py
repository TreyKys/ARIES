import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Any

@dataclass
class PostMortem:
    entry_efficiency: float
    exit_efficiency: float
    r_multiple: float
    max_favorable: float
    max_adverse: float
    notes: str

class TradeJournal:
    def analyze_trade(self, trade) -> PostMortem:
        pnl = getattr(trade, 'pnl', 0)
        mfe = getattr(trade, 'mfe', pnl * 1.5) # Mocked MFE
        mae = getattr(trade, 'mae', 0)
        risk_amount = getattr(trade, 'risk_amount', 100)
        
        entry_eff = (pnl / mfe * 100) if mfe > 0 else 0
        exit_eff = (pnl / mfe * 100) if mfe > 0 else 0
        r_multiple = pnl / risk_amount if risk_amount > 0 else 0
        notes = "Profitable trade" if pnl > 0 else "Loss"
        
        return PostMortem(
            entry_efficiency=entry_eff,
            exit_efficiency=exit_eff,
            r_multiple=r_multiple,
            max_favorable=mfe,
            max_adverse=mae,
            notes=notes
        )

    async def save_post_mortem(self, trade, post_mortem: PostMortem, database):
        await database.log_engine_event(
            "POST_MORTEM",
            f"Trade {getattr(trade, 'id', 'unknown')} analyzed",
            f"{post_mortem}"
        )

    def get_performance_summary(self, trades: List[Any]) -> Dict[str, Any]:
        returns = [getattr(t, 'pnl', 0) for t in trades]
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]
        
        mean_ret = np.mean(returns) if returns else 0
        std_ret = np.std(returns) if returns and np.std(returns) > 0 else 1
        sharpe = (mean_ret / std_ret) * np.sqrt(252)
        
        neg_returns = [r for r in returns if r < 0]
        std_neg = np.std(neg_returns) if neg_returns and np.std(neg_returns) > 0 else 1
        sortino = (mean_ret / std_neg) * np.sqrt(252)
        
        win_rate = len(wins) / len(returns) if returns else 0
        loss_rate = 1 - win_rate
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0
        
        expectancy = (win_rate * avg_win) - (loss_rate * abs(avg_loss))
        
        return {
            "sharpe": sharpe,
            "sortino": sortino,
            "max_dd": 0,
            "recovery_factor": 0,
            "expectancy": expectancy,
            "avg_win_loss_ratio": abs(avg_win / avg_loss) if avg_loss != 0 else 0,
            "profit_factor": abs(sum(wins) / sum(losses)) if sum(losses) != 0 else 0
        }
