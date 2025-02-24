class BreakoutCallBuy(QCAlgorithm):
    
    def Initialize(self):
        # Configuración inicial del backtest
        self.SetStartDate(2018, 1, 1)  # Fecha de inicio
        self.SetEndDate(2021, 1, 1)  # Fecha de finalización
        self.SetCash(100000)  # Capital inicial
        
        # Agregar el activo subyacente (Microsoft - MSFT)
        equity = self.AddEquity("MSFT", Resolution.Minute)
        equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.equity = equity.Symbol
        self.SetBenchmark(self.equity)  # Establecer el benchmark
        
        # Agregar opciones sobre el activo subyacente
        option = self.AddOption("MSFT", Resolution.Minute)
        option.SetFilter(-3, 3, timedelta(20), timedelta(40))  # Filtro de opciones
        
        # Indicador de máximo de 21 días para detectar breakout
        self.high = self.MAX(self.equity, 21, Resolution.Daily, Field.High)
    
    def OnData(self, data):
        # Esperar hasta que el indicador esté listo
        if not self.high.IsReady:
            return
        
        # Verificar si hay opciones en la cartera
        option_invested = [x.Key for x in self.Portfolio if x.Value.Invested and x.Value.Type == SecurityType.Option]
        
        # Si hay opciones en la cartera, verificar la fecha de expiración
        if option_invested:
            if self.Time + timedelta(4) > option_invested[0].ID.Date:
                self.Liquidate(option_invested[0], "Demasiado cerca de la expiración")
            return
        
        # Comprar una opción Call si el precio supera el máximo de los últimos 21 días
        if self.Securities[self.equity].Price >= self.high.Current.Value:
            for i in data.OptionChains:
                chains = i.Value
                self.BuyCall(chains)

    def BuyCall(self, chains):
        # Seleccionar la opción Call con la expiración más lejana disponible
        expiry = sorted(chains, key=lambda x: x.Expiry, reverse=True)[0].Expiry
        
        # Filtrar solo las opciones Call con esa expiración
        calls = [i for i in chains if i.Expiry == expiry and i.Right == OptionRight.Call]
        
        # Ordenar las opciones Call por cercanía al precio del activo subyacente
        call_contracts = sorted(calls, key=lambda x: abs(x.Strike - x.UnderlyingLastPrice))
        
        if len(call_contracts) == 0:  # Verificar que haya contratos disponibles
            return
        
        self.call = call_contracts[0]  # Seleccionar la mejor opción Call
        
        # Calcular la cantidad de contratos a comprar (5% del portafolio)
        quantity = self.Portfolio.TotalPortfolioValue / self.call.AskPrice
        quantity = int(0.05 * quantity / 100)
        
        # Realizar la compra
        self.Buy(self.call.Symbol, quantity)

    def OnOrderEvent(self, orderEvent):
        # Manejo de eventos de órdenes
        order = self.Transactions.GetOrderById(orderEvent.OrderId)
        if order.Type == OrderType.OptionExercise:
            self.Liquidate()
