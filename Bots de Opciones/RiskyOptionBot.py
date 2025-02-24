from datetime import datetime
from ib_insync import *
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio

class RiskyOptionsBot:
    """Risky Options Bot (Python, Interactive Brokers)
        Compra contratos de SPY después de 3 cierres consecutivos al alza en velas de 5 minutos
        y establece un objetivo de ganancia en la siguiente vela"""

    def __init__(self, *args, **kwargs):
        print("Options Bot Running, connecting to IB...")
        
        # Conectar con Interactive Brokers
        try:
            self.ib = IB()
            self.ib.connect('127.0.0.1', 7497, clientId=1)
        except Exception as e:
            print(str(e))
        
        # Crear contrato del subyacente SPY
        self.underlying = Stock('SPY', 'SMART', 'USD')
        self.ib.qualifyContracts(self.underlying)
        
        print("Backfilling data to catch up ...")
        
        # Solicitar datos históricos en velas de 5 minutos
        self.data = self.ib.reqHistoricalData(
            self.underlying, endDateTime='', durationStr='2 D',
            barSizeSetting='5 mins', whatToShow='TRADES'
        )
        
        # Variable para controlar si estamos en una operación
        self.in_trade = False
        
        # Obtener cadenas de opciones disponibles para SPY
        self.chains = self.ib.reqSecDefOptParams(
            self.underlying.symbol, '', self.underlying.secType, self.underlying.conId
        )
        
        # Actualizar cadenas de opciones cada hora
        update_chain_scheduler = BackgroundScheduler(job_defaults={'max_instances': 2})
        update_chain_scheduler.add_job(func=self.update_options_chains, trigger='cron', hour='*')
        update_chain_scheduler.start()
        
        print("Running Live")
        
        # Configurar eventos de actualización de datos en streaming
        self.data.updateEvent += self.on_bar_update
        self.ib.execDetailsEvent += self.exec_status
        
        # Ejecutar el bot en bucle infinito
        self.ib.run()

    def update_options_chains(self):
        """Actualizar la lista de opciones disponibles"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            print("Updating options chains")
            
            self.chains = self.ib.reqSecDefOptParams(
                self.underlying.symbol, '', self.underlying.secType, self.underlying.conId
            )
        except Exception as e:
            print(str(e))

    def on_bar_update(self, bars: BarDataList, has_new_bar: bool):
        """Manejo de nueva vela de datos"""
        try:
            if has_new_bar:
                df = util.df(bars)  # Convertir datos en un DataFrame de Pandas
                
                if not self.in_trade:
                    print("Last Close : " + str(df.close.iloc[-1]))
                    
                    # Comprobar si hay 3 cierres consecutivos al alza
                    if df.close.iloc[-1] > df.close.iloc[-2] and df.close.iloc[-2] > df.close.iloc[-3]:
                        for optionschain in self.chains:
                            for strike in optionschain.strikes:
                                if strike > df.close.iloc[-1] + 5:
                                    print("Found 3 consecutive higher closers, entering trade.")
                                    
                                    self.options_contract = Option(
                                        self.underlying.symbol,
                                        optionschain.expirations[1],
                                        strike, 'C', 'SMART', tradingClass=self.underlying.symbol
                                    )
                                    
                                    options_order = MarketOrder("BUY", 1, account=self.ib.wrapper.accounts[-1])
                                    trade = self.ib.placeOrder(self.options_contract, options_order)
                                    self.lastEstimatedFillPrice = df.close.iloc[-1]
                                    self.in_trade = True
                                    return
            else:
                if df.close.iloc[-1] > self.lastEstimatedFillPrice:
                    options_order = MarketOrder("SELL", 1, account=self.ib.wrapper.accounts[-1])
        except Exception as e:
            print(str(e))

    def exec_status(self, trade: Trade, fill: Fill):
        """Manejo de ejecución de órdenes"""
        print("Filled")

# Instanciar la clase para iniciar el bot
RiskyOptionsBot()
