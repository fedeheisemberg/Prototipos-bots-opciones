"""
Bot Avanzado de Opciones para Matba Rofex (Argentina)
Autor: Experto en Mercados Financieros
Version: 1.3
Fecha: Febrero 2024
Modificado para soportar opciones de GGAL
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
        'GGAL': {
            'cfi': 'OCAFPS', 
            'multiplier': 100,
            'vencimientos': ['FEB', 'ABR', 'JUL', 'AGO', 'OCT', 'DIC'],
            'strike_divisor': 10  # Para convertir 40283 a 4028.30
        }
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

    def parse_ggal_strike(self, strike_str):
        """Convierte el strike de formato 40283 a 4028.30"""
        return float(strike_str) / self.symbol_config['GGAL']['strike_divisor']

    def format_ggal_option_symbol(self, base_symbol, expiration, option_type, strike):
        """
        Formatea el símbolo de la opción de GGAL
        Ejemplo: GGAL + FEB + C + 40283
        """
        # Asumimos que el strike viene como float (ej: 4028.30)
        strike_formatted = str(int(strike * self.symbol_config['GGAL']['strike_divisor']))
        return f"GFG{option_type}{strike_formatted}{expiration}"

    # --------------------------------------------------
    # 1. BULL/BEAR SPREADS
    # --------------------------------------------------
    def vertical_spread(self, strategy_type, symbol, expiration, short_strike, long_strike, contracts=1):
        """
        Estrategia genérica para spreads verticales
        Types: 'bull_call', 'bear_put', 'bear_call', 'bull_put'
        """
        if symbol == 'GGAL':
            # Convertir strikes si es necesario
            short_strike = self.parse_ggal_strike(str(short_strike))
            long_strike = self.parse_ggal_strike(str(long_strike))
            
        option_type = 'C' if 'call' in strategy_type else 'V'  # GGAL usa 'V' para puts
        multiplier = self.symbol_config[symbol]['multiplier']
        
        # Construir símbolos de opciones para GGAL
        short_leg = self.format_ggal_option_symbol(symbol, expiration, option_type, short_strike)
        long_leg = self.format_ggal_option_symbol(symbol, expiration, option_type, long_strike)
        
        # Obtener precios en tiempo real
        px_short = self.md.get_real_time_data(short_leg)['marketData']['LA']['price']
        px_long = self.md.get_real_time_data(long_leg)['marketData']['LA']['price']
        
        if strategy_type in ['bull_call', 'bear_put']:
            debit = px_long - px_short
            side_long = 'BUY'
            side_short = 'SELL'
        else:
            debit = px_short - px_long
            side_long = 'SELL'
            side_short = 'BUY'
        
        position_size = self.rm.calculate_position_size(debit) * contracts
        
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
        if symbol == 'GGAL':
            put_spread = [self.parse_ggal_strike(str(k)) for k in put_spread]
            call_spread = [self.parse_ggal_strike(str(k)) for k in call_spread]
            
        # Construir símbolos para GGAL
        put_short = self.format_ggal_option_symbol(symbol, expiration, 'V', put_spread[0])
        put_long = self.format_ggal_option_symbol(symbol, expiration, 'V', put_spread[1])
        call_short = self.format_ggal_option_symbol(symbol, expiration, 'C', call_spread[0])
        call_long = self.format_ggal_option_symbol(symbol, expiration, 'C', call_spread[1])
        
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
        if symbol == 'GGAL':
            lower_strike = self.parse_ggal_strike(str(lower_strike))
            middle_strike = self.parse_ggal_strike(str(middle_strike))
            upper_strike = self.parse_ggal_strike(str(upper_strike))
            
        option_type = 'C' if strategy_type == 'call' else 'V'
        multiplier = self.symbol_config[symbol]['multiplier']
        
        # Construir símbolos para GGAL
        leg1 = self.format_ggal_option_symbol(symbol, expiration, option_type, lower_strike)
        leg2 = self.format_ggal_option_symbol(symbol, expiration, option_type, middle_strike)
        leg3 = self.format_ggal_option_symbol(symbol, expiration, option_type, upper_strike)
        
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
        if symbol == 'GGAL':
            long_strike = self.parse_ggal_strike(str(long_strike))
            short_strike = self.parse_ggal_strike(str(short_strike))
            
        option_type = 'C' if strategy_type == 'call' else 'V'
        multiplier = self.symbol_config[symbol]['multiplier']
        
        # Construir símbolos para GGAL
        long_leg = self.format_ggal_option_symbol(symbol, expiration, option_type, long_strike)
        short_leg = self.format_ggal_option_symbol(symbol, expiration, option_type, short_strike)
        
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
        if symbol == 'GGAL':
            strike1 = self.parse_ggal_strike(str(strike1))
            if strike2:
                strike2 = self.parse_ggal_strike(str(strike2))
                
        if strategy_type == 'straddle':
            call_strike = put_strike = strike1
        else:
            call_strike, put_strike = sorted([strike1, strike2], reverse=True)
        
        # Construir símbolos para GGAL
        call_symbol = self.format_ggal_option_symbol(symbol, expiration, 'C', call_strike)
        put_symbol = self.format_ggal_option_symbol(symbol, expiration, 'V', put_strike)
        
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
                call_strike + total_cost/self.symbol_config[symbol]['multiplier'],
                put_strike - total_cost/self.symbol_config[symbol]['multiplier']
            ],
            "orders": orders
        }

# ==========================
# MAIN & EJECUCIÓN
# ==========================
if __name__ == "__main__":
    # Configurar credenciales
    auth = AuthManager("tu_usuario", "tu_password")
    
    # Ejemplo de uso para GGAL
    strategies = OptionsStrategies(auth)
    
    # Ejemplo 1: Bull Call Spread en GGAL
    result_bull_call = strategies.vertical_spread(
        strategy_type='bull_call',
        symbol='GGAL',
        expiration='FEB',  # Para febrero
        short_strike=40283,  # Representa $4028.30
        long_strike=45783,  # Representa $4578.30
        contracts=1
    )
    
    # Ejemplo 2: Iron Condor en GGAL
    result_iron_condor = strategies.iron_condor(
        symbol='GGAL',
        expiration='FEB',
        put_spread=[40283, 45783],  # Strikes para put spread
        call_spread=[65783, 71783],  # Strikes para call spread
        contracts=1
    )
    
    print("Resultado Bull Call Spread:", json.dumps(result_bull_call, indent=2))
    print("Resultado Iron Condor:", json.dumps(result_iron_condor, indent=2))
