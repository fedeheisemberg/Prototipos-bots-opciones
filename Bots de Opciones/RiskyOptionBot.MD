
## **Descripción general del bot**
El **RiskyOptionsBot** es un bot de trading automatizado que se conecta a Interactive Brokers (IB) y busca comprar contratos de opciones sobre **SPY** cuando se cumplen ciertas condiciones en el precio. La estrategia consiste en:

1. Monitorear velas de 5 minutos del SPY.
2. Identificar tres cierres consecutivos al alza.
3. Comprar una opción de compra (Call) fuera del dinero ($5 por encima del precio actual).
4. Vender la opción en la siguiente vela si el precio sube.

---

## **Librerías utilizadas**
```python
from datetime import datetime
from ib_insync import *
from apscheduler.schedulers.background import BackgroundScheduler
import asyncio
```
- **ib_insync**: Librería para conectarse y operar con Interactive Brokers.
- **apscheduler**: Para programar tareas recurrentes como la actualización de la cadena de opciones.
- **asyncio**: Para manejar eventos asíncronos.

---

## **Clase `RiskyOptionsBot`**
Esta clase contiene toda la lógica del bot.

### **Método `__init__`**
```python
def __init__(self, *args, **kwargs):
```
- Es el **constructor** de la clase. Se ejecuta al instanciar el bot.

#### **Conexión con IB**
```python
try:
    self.ib = IB()
    self.ib.connect('127.0.0.1', 7497, clientId=1)
except Exception as e:
    print(str(e))
```
- Crea una instancia de IB y trata de conectarse en `localhost` al puerto **7497**.
- Si falla la conexión, imprime el error.

#### **Definir el contrato del subyacente (SPY)**
```python
self.underlying = Stock('SPY', 'SMART', 'USD')
self.ib.qualifyContracts(self.underlying)
```
- Se define un contrato sobre SPY en Interactive Brokers y se valida su existencia.

#### **Descargar datos históricos**
```python
self.data = self.ib.reqHistoricalData(
    self.underlying, endDateTime='', durationStr='2 D',
    barSizeSetting='5 mins', whatToShow='TRADES'
)
```
- Obtiene los datos de los últimos 2 días en velas de **5 minutos**.

#### **Obtener la cadena de opciones**
```python
self.chains = self.ib.reqSecDefOptParams(
    self.underlying.symbol, '', self.underlying.secType, self.underlying.conId
)
```
- Solicita la lista de opciones disponibles para SPY.

#### **Configurar actualización automática de opciones**
```python
update_chain_scheduler = BackgroundScheduler(job_defaults={'max_instances': 2})
update_chain_scheduler.add_job(func=self.update_options_chains, trigger='cron', hour='*')
update_chain_scheduler.start()
```
- Programa la actualización de la lista de opciones **cada hora**.

#### **Configurar eventos de actualización**
```python
self.data.updateEvent += self.on_bar_update
self.ib.execDetailsEvent += self.exec_status
```
- Se ejecuta `on_bar_update` cuando llega un nuevo dato.
- `exec_status` se ejecuta cuando una orden es ejecutada.

#### **Ejecutar el bot**
```python
self.ib.run()
```
- Inicia el **bucle de eventos** de IB para mantener el bot corriendo.

---

## **Método `update_options_chains`**
```python
def update_options_chains(self):
```
- Actualiza la lista de opciones disponibles.

```python
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
```
- Configura un nuevo **event loop** para manejar la actualización de forma asíncrona.

```python
self.chains = self.ib.reqSecDefOptParams(
    self.underlying.symbol, '', self.underlying.secType, self.underlying.conId
)
```
- Vuelve a solicitar la lista de opciones.

---

## **Método `on_bar_update`**
Este método se ejecuta cada vez que se recibe una nueva vela.

```python
def on_bar_update(self, bars: BarDataList, has_new_bar: bool):
```
- `bars`: Lista de datos históricos de SPY.
- `has_new_bar`: `True` si hay una nueva vela.

### **Conversión de datos a DataFrame**
```python
df = util.df(bars)
```
- Convierte los datos en un `DataFrame` de Pandas.

### **Condición de entrada**
```python
if not self.in_trade:
    print("Last Close : " + str(df.close.iloc[-1]))

    if df.close.iloc[-1] > df.close.iloc[-2] and df.close.iloc[-2] > df.close.iloc[-3]:
```
- Si **no estamos en una operación**, verifica si hay **3 cierres consecutivos al alza**.

### **Buscar opción Call para comprar**
```python
for optionschain in self.chains:
    for strike in optionschain.strikes:
        if strike > df.close.iloc[-1] + 5:
```
- Busca una opción **Call** cuyo strike sea **$5 por encima** del último cierre.

```python
self.options_contract = Option(
    self.underlying.symbol,
    optionschain.expirations[1],
    strike, 'C', 'SMART', tradingClass=self.underlying.symbol
)
```
- Se crea el contrato de la opción.

### **Ejecutar orden de compra**
```python
options_order = MarketOrder("BUY", 1, account=self.ib.wrapper.accounts[-1])
trade = self.ib.placeOrder(self.options_contract, options_order)
self.lastEstimatedFillPrice = df.close.iloc[-1]
self.in_trade = True
return
```
- Se envía una orden de **compra** de 1 contrato Call.
- Se guarda el precio de entrada y se marca como **en operación**.

---

## **Condición de salida**
```python
else:
    if df.close.iloc[-1] > self.lastEstimatedFillPrice:
        options_order = MarketOrder("SELL", 1, account=self.ib.wrapper.accounts[-1])
```
- Si el precio sube **por encima** del precio de compra, se vende la opción.

---

## **Método `exec_status`**
```python
def exec_status(self, trade: Trade, fill: Fill):
    print("Filled")
```
- Muestra un mensaje cuando una orden es ejecutada.

---

## **Instanciar el bot**
```python
RiskyOptionsBot()
```
- Crea una instancia del bot y lo inicia.

---

## **Resumen del flujo del bot**
1. **Conexión a IB**.
2. **Obtención de datos históricos y lista de opciones**.
3. **Espera datos en vivo**.
4. **Evalúa condición de entrada** (3 cierres consecutivos al alza).
5. **Compra una opción Call** si se cumple la condición.
6. **Espera la siguiente vela**.
7. **Si el precio sube, vende la opción**.
8. **Repite el proceso**.

---

## **Posibles mejoras**
- Manejar excepciones en la selección de opciones.
- Configurar un **stop-loss** en caso de caída del precio.
- Agregar un **control de riesgo** para evitar operar con toda la cuenta.

