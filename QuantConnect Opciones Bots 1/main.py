from datetime import timedelta
from QuantConnect.Data.Custom.CBOE import *

class OptionChainProviderPutProtection(QCAlgorithm):

    def Initialize(self):
        # Establecer la fecha de inicio y fin para la prueba retrospectiva (backtest)
        self.SetStartDate(2017, 10, 1)
        self.SetEndDate(2020, 10, 1)
        
        # Establecer el saldo inicial para la simulación
        self.SetCash(100000)
        
        # Agregar el activo subyacente (SPY en este caso)
        self.equity = self.AddEquity("SPY", Resolution.Minute)
        self.equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.symbol = self.equity.Symbol
        
        # Agregar los datos del índice de volatilidad VIX
        self.vix = self.AddData(CBOE, "VIX").Symbol
        
        # Inicializar el indicador de volatilidad implícita (IV)
        self.rank = 0
        
        # Inicializar la variable del contrato de opción como una cadena vacía
        self.contract = str()
        self.contractsAdded = set()
        
        # Parámetros del algoritmo ------------------------------------------------------------
        self.DaysBeforeExp = 2  # Número de días antes del vencimiento para salir de la posición
        self.DTE = 25  # Días objetivo hasta el vencimiento de la opción
        self.OTM = 0.01  # Porcentaje fuera del dinero (OTM) para la opción put
        self.lookbackIV = 150  # Periodo de observación para el cálculo del IV (en días)
        self.IVlvl = 0.5  # Nivel del IV en el que se entra en la posición
        self.percentage = 0.9  # Porcentaje del portafolio asignado al activo subyacente
        self.options_alloc = 90  # Cantidad de acciones cubiertas por cada opción (100 sería el balanceado)
        # -----------------------------------------------------------------------------------
    
        # Programar la función de graficado 30 minutos después de la apertura del mercado
        self.Schedule.On(self.DateRules.EveryDay(self.symbol), \
                        self.TimeRules.AfterMarketOpen(self.symbol, 30), \
                        self.Plotting)
        
        # Programar la actualización del indicador de volatilidad VIXRank
        self.Schedule.On(self.DateRules.EveryDay(self.symbol), \
                        self.TimeRules.AfterMarketOpen(self.symbol, 30), \
                        self.VIXRank)
        
        # Establecer el periodo de calentamiento para el indicador IV
        self.SetWarmUp(timedelta(self.lookbackIV)) 

    def VIXRank(self):
        # Obtener el historial del VIX y calcular su nivel relativo
        history = self.History(CBOE, self.vix, self.lookbackIV, Resolution.Daily)
        self.rank = ((self.Securities[self.vix].Price - min(history["low"])) / \
                     (max(history["high"]) - min(history["low"])))
 
    def OnData(self, data):
        ''' Evento OnData: punto de entrada principal del algoritmo.
            Recibe nuevos datos de mercado y ejecuta la lógica de inversión. '''
        
        if self.IsWarmingUp:
            return
        
        # Comprar el activo subyacente si aún no está en la cartera
        if not self.Portfolio[self.symbol].Invested:
            self.SetHoldings(self.symbol, self.percentage)
        
        # Comprar una opción put si el VIX está relativamente alto
        if self.rank > self.IVlvl:
            self.BuyPut(data)
        
        # Cerrar la opción put si está cerca de su vencimiento
        if self.contract:
            if (self.contract.ID.Date - self.Time) <= timedelta(self.DaysBeforeExp):
                self.Liquidate(self.contract)
                self.Log("Cerrado: muy cerca del vencimiento")
                self.contract = str()

    def BuyPut(self, data):
        # Obtener datos de opciones disponibles
        if self.contract == str():
            self.contract = self.OptionsFilter(data)
            return
        
        # Si aún no se ha comprado la opción y los datos están disponibles, ejecutar la compra
        elif not self.Portfolio[self.contract].Invested and data.ContainsKey(self.contract):
            self.Buy(self.contract, round(self.Portfolio[self.symbol].Quantity / self.options_alloc))

    def OptionsFilter(self, data):
        ''' Filtra la lista de contratos de opciones disponibles para el activo subyacente.
            Se selecciona la opción put más adecuada basada en la fecha de vencimiento y el precio de ejercicio. '''
        
        contracts = self.OptionChainProvider.GetOptionContractList(self.symbol, data.Time)
        self.underlyingPrice = self.Securities[self.symbol].Price
        
        # Filtrar opciones put fuera del dinero (OTM) que expiren cerca de los días objetivo (DTE)
        otm_puts = [i for i in contracts if i.ID.OptionRight == OptionRight.Put and
                                            self.underlyingPrice - i.ID.StrikePrice > self.OTM * self.underlyingPrice and
                                            self.DTE - 8 < (i.ID.Date - data.Time).days < self.DTE + 8]
        
        if len(otm_puts) > 0:
            # Ordenar opciones según la cercanía a los días objetivo y el precio de ejercicio
            contract = sorted(sorted(otm_puts, key=lambda x: abs((x.ID.Date - self.Time).days - self.DTE)),
                                                     key=lambda x: self.underlyingPrice - x.ID.StrikePrice)[0]
            
            if contract not in self.contractsAdded:
                self.contractsAdded.add(contract)
                # Suscribirse a los datos del contrato seleccionado
                self.AddOptionContract(contract, Resolution.Minute)
            
            return contract
        else:
            return str()

    def Plotting(self):
        # Graficar el indicador IV
        self.Plot("Vol Chart", "Rank", self.rank)
        self.Plot("Vol Chart", "lvl", self.IVlvl)
        
        # Graficar el precio del activo subyacente
        self.Plot("Data Chart", self.symbol, self.Securities[self.symbol].Close)
        
        # Graficar el precio de ejercicio de la opción put si está en cartera
        option_invested = [x.Key for x in self.Portfolio if x.Value.Invested and x.Value.Type == SecurityType.Option]
        if option_invested:
            self.Plot("Data Chart", "strike", option_invested[0].ID.StrikePrice)

    def OnOrderEvent(self, orderEvent):
        # Registrar eventos de órdenes en el log
        self.Log(str(orderEvent))