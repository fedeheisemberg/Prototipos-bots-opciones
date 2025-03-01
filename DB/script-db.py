import pandas as pd
import sqlite3
from datetime import datetime, time as dt_time
import time
import schedule
from pyhomebroker import HomeBroker
import re
import os
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Configuración de la base de datos
Base = declarative_base()

class DatosOpcion(Base):
    __tablename__ = 'opciones_ggal'
    
    id = Column(Integer, primary_key=True)
    simbolo = Column(String, index=True)
    vencimiento = Column(String, index=True)  # FE, AB, JU, AG, OC, DI
    tipo_opcion = Column(String)  # Call o Put
    strike = Column(Float)
    tamano_bid = Column(Integer)
    bid = Column(Float)
    ask = Column(Float)
    tamano_ask = Column(Integer)
    ultimo = Column(Float)
    cambio = Column(Float)
    apertura = Column(Float)
    maximo = Column(Float)
    minimo = Column(Float)
    cierre_previo = Column(Float)
    monto_operado = Column(Float)
    volumen = Column(Integer)
    operaciones = Column(Integer)
    fecha_hora = Column(DateTime, index=True)
    timestamp = Column(DateTime, default=datetime.now)

# Crear motor de base de datos
archivo_db = 'opciones_ggal.db'
motor = create_engine(f'sqlite:///{archivo_db}')
Base.metadata.create_all(motor)

# Crear sesión
Sesion = sessionmaker(bind=motor)

# Credenciales de HomeBroker
broker = 203
dni = '40728985'
usuario = 'FedeMarti02'
contrasena = '#Fandeieb234'

# DataFrame para las opciones
datos_opciones = pd.DataFrame()
esta_conectado = False

# Extraer vencimiento, strike y tipo de opción del símbolo
def analizar_simbolo_opcion(simbolo):
    if not simbolo.startswith('GFG'):
        return None, None, None
    
    tipo_opcion = 'Call' if 'C' in simbolo[3:4] else 'Put'
    
    # Extraer vencimiento y strike
    patron = r'GFG[CP](\d+)([A-Z]{2})'
    coincidencia = re.match(patron, simbolo)
    if coincidencia:
        strike = float(coincidencia.group(1)) / 100  # Asumiendo que el strike está en centavos
        vencimiento = coincidencia.group(2)
        return vencimiento, strike, tipo_opcion
    return None, None, None

# Función de callback para datos de opciones
def en_opciones(online, cotizaciones):
    global datos_opciones
    
    # Filtrar solo opciones de GGAL (prefijo GFG)
    opciones_ggal = cotizaciones[cotizaciones.index.str.startswith('GFG')]
    
    if not opciones_ggal.empty:
        # Crear una copia para evitar SettingWithCopyWarning
        estos_datos = opciones_ggal.copy()
        estos_datos['cambio'] = estos_datos["change"] / 100
        estos_datos['fecha_hora'] = pd.to_datetime(estos_datos['datetime'])
        
        # Agregar columnas de vencimiento y tipo de opción
        for idx, fila in estos_datos.iterrows():
            vencimiento, strike, tipo_opcion = analizar_simbolo_opcion(idx)
            estos_datos.at[idx, 'vencimiento'] = vencimiento
            estos_datos.at[idx, 'strike'] = strike
            estos_datos.at[idx, 'tipo_opcion'] = tipo_opcion
        
        # Actualizar el DataFrame global
        datos_opciones = pd.concat([datos_opciones, estos_datos])
        
        # Guardar en la base de datos
        guardar_en_base_datos(estos_datos)
        
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Guardados {len(estos_datos)} registros de opciones GGAL")

def en_error(online, error):
    print(f"Mensaje de error recibido: {error}")
    
def guardar_en_base_datos(datos):
    sesion = Sesion()
    
    try:
        for idx, fila in datos.iterrows():
            # Crear nuevo registro de datos de opción
            registro_opcion = DatosOpcion(
                simbolo=idx,
                vencimiento=fila.get('vencimiento'),
                tipo_opcion=fila.get('tipo_opcion'),
                strike=fila.get('strike'),
                tamano_bid=fila.get('bid_size'),
                bid=fila.get('bid'),
                ask=fila.get('ask'),
                tamano_ask=fila.get('ask_size'),
                ultimo=fila.get('last'),
                cambio=fila.get('cambio'),
                apertura=fila.get('open'),
                maximo=fila.get('high'),
                minimo=fila.get('low'),
                cierre_previo=fila.get('previous_close'),
                monto_operado=fila.get('turnover'),
                volumen=fila.get('volume'),
                operaciones=fila.get('operations'),
                fecha_hora=fila.get('fecha_hora')
            )
            sesion.add(registro_opcion)
        
        sesion.commit()
    except Exception as e:
        sesion.rollback()
        print(f"Error en la base de datos: {e}")
    finally:
        sesion.close()

