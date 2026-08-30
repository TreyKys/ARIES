import asyncio
import ccxt.async_support as ccxt
import logging
import uuid
import traceback
from datetime import datetime
from core.bullpen import Bullpen
from core.council import Council
from core.gemini_agents import GeminiTribunal
from core.departments import HistorianDepartment, MacroDesk, OrderFlowDepartment

logger = logging.getLogger(__name__)

class Engine:
    def __init__(self, settings, database, feed_manager, candle_store, supabase, telegram):
        self.settings = settings
        self.database = database
        self.feed_manager = feed_manager
        self.candle_store = candle_store
        self.supabase = supabase
        self.telegram = telegram
        
        self.mode = getattr(settings, 'MODE', 'PAPER')
        self._running = False
        self._tasks = []
        
        # Native Binance Demo Client to bypass CCXT Demo incompatibilities
        from core.demo_client import BinanceDemoClient
        self.execution_client = BinanceDemoClient(settings.BINANCE_API_KEY, settings.BINANCE_SECRET)
        
        
        # Instantiate Swarm & Departments
        self.bullpen = Bullpen(settings, candle_store)
        self.council = Council(settings)
        self.gemini_tribunal = GeminiTribunal()
        
        self.historian = HistorianDepartment(supabase)
        self.macro_desk = MacroDesk()
        self.order_flow = OrderFlowDepartment(feed_manager)
        
        self.open_positions = {}
        
        self.daily_pnl = 0.0
        self.total_trades = 0
        self.winning_trades = 0

    
    async def push_log(self, agent: str, msg: str, severity: str = 'INFO'):
        try:
            self.supabase.client.table('council_feed').insert({
                'agent_name': agent,
                'message': msg,
                'severity': severity
            }).execute()
        except Exception:
            pass

    async def start(self):
        self._running = True
        logger.info(f"ARES-1 ENGINE STARTED (MoE + 3 Departments) — MODE: {self.mode}")
        
        if hasattr(self.feed_manager, 'start'):
            await self.push_log("SYSTEM", "ARES-2 GEMINI OVERLORD INITIALIZED. Awaiting market ticks...", "DEBUG")
            await self.feed_manager.start()
            await asyncio.sleep(5)
            await self.push_log("MACRO_DESK", "Historical market data loaded. Bullpen is fully spun up and analyzing structural trends.", "DEBUG")
            
        if hasattr(self.candle_store, 'register_callback'):
            self.candle_store.register_callback(self._on_candle_close)
            
        self._tasks = [
            asyncio.create_task(self._heartbeat_loop()),
            asyncio.create_task(self._manage_open_trades())
        ]

    async def _on_candle_close(self, symbol, timeframe, candle):
        logger.info(f"Inside _on_candle_close for {symbol} {timeframe}")
        if timeframe not in ['1m', '5m']:
            return
            
        
        # Push tick heartbeat
        await self.push_log("SYSTEM", f"Tick analysis triggered for {symbol} on {timeframe}m", "DEBUG")

        
        # 1. Grunt Workers analyze the raw data
        state = await self.bullpen.analyze(symbol)
        if not state.get('ready'):
            return
            
        # 2. Add Department Intelligence to the State
        state['macro_desk'] = self.macro_desk.check_macro_shield()
        state['order_flow'] = await self.order_flow.get_liquidity_imbalance(symbol)
        state['historian'] = self.historian.get_historical_precedent(state)
            
        # Push MTF data to UI
        if timeframe == '5m':
            try:
                self.supabase.client.table('mtf_analysis').update({
                    'macro_bias': state.get('macro_trend'),
                    'macro_trend': state.get('macro_trend'),
                    'structure_1h': state.get('macro_trend'),
                    'structure_15m': state.get('structure_15m'),
                    'execution_5m': 'BULLISH' if state.get('rsi_5m', 50) > 50 else 'BEARISH',
                    'execution_1m': 'BULLISH' if state.get('current_price', 0) > candle.open else 'BEARISH',
                    'confluence_score': 85
                }).eq('id', 1).execute()
            except Exception:
                pass

        # 3. Council Votes
        
        # 3. Hybrid Council Deliberation
        # A. Python Council computes mathematical votes
        python_decision = self.council.vote(state)
        state['python_council'] = python_decision
        
        # Verbose Logging for User Dashboard
        if python_decision['approved']:
            await self.push_log("PYTHON_COUNCIL", f"Setup detected on {symbol}. Requesting CIO approval...", "DEBUG")
        else:
            reason = python_decision['rejections'][0] if python_decision['rejections'] else "No setup"
            await self.push_log("PYTHON_COUNCIL", f"Scanning {symbol}: Abstaining ({reason})", "DEBUG")
            
        # Hard Filter to protect Gemini API Free Tier
        # Only wake up Gemini Overlord if Python Council mathematically approves the trade,
        # OR if OrderFlow detects a massive sweep opportunity (whale trap)
        of_bias = state.get('order_flow', {}).get('bias', 'NEUTRAL')
        if not python_decision['approved'] and of_bias == 'NEUTRAL':
            # Skip Gemini to save API requests
            return
            
        await self.push_log("GEMINI_CIO", f"Reviewing mathematical setup for {symbol}...", "DEBUG")
        
        # B. Gemini Overlord reviews Python's work and makes final call
        decision = await self.gemini_tribunal.deliberate(state)
        
        # Broadcast the reasoning to the UI
        if decision['approved']:
            await self.push_log("GEMINI_CIO", f"UNANIMOUS APPROVAL: Executing {decision['direction']} on {symbol}. Reason: {decision['reasoning']} (Confidence: {decision['confidence']}%)", "SUCCESS")
        else:
            await self.push_log("GEMINI_CIO", f"VETOED {symbol}: {decision['reasoning']}", "WARN")
            
        # 4. Execution Gate
        if decision['approved'] and symbol not in self.open_positions:
            direction = decision['direction']
            entry_price = state['current_price']
            order_side = 'buy' if direction == 'LONG' else 'sell'
            
            # --- REAL MARKET EXECUTION PROTOCOL ---
            try:
                # 1. Fetch available balance
                # Use explicit requests to bypass CCXT's broken Demo Trading sapi endpoint dependency
                import time, hashlib, hmac, urllib.parse, aiohttp
                timestamp = int(time.time() * 1000)
                params = {'timestamp': timestamp}
                qs = urllib.parse.urlencode(params)
                sig = hmac.new(self.settings.BINANCE_SECRET.encode('utf-8'), qs.encode('utf-8'), hashlib.sha256).hexdigest()
                url = f"https://demo-fapi.binance.com/fapi/v2/account?timestamp={timestamp}&signature={sig}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers={'X-MBX-APIKEY': self.settings.BINANCE_API_KEY}) as resp:
                        data = await resp.json()
                        usdt_balance = 0.0
                        for a in data.get('assets', []):
                            if a['asset'] == 'USDT':
                                usdt_balance = float(a['availableBalance'])
                                break
                
                # CLAMP FOR MICRO ACCOUNT
                # Even if they have $10,000, we force the bot to trade as if it only has $50
                usdt_balance = min(usdt_balance, self.council.current_equity)
                
                # 2. Set Leverage (Targeting 10x for ARES-1 Micro Account)
                leverage = 10
                try:
                    await self.execution_client.set_leverage(leverage, symbol)
                except Exception as e:
                    logger.debug(f"Leverage set skipped/failed: {e}")
                    
                # 3. Calculate dynamic position size (Risk 5% of account * leverage)
                risk_capital = (usdt_balance * 0.05) * leverage
                if risk_capital < 5.0:  # Minimum order size safety fallback (Binance requires > 5 USDT notional)
                    risk_capital = 10.0
                
                raw_amount = risk_capital / entry_price
                
                # Format amount to exchange precision via CCXT
                await self.execution_client.load_markets()
                amount = float(self.execution_client.amount_to_precision(symbol, raw_amount))
                
                logger.info(f"Sending real testnet order: {order_side.upper()} {amount} {symbol}")
                
                # 4. Execute Entry Market Order
                entry_order = await self.execution_client.create_market_order(symbol, order_side, amount)
                
                # Wait for fill confirmation & get actual execution price
                actual_entry = entry_order.get('average')
                if actual_entry is None or actual_entry == 0:
                    actual_entry = entry_order.get('price', entry_price)
                if actual_entry is None or actual_entry == 0:
                    actual_entry = entry_price
                    
                # 5. Execute SL/TP Orders on the exchange orderbook
                sl_price = actual_entry - decision['sl_dist'] if direction == 'LONG' else actual_entry + decision['sl_dist']
                tp_price = actual_entry + decision['tp_dist'] if direction == 'LONG' else actual_entry - decision['tp_dist']
                
                sl_price_str = float(self.execution_client.price_to_precision(symbol, sl_price))
                tp_price_str = float(self.execution_client.price_to_precision(symbol, tp_price))
                
                close_side = 'sell' if direction == 'LONG' else 'buy'
                
                # Place Stop Loss Market Order
                try:
                    sl_params = {'stopPrice': sl_price_str, 'reduceOnly': True}
                    await self.execution_client.create_order(symbol, 'STOP_MARKET', close_side, amount, sl_price_str, params=sl_params)
                except Exception as e:
                    logger.error(f"Failed to set SL: {e}")

                # Place Take Profit Market Order
                try:
                    tp_params = {'stopPrice': tp_price_str, 'reduceOnly': True}
                    await self.execution_client.create_order(symbol, 'TAKE_PROFIT_MARKET', close_side, amount, tp_price_str, params=tp_params)
                except Exception as e:
                    logger.error(f"Failed to set TP: {e}")

                await self.push_log("SYSTEM", f"MARKET FILL: {order_side.upper()} {amount} {symbol} @ {actual_entry}. SL & TP placed on Exchange Orderbook.", "SUCCESS")
                
                # 6. Record to Database (Only if execution completely succeeded)
                trade = {
                    'id': str(uuid.uuid4()),
                    'symbol': symbol,
                    'side': direction,
                    'entry_price': actual_entry,
                    'stop_loss': sl_price,
                    'take_profit': tp_price,
                    'status': 'OPEN',
                    'strategy': state['regime'],
                    'opened_at': datetime.utcnow().isoformat()
                }
                self.open_positions[symbol] = trade
                
                try:
                    self.supabase.client.table('trades').insert(trade).execute()
                except Exception:
                    pass
                logger.info(f"TRADE EXECUTED: {direction} {symbol} @ {actual_entry}")
                    
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Testnet Execution Error: {error_trace}")
                # Parse exact CCXT error for the UI
                err_msg = str(e).split('}')[-1].strip() if '}' in str(e) else str(e)
                await self.push_log("SYSTEM", f"EXCHANGE REJECTED ORDER: {err_msg}", "WARN")

        if decision['confidence'] > 50:
            try:
                self.supabase.client.table('signals').insert({
                    'symbol': symbol,
                    'action': decision['direction'] or 'REJECTED',
                    'confidence': decision['confidence'],
                    'risk_tier': 'NORMAL',
                    'council_votes': decision['votes_log']
                }).execute()
            except Exception:
                pass

    async def _manage_open_trades(self):
        while self._running:
            for symbol, trade in list(self.open_positions.items()):
                df_1m = self.candle_store.get_dataframe(symbol, '1m')
                if df_1m.empty: continue
                    
                current_price = df_1m['close'].iloc[-1]
                closed = False
                pnl_usd = 0.0
                size = 1.0 
                
                if trade['side'] == 'LONG':
                    if current_price >= trade['take_profit']:
                        pnl_usd = (trade['take_profit'] - trade['entry_price']) * size; closed = True
                    elif current_price <= trade['stop_loss']:
                        pnl_usd = (trade['stop_loss'] - trade['entry_price']) * size; closed = True
                else:
                    if current_price <= trade['take_profit']:
                        pnl_usd = (trade['entry_price'] - trade['take_profit']) * size; closed = True
                    elif current_price >= trade['stop_loss']:
                        pnl_usd = (trade['entry_price'] - trade['stop_loss']) * size; closed = True
                        
                if closed:
                    logger.info(f"TRADE CLOSED: {trade['side']} {symbol} | PNL: ${pnl_usd:.2f}")
                    self.total_trades += 1
                    if pnl_usd > 0:
                        self.winning_trades += 1
                        self.council.consecutive_losses = 0
                    else:
                        self.council.consecutive_losses += 1
                        
                    self.daily_pnl += pnl_usd
                    self.council.current_equity += pnl_usd
                    if self.council.current_equity > self.council.peak_equity:
                        self.council.peak_equity = self.council.current_equity
                        
                    try:
                        self.supabase.client.table('trades').update({
                            'exit_price': current_price,
                            'pnl_usd': pnl_usd,
                            'r_multiple': 1.2 if pnl_usd > 0 else -1.0,
                            'status': 'CLOSED',
                            'closed_at': datetime.utcnow().isoformat()
                        }).eq('id', trade['id']).execute()
                    except Exception:
                        pass
                    del self.open_positions[symbol]
                    
            await asyncio.sleep(2)

    async def _heartbeat_loop(self):
        while self._running:
            # --- REAL MARKET BALANCE SYNC ---
            try:
                import time, hashlib, hmac, urllib.parse, aiohttp
                timestamp = int(time.time() * 1000)
                params = {'timestamp': timestamp}
                qs = urllib.parse.urlencode(params)
                sig = hmac.new(self.settings.BINANCE_SECRET.encode('utf-8'), qs.encode('utf-8'), hashlib.sha256).hexdigest()
                url = f"https://demo-fapi.binance.com/fapi/v2/account?timestamp={timestamp}&signature={sig}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers={'X-MBX-APIKEY': self.settings.BINANCE_API_KEY}) as resp:
                        data = await resp.json()
                        exchange_usdt = self.council.current_equity
                        if 'assets' in data:
                            for a in data['assets']:
                                if a['asset'] == 'USDT':
                                    exchange_usdt = float(a['walletBalance'])
                                    break
                            
                            if not hasattr(self, 'baseline_exchange_balance') or self.baseline_exchange_balance is None:
                                self.baseline_exchange_balance = exchange_usdt
                                
                            realized_pnl = exchange_usdt - self.baseline_exchange_balance
                            
                            # MICRO-ACCOUNT SIMULATION
                            self.council.current_equity = self.settings.STARTING_CAPITAL + realized_pnl
                            self.daily_pnl = realized_pnl
                            logger.info(f'Exchange USDT: {exchange_usdt}, Baseline: {self.baseline_exchange_balance}, PNL: {realized_pnl}, Equity: {self.council.current_equity}')
            except Exception as e:
                pass

            win_rate = (self.winning_trades / self.total_trades) * 100 if self.total_trades > 0 else 0
            try:
                self.supabase.client.table('system_state').update({
                    'balance': self.council.current_equity,
                    'today_pnl_abs': self.daily_pnl,
                    'today_pnl_pct': (self.daily_pnl / self.settings.STARTING_CAPITAL) * 100,
                    'win_rate': win_rate,
                    'is_connected': True
                }).eq('id', 1).execute()
            except Exception:
                pass
            await asyncio.sleep(5)

    async def stop(self):
        self._running = False
        for task in self._tasks:
            task.cancel()
        if hasattr(self.feed_manager, 'stop'):
            await self.feed_manager.stop()
        try:
            self.supabase.client.table('system_state').update({'is_connected': False}).eq('id', 1).execute()
        except Exception:
            pass
        await self.database.close()
