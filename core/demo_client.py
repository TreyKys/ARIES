import aiohttp
import time
import hashlib
import hmac
import urllib.parse
from config.pairs import get_pair_by_symbol

class BinanceDemoClient:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = 'https://demo-fapi.binance.com'

    def _sign(self, params):
        params['timestamp'] = int(time.time() * 1000)
        query_string = urllib.parse.urlencode(params)
        signature = hmac.new(self.api_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        params['signature'] = signature
        return params

    async def _post(self, endpoint, params):
        url = f"{self.base_url}{endpoint}"
        signed_params = self._sign(params)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers={'X-MBX-APIKEY': self.api_key}, data=signed_params) as resp:
                data = await resp.json()
                if 'code' in data and data['code'] < 0:
                    raise Exception(data['msg'])
                return data
                
    async def _get(self, endpoint, params=None):
        if params is None:
            params = {}
        url = f"{self.base_url}{endpoint}"
        signed_params = self._sign(params)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={'X-MBX-APIKEY': self.api_key}, params=signed_params) as resp:
                data = await resp.json()
                if 'code' in data and data['code'] < 0:
                    raise Exception(data['msg'])
                return data

    async def fetch_balance(self):
        # We only implement this method for backwards compatibility with patch_raw_balance.py which we can revert or keep!
        # Actually I patched engine.py to bypass fetch_balance entirely in _heartbeat_loop!
        # But wait, execution gate still uses fetch_balance!
        data = await self._get('/fapi/v2/account')
        return data

    async def set_leverage(self, leverage, symbol):
        sym = symbol.replace('/', '')
        return await self._post('/fapi/v1/leverage', {'symbol': sym, 'leverage': leverage})
        
    async def load_markets(self):
        pass # No-op since we use config

    def amount_to_precision(self, symbol, amount):
        pair = get_pair_by_symbol(symbol)
        prec = pair.qty_precision if pair else 3
        return f"{amount:.{prec}f}"

    def price_to_precision(self, symbol, price):
        pair = get_pair_by_symbol(symbol)
        prec = pair.price_precision if pair else 2
        return f"{price:.{prec}f}"

    async def create_market_order(self, symbol, side, amount):
        sym = symbol.replace('/', '')
        params = {
            'symbol': sym,
            'side': side.upper(),
            'type': 'MARKET',
            'quantity': amount
        }
        return await self._post('/fapi/v1/order', params)

    async def create_order(self, symbol, type_, side, amount, price, params):
        sym = symbol.replace('/', '')
        api_params = {
            'symbol': sym,
            'side': side.upper(),
            'type': type_.upper(),
            'quantity': amount
        }
        if 'stopPrice' in params:
            api_params['stopPrice'] = params['stopPrice']
        if 'reduceOnly' in params and params['reduceOnly']:
            api_params['reduceOnly'] = 'true'
            
        return await self._post('/fapi/v1/order', api_params)

