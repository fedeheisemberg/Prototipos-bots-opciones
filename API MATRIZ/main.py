"""
Bot Avanzado de Opciones para Matba Rofex (Argentina)
Autor: Experto en Mercados Financieros
Version: 1.2
Fecha: Agosto 2023
"""

# ========================
# MÓDULO DE CONFIGURACIÓN
# ========================
import requests
import json
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class Config:
    API_BASE_URL = "https://api.remarkets-primary.com.ar"
    ACCOUNT_ID = "TU_CUENTA"
    RISK_LIMIT = 0.02  # 2% de capital por operación
    VOLATILITY_WINDOW = 20  # Días para cálculo de volatilidad histórica
    SYMBOL_MAP = {
        'DLR': {'cfi': 'FXXXSX', 'multiplier': 1000},
        'GGAL': {'cfi': 'OCAFPS', 'multiplier': 100}
    }

# ==========================
# MÓDULO DE AUTENTICACIÓN
# ==========================
class AuthManager:
    def __init__(self, username, password):
        self._token = None
        self._username = username
        self._password = password
        
    def get_token(self):
        url = f"{Config.API_BASE_URL}/auth/getToken"
        headers = {
            "X-Username": self._username,
            "X-Password": self._password
        }
        response = requests.post(url, headers=headers)
        if response.status_code == 200:
            self._token = response.headers.get("X-Auth-Token")
            return self._token
        else:
            raise Exception(f"Error de autenticación: {response.text}")

# ==========================
# MÓDULO DE MARKET DATA
# ==========================
class MarketData:
    def __init__(self, auth):
        self.auth = auth
        
    def get_real_time_data(self, symbol, entries="BI,OF,LA,OP,CL,SE,OI"):
        url = f"{Config.API_BASE_URL}/rest/marketdata/get"
        headers = {"X-Auth-Token": self.auth.get_token()}
        params = {
            "marketId": "ROFX",
            "symbol": symbol,
            "entries": entries,
            "depth": 5
        }
        response = requests.get(url, headers=headers, params=params)
        return response.json() if response.status_code == 200 else None

    def get_historical_volatility(self, symbol, days=Config.VOLATILITY_WINDOW):
        url = f"{Config.API_BASE_URL}/rest/data/getTrades"
        headers = {"X-Auth-Token": self.auth.get_token()}
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        params = {
            "marketId": "ROFX",
            "symbol": symbol,
            "dateFrom": start_date.strftime("%Y-%m-%d"),
            "dateTo": end_date.strftime("%Y-%m-%d")
        }
        
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json().get('trades', [])
            closes = [float(trade['price']) for trade in data]
            returns = np.log(np.array(closes[1:]) / np.array(closes[:-1]))
            return np.std(returns) * np.sqrt(252)  # Volatilidad anualizada
        return 0.0

# ==========================
# MÓDULO DE GESTIÓN DE RIESGO
# ==========================
class RiskManager:
    def __init__(self, auth):
        self.auth = auth
        
    def get_account_balance(self):
        url = f"{Config.API_BASE_URL}/rest/risk/accountReport/{Config.ACCOUNT_ID}"
        headers = {"X-Auth-Token": self.auth.get_token()}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return float(response.json()['accountData']['availableToCollateral'])
        return 0.0

    def calculate_position_size(self, premium, stop_loss_pct=0.10):
        balance = self.get_account_balance()
        max_risk = balance * Config.RISK_LIMIT
        return int(max_risk / (premium * stop_loss_pct))

# ==========================
# MÓDULO DE EJECUCIÓN DE ÓRDENES
# ==========================
class OrderManager:
    def __init__(self, auth):
        self.auth = auth
        
    def send_order(self, order_params):
        url = f"{Config.API_BASE_URL}/rest/order/newSingleOrder"
        headers = {"X-Auth-Token": self.auth.get_token()}
        
        default_params = {
            "marketId": "ROFX",
            "timeInForce": "DAY",
            "iceberg": False,
            "cancelPrevious": False,
            "account": Config.ACCOUNT_ID
        }
        
        response = requests.get(url, headers=headers, params={**default_params, **order_params})
        return response.json() if response.status_code == 200 else None

