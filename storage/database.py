import aiosqlite
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path='ares1.db'):
        self.db_path = db_path
        self._conn = None

    async def init(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._create_tables()
        logger.info(f"Database initialized at {self.db_path}")

    async def _create_tables(self):
        queries = [
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                direction TEXT,
                entry_price REAL,
                exit_price REAL,
                size REAL,
                pnl REAL,
                status TEXT,
                entry_time TEXT,
                exit_time TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                direction TEXT,
                price REAL,
                timestamp TEXT,
                confidence REAL,
                data_json TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS equity_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                equity REAL,
                available_margin REAL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS engine_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT,
                message TEXT,
                data_json TEXT
            )
            """
        ]
        for query in queries:
            await self._conn.execute(query)
        await self._conn.commit()

    async def save_trade(self, trade) -> int:
        query = """
            INSERT INTO trades (symbol, direction, entry_price, exit_price, size, pnl, status, entry_time, exit_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = await self._conn.execute(query, (
            trade.symbol, trade.direction, trade.entry_price, trade.exit_price, trade.size, trade.pnl, trade.status, getattr(trade, 'entry_time', None), getattr(trade, 'exit_time', None)
        ))
        await self._conn.commit()
        return cursor.lastrowid

    async def save_signal(self, signal) -> int:
        query = """
            INSERT INTO signals (symbol, direction, price, timestamp, confidence, data_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        cursor = await self._conn.execute(query, (
            signal.symbol, signal.direction, signal.price, signal.timestamp, signal.confidence, json.dumps(getattr(signal, 'data', {}))
        ))
        await self._conn.commit()
        return cursor.lastrowid

    async def save_equity_snapshot(self, snapshot):
        query = """
            INSERT INTO equity_snapshots (timestamp, equity, available_margin)
            VALUES (?, ?, ?)
        """
        await self._conn.execute(query, (snapshot.timestamp, snapshot.equity, snapshot.available_margin))
        await self._conn.commit()

    async def log_engine_event(self, event_type: str, message: str, data_json: Optional[str] = None):
        query = "INSERT INTO engine_log (event_type, message, data_json) VALUES (?, ?, ?)"
        await self._conn.execute(query, (event_type, message, data_json))
        await self._conn.commit()

    async def get_trades(self, limit=50, offset=0) -> List[Any]:
        query = "SELECT * FROM trades ORDER BY id DESC LIMIT ? OFFSET ?"
        async with self._conn.execute(query, (limit, offset)) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def get_signals(self, limit=50, offset=0) -> List[Any]:
        query = "SELECT * FROM signals ORDER BY id DESC LIMIT ? OFFSET ?"
        async with self._conn.execute(query, (limit, offset)) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def get_equity_history(self, days=30) -> List[Any]:
        query = "SELECT * FROM equity_snapshots ORDER BY id DESC LIMIT ?"
        async with self._conn.execute(query, (days * 1440,)) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def get_trade_stats(self) -> Dict[str, Any]:
        async with self._conn.execute("SELECT pnl, status FROM trades") as cursor:
            rows = await cursor.fetchall()
            
        total = len(rows)
        wins = len([r for r in rows if (r['pnl'] or 0) > 0])
        losses = len([r for r in rows if (r['pnl'] or 0) < 0])
        total_pnl = sum([r['pnl'] or 0 for r in rows])
        best = max([r['pnl'] or 0 for r in rows]) if rows else 0
        worst = min([r['pnl'] or 0 for r in rows]) if rows else 0
        
        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / total * 100) if total > 0 else 0,
            "profit_factor": abs(sum([r['pnl'] for r in rows if (r['pnl'] or 0) > 0]) / sum([r['pnl'] for r in rows if (r['pnl'] or 0) < 0])) if losses > 0 else 0,
            "avg_r": 0,
            "best_trade": best,
            "worst_trade": worst,
            "total_pnl": total_pnl
        }

    async def close(self):
        if self._conn:
            await self._conn.close()
