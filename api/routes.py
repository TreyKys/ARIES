from fastapi import APIRouter, Request, Depends, Query
from typing import List, Dict, Any

router = APIRouter(prefix="/api")

def get_engine(request: Request):
    return request.app.state.engine

def get_db(request: Request):
    return request.app.state.database

@router.get("/status")
async def get_status(engine = Depends(get_engine)):
    return engine.get_status()

@router.get("/trades")
async def get_trades(limit: int = Query(50), offset: int = Query(0), db = Depends(get_db)):
    return await db.get_trades(limit=limit, offset=offset)

@router.get("/signals")
async def get_signals(limit: int = Query(50), offset: int = Query(0), db = Depends(get_db)):
    return await db.get_signals(limit=limit, offset=offset)

@router.get("/equity")
async def get_equity(days: int = Query(30), db = Depends(get_db)):
    return await db.get_equity_history(days=days)

@router.get("/stats")
async def get_stats(db = Depends(get_db)):
    return await db.get_trade_stats()

@router.get("/config")
async def get_config(engine = Depends(get_engine)):
    return getattr(engine, 'settings', {})

@router.put("/config")
async def update_config(config: Dict[str, Any], engine = Depends(get_engine)):
    # Simple placeholder for config updates
    return {"status": "updated"}

@router.post("/mode/{mode}")
async def set_mode(mode: str, engine = Depends(get_engine)):
    engine.mode = mode.upper()
    return {"mode": engine.mode}
