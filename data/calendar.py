import asyncio
import logging
import httpx
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class EconomicCalendar:
    def __init__(self):
        self.events = []
        self._lock = asyncio.Lock()
        self.last_update = None
        self.HIGH_IMPACT_EVENTS = [
            "FOMC", "CPI", "NFP", "PPI", "GDP", "ECB", "BOE", "BOJ", 
            "Unemployment Claims", "Non-Farm Employment Change"
        ]

    async def update(self):
        async with self._lock:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
                    resp.raise_for_status()
                    data = resp.json()
                    
                    parsed_events = []
                    for item in data:
                        impact = item.get("impact", "")
                        if impact == "High":
                            title = item.get("title", "")
                            # Check if title matches our high impact
                            if any(x.lower() in title.lower() for x in self.HIGH_IMPACT_EVENTS):
                                date_str = item.get("date", "")
                                if date_str:
                                    try:
                                        # Format usually "2026-08-28T08:30:00-04:00"
                                        dt = datetime.fromisoformat(date_str).astimezone(timezone.utc)
                                        parsed_events.append({
                                            "time": dt,
                                            "name": title,
                                            "impact": impact,
                                            "currency": item.get("country", "")
                                        })
                                    except Exception as e:
                                        logger.error(f"Error parsing date {date_str}: {e}")
                    
                    # Sort by time
                    self.events = sorted(parsed_events, key=lambda x: x["time"])
                    self.last_update = datetime.now(timezone.utc)
                    logger.info(f"Updated economic calendar, found {len(self.events)} high-impact events.")
            except Exception as e:
                logger.error(f"Failed to update economic calendar: {e}")

    async def get_upcoming_events(self, hours: int = 24) -> List[Dict]:
        async with self._lock:
            now = datetime.now(timezone.utc)
            cutoff = now + timedelta(hours=hours)
            return [e for e in self.events if now <= e["time"] <= cutoff]

    async def is_news_blackout(self, buffer_minutes: int = 15) -> bool:
        async with self._lock:
            now = datetime.now(timezone.utc)
            for e in self.events:
                dt = e["time"]
                delta = abs((dt - now).total_seconds()) / 60.0
                if delta <= buffer_minutes:
                    return True
            return False

    async def get_next_event(self) -> Optional[Dict]:
        async with self._lock:
            now = datetime.now(timezone.utc)
            for e in self.events:
                if e["time"] >= now:
                    return e
            return None