def conectar_homebroker():
    global esta_conectado, hb
    
    if esta_conectado:
        return
    
    try:
        print("Conectando a HomeBroker...")
        hb = HomeBroker(int(broker), on_options=en_opciones, on_error=en_error)
        hb.auth.login(dni=dni, user=usuario, password=contrasena, raise_exception=True)
        hb.online.connect()
        hb.online.subscribe_options()
        esta_conectado = True
        print("Conexión exitosa a HomeBroker")
    except Exception as e:
        print(f"Error al conectar a HomeBroker: {e}")
        esta_conectado = False

def desconectar_homebroker():
    global esta_conectado, hb
    
    if not esta_conectado:
        return
    
    try:
        print("Desconectando de HomeBroker...")
        hb.online.disconnect()
        esta_conectado = False
        print("Desconexión exitosa de HomeBroker")
    except Exception as e:
        print(f"Error al desconectar de HomeBroker: {e}")

def es_horario_trading():
    ahora = datetime.now()
    hora_actual = ahora.time()
    # Horario de trading: 11:00 AM a 5:00 PM
    return (
        dt_time(11, 0) <= hora_actual <= dt_time(17, 0) and 
        ahora.weekday() < 5  # Lunes a Viernes
    )

def verificar_y_conectar():
    if es_horario_trading():
        if not esta_conectado:
            conectar_homebroker()
    else:
        if esta_conectado:
            desconectar_homebroker()

def generar_informe_diario():
    ahora = datetime.now()
    
    try:
        # Conectar a la base de datos
        conn = sqlite3.connect(archivo_db)
        
        # Obtener datos de hoy
        hoy = ahora.strftime('%Y-%m-%d')
        consulta = f"""
        SELECT 
            simbolo, 
            vencimiento, 
            tipo_opcion, 
            strike, 
            COUNT(*) as cantidad_registros,
            MIN(fecha_hora) as primer_registro,
            MAX(fecha_hora) as ultimo_registro,
            MIN(ultimo) as precio_min,
            MAX(ultimo) as precio_max,
            last_value(ultimo) as precio_cierre
        FROM opciones_ggal 
        WHERE date(fecha_hora) = '{hoy}'
        GROUP BY simbolo
        """
        
        datos_hoy = pd.read_sql_query(consulta, conn)
        conn.close()
        
        if datos_hoy.empty:
            print(f"No se registraron datos para {hoy}")
            return
        
        # Crear un informe simple
        informe = f"Informe Diario de Datos de Opciones - {hoy}\n"
        informe += f"Total de símbolos registrados: {len(datos_hoy)}\n"
        informe += f"Total de puntos de datos: {datos_hoy['cantidad_registros'].sum()}\n"
        informe += f"Período de tiempo: {datos_hoy['primer_registro'].min()} a {datos_hoy['ultimo_registro'].max()}\n"
        informe += "\nTop 5 opciones más activas:\n"
        
        # Ordenar por cantidad de registros y mostrar los 5 primeros
        opciones_top = datos_hoy.sort_values('cantidad_registros', ascending=False).head(5)
        for _, fila in opciones_top.iterrows():
            informe += f"  {fila['simbolo']} ({fila['tipo_opcion']} - {fila['vencimiento']}): {fila['cantidad_registros']} registros, "
            informe += f"Rango: {fila['precio_min']} - {fila['precio_max']}, Cierre: {fila['precio_cierre']}\n"
        
        print(informe)
        
        # Guardar informe en archivo
        archivo_informe = f"informe_opciones_{hoy}.txt"
        with open(archivo_informe, 'w') as f:
            f.write(informe)
        
        print(f"Informe guardado en {archivo_informe}")
        
    except Exception as e:
        print(f"Error al generar informe diario: {e}")

# Programar tareas
schedule.every(2).seconds.do(verificar_y_conectar)
schedule.every().day.at("17:05").do(generar_informe_diario)

if __name__ == "__main__":
    print("Iniciando Sistema de Registro de Base de Datos para Opciones GGAL")
    print(f"Archivo de base de datos: {os.path.abspath(archivo_db)}")
    
    # Verificar base de datos
    if os.path.exists(archivo_db):
        conn = sqlite3.connect(archivo_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM opciones_ggal")
        conteo = cursor.fetchone()[0]
        conn.close()
        print(f"Base de datos existente encontrada con {conteo} registros")
    else:
        print("Se creó una nueva base de datos")
    
    # Bucle principal
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("Deteniendo el Sistema de Registro de Base de Datos para Opciones GGAL")
        if esta_conectado:
            desconectar_homebroker()