# ==========================
# ESTRATEGIAS COMPLETAS
# ==========================
class OptionsStrategies:
    def __init__(self, auth):
        self.md = MarketData(auth)
        self.om = OrderManager(auth)
        self.rm = RiskManager(auth)
        self.symbol_config = Config.SYMBOL_MAP

    # --------------------------------------------------
    # 1. BULL/BEAR SPREADS
    # --------------------------------------------------
    def vertical_spread(self, strategy_type, symbol, expiration, short_strike, long_strike, contracts=1):
        """
        Estrategia genérica para spreads verticales
        Types: 'bull_call', 'bear_put', 'bear_call', 'bull_put'
        """
        option_type = 'C' if 'call' in strategy_type else 'P'
        multiplier = self.symbol_config[symbol]['multiplier']
        
        # Construir símbolos de opciones
        short_leg = f"{symbol}{expiration}{option_type}{short_strike}"
        long_leg = f"{symbol}{expiration}{option_type}{long_strike}"
        
        # Obtener precios en tiempo real
        px_short = self.md.get_real_time_data(short_leg)['marketData']['LA']['price']
        px_long = self.md.get_real_time_data(long_leg)['marketData']['LA']['price']
        
        # Determinar dirección del spread
        if strategy_type in ['bull_call', 'bear_put']:
            debit = px_long - px_short
            side_long = 'BUY'
            side_short = 'SELL'
        else:
            debit = px_short - px_long
            side_long = 'SELL'
            side_short = 'BUY'
        
        # Calcular tamaño de posición
        position_size = self.rm.calculate_position_size(debit) * contracts
        
        # Ejecutar órdenes
        orders = [
            self.om.send_order({
                "symbol": long_leg,
                "orderQty": position_size,
                "price": px_long,
                "ordType": "LIMIT",
                "side": side_long
            }),
            self.om.send_order({
                "symbol": short_leg,
                "orderQty": position_size,
                "price": px_short,
                "ordType": "LIMIT",
                "side": side_short
            })
        ]
        
        return {
            "strategy": strategy_type,
            "net_debit": debit * multiplier,
            "max_profit": (long_strike - short_strike - debit) * multiplier if 'bull' in strategy_type else (short_strike - long_strike - debit) * multiplier,
            "orders": orders
        }

    # --------------------------------------------------
    # 2. IRON CONDOR
    # --------------------------------------------------
    def iron_condor(self, symbol, expiration, put_spread, call_spread, contracts=1):
        """
        Iron Condor: 
        - Sell PUT (K1)
        - Buy PUT (K2)
        - Sell CALL (K3)
        - Buy CALL (K4)
        Donde K1 < K2 < K3 < K4
        """
        # Construir símbolos
        put_short = f"{symbol}{expiration}P{put_spread[0]}"
        put_long = f"{symbol}{expiration}P{put_spread[1]}"
        call_short = f"{symbol}{expiration}C{call_spread[0]}"
        call_long = f"{symbol}{expiration}C{call_spread[1]}"
        
        # Obtener primas
        px_put_short = self.md.get_real_time_data(put_short)['marketData']['LA']['price']
        px_put_long = self.md.get_real_time_data(put_long)['marketData']['LA']['price']
        px_call_short = self.md.get_real_time_data(call_short)['marketData']['LA']['price']
        px_call_long = self.md.get_real_time_data(call_long)['marketData']['LA']['price']
        
        # Calcular crédito neto
        net_credit = (px_put_short - px_put_long) + (px_call_short - px_call_long)
        position_size = self.rm.calculate_position_size(net_credit) * contracts
        
        # Ejecutar órdenes
        orders = [
            # Put Spread
            self.om.send_order({"symbol": put_short, "side": "SELL", "orderQty": position_size, "price": px_put_short}),
            self.om.send_order({"symbol": put_long, "side": "BUY", "orderQty": position_size, "price": px_put_long}),
            # Call Spread
            self.om.send_order({"symbol": call_short, "side": "SELL", "orderQty": position_size, "price": px_call_short}),
            self.om.send_order({"symbol": call_long, "side": "BUY", "orderQty": position_size, "price": px_call_long})
        ]
        
        return {
            "strategy": "iron_condor",
            "net_credit": net_credit * self.symbol_config[symbol]['multiplier'],
            "max_loss": (put_spread[1] - put_spread[0] + call_spread[1] - call_spread[0] - net_credit) * self.symbol_config[symbol]['multiplier'],
            "orders": orders
        }

    # --------------------------------------------------
    # 3. BUTTERFLY SPREAD
    # --------------------------------------------------
    def butterfly_spread(self, strategy_type, symbol, expiration, lower_strike, middle_strike, upper_strike, contracts=1):
        """
        Butterfly Spread (Call o Put)
        - Buy 1 K1
        - Sell 2 K2
        - Buy 1 K3
        """
        option_type = 'C' if strategy_type == 'call' else 'P'
        multiplier = self.symbol_config[symbol]['multiplier']
        
        # Construir símbolos
        leg1 = f"{symbol}{expiration}{option_type}{lower_strike}"
        leg2 = f"{symbol}{expiration}{option_type}{middle_strike}"
        leg3 = f"{symbol}{expiration}{option_type}{upper_strike}"
        
        # Obtener primas
        px_leg1 = self.md.get_real_time_data(leg1)['marketData']['LA']['price']
        px_leg2 = self.md.get_real_time_data(leg2)['marketData']['LA']['price']
        px_leg3 = self.md.get_real_time_data(leg3)['marketData']['LA']['price']
        
        # Calcular costo/net debit
        net_debit = px_leg1 - (2 * px_leg2) + px_leg3
        position_size = self.rm.calculate_position_size(abs(net_debit)) * contracts
        
        # Ejecutar órdenes
        orders = [
            self.om.send_order({"symbol": leg1, "side": "BUY", "orderQty": position_size, "price": px_leg1}),
            self.om.send_order({"symbol": leg2, "side": "SELL", "orderQty": position_size * 2, "price": px_leg2}),
            self.om.send_order({"symbol": leg3, "side": "BUY", "orderQty": position_size, "price": px_leg3})
        ]
        
        return {
            "strategy": f"{strategy_type}_butterfly",
            "net_cost": net_debit * multiplier,
            "max_profit": (middle_strike - lower_strike - net_debit) * multiplier,
            "orders": orders
        }

    # --------------------------------------------------
    # 4. RATIO SPREADS
    # --------------------------------------------------
    def ratio_spread(self, strategy_type, symbol, expiration, long_strike, short_strike, ratio=2, contracts=1):
        """
        Ratio Spread (Call o Put)
        - Buy 1 ITM option
        - Sell X OTM options (ratio typically 2:1 or 3:1)
        """
        option_type = 'C' if strategy_type == 'call' else 'P'
        multiplier = self.symbol_config[symbol]['multiplier']
        
        # Construir símbolos
        long_leg = f"{symbol}{expiration}{option_type}{long_strike}"
        short_leg = f"{symbol}{expiration}{option_type}{short_strike}"
        
        # Obtener primas
        px_long = self.md.get_real_time_data(long_leg)['marketData']['LA']['price']
        px_short = self.md.get_real_time_data(short_leg)['marketData']['LA']['price']
        
        # Calcular crédito/débito
        net_credit = (px_short * ratio) - px_long
        position_size = self.rm.calculate_position_size(net_credit) * contracts
        
        # Ejecutar órdenes
        orders = [
            self.om.send_order({"symbol": long_leg, "side": "BUY", "orderQty": position_size, "price": px_long}),
            self.om.send_order({"symbol": short_leg, "side": "SELL", "orderQty": position_size * ratio, "price": px_short})
        ]
        
        return {
            "strategy": f"{strategy_type}_ratio_{ratio}1",
            "net_credit": net_credit * multiplier,
            "max_risk": "Unlimited" if strategy_type == 'call' else (long_strike - (net_credit/multiplier)) * multiplier,
            "orders": orders
        }

    # --------------------------------------------------
    # 5. STRADDLE/STRANGLE
    # --------------------------------------------------
    def volatility_play(self, strategy_type, symbol, expiration, strike1, strike2=None, contracts=1):
        """
        Estrategias de volatilidad:
        - Straddle (mismo strike)
        - Strangle (strikes diferentes)
        """
        if strategy_type == 'straddle':
            call_strike = put_strike = strike1
        else:
            call_strike, put_strike = sorted([strike1, strike2], reverse=True)
        
        call_symbol = f"{symbol}{expiration}C{call_strike}"
        put_symbol = f"{symbol}{expiration}P{put_strike}"
        
        px_call = self.md.get_real_time_data(call_symbol)['marketData']['LA']['price']
        px_put = self.md.get_real_time_data(put_symbol)['marketData']['LA']['price']
        
        total_cost = (px_call + px_put) * self.symbol_config[symbol]['multiplier']
        position_size = self.rm.calculate_position_size(total_cost) * contracts
        
        orders = [
            self.om.send_order({"symbol": call_symbol, "side": "BUY", "orderQty": position_size, "price": px_call}),
            self.om.send_order({"symbol": put_symbol, "side": "BUY", "orderQty": position_size, "price": px_put})
        ]
        
        return {
            "strategy": strategy_type,
            "total_cost": total_cost,
            "breakevens": [
                call_strike + total_cost,
                put_strike - total_cost
            ],
            "orders": orders
        }

# ==========================
# MAIN & EJECUCIÓN
# ==========================
if __name__ == "__main__":
    # Configurar credenciales
    auth = AuthManager("tu_usuario", "tu_password")
    
    # Ejemplo: Ejecutar Bull Call Spread en DLR
    strategies = OptionsStrategies(auth)
    result = strategies.bull_call_spread(
        symbol="DLR",
        expiration="DIC23",
        lower_strike=800,
        upper_strike=850
    )
    
    print(f"Resultado de la operación: {json.dumps(result, indent=2)}")