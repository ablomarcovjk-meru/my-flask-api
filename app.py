from flask import Flask, jsonify, request
import pandas as pd
from datetime import datetime
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
import locale
import os

app = Flask(__name__)

# Load CSV file
df = pd.read_csv('https://raw.githubusercontent.com/ablomarcovjk-meru/my-flask-api/refs/heads/main/archivos_clientes.csv?token=GHSAT0AAAAAACX5VEHX7DDQ7Z53BEU6S2CMZX3GAPQ', encoding='utf-8')

# Convert dates to datetime format
df['SO_FULFILMENT_DATE'] = pd.to_datetime(df['SO_FULFILMENT_DATE'], format='%d/%m/%y')

# Locale for currency formatting
locale.setlocale(locale.LC_ALL, '')

# Function to format price with dollar symbol
def formatear_precio(valor):
    return "${:,.2f}".format(valor)  # Format as $1,234.56

# Function to get the month name in Spanish
def obtener_nombre_mes(mes_periodo):
    meses = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    return meses[mes_periodo.month - 1]

# Function to identify months without purchases in 2024
def meses_sin_compras_2024(cliente_data):
    compras_2024 = cliente_data[cliente_data['SO_FULFILMENT_DATE'].dt.year == 2024]
    fecha_actual = datetime.now()
    todos_los_meses_2024 = pd.period_range('2024-01', fecha_actual.strftime('%Y-%m'), freq='M')
    meses_comprados_2024 = compras_2024['SO_FULFILMENT_DATE'].dt.to_period('M').unique()
    meses_no_comprados_2024 = [mes for mes in todos_los_meses_2024 if mes not in meses_comprados_2024]
    return [obtener_nombre_mes(mes) for mes in meses_no_comprados_2024]

# Function to identify the last month of purchase in 2023
def mes_ultima_compra_2023(cliente_data):
    compras_2023 = cliente_data[cliente_data['SO_FULFILMENT_DATE'].dt.year == 2023]
    if compras_2023.empty:
        return "No realizo compras en 2023"
    ultima_compra_2023 = compras_2023['SO_FULFILMENT_DATE'].max()
    return obtener_nombre_mes(ultima_compra_2023.to_period('M'))

# Main function to search customer by ID, name, or email
def buscar_cliente(criterio, tipo_busqueda='CUSTOMER_MOS_ID'):
    # If searching by name, use fuzzy matching to find the closest name
    if tipo_busqueda == 'CUSTOMER_FULL_NAME':
        nombres = df['CUSTOMER_FULL_NAME'].tolist()
        mejor_coincidencia, puntuacion = process.extractOne(criterio, nombres, scorer=fuzz.token_sort_ratio)
        
        if puntuacion < 80:
            return f"No se encontraron coincidencias cercanas para el nombre del cliente: {criterio}"

        cliente_data = df[df['CUSTOMER_FULL_NAME'] == mejor_coincidencia]

    # If searching by email, use fuzzy matching for emails
    elif tipo_busqueda == 'EMAIL':
        correos = df['EMAIL'].tolist()
        mejor_coincidencia, puntuacion = process.extractOne(criterio, correos, scorer=fuzz.token_sort_ratio)
        
        if puntuacion < 80:
            return f"No se encontraron coincidencias cercanas para el correo: {criterio}"

        cliente_data = df[df['EMAIL'] == mejor_coincidencia]

    # If searching by ID
    else:
        cliente_data = df[df['CUSTOMER_MOS_ID'] == criterio]
    
    if cliente_data.empty:
        return f"No se encontraron datos para el cliente con {tipo_busqueda}: {criterio}"

    # Extract the variables to be returned
    ultima_compra = cliente_data['SO_FULFILMENT_DATE'].max()
    ultima_compra_str = ultima_compra.strftime('%Y-%m-%d')
    fecha_actual = datetime.now()
    dias_sin_compra = (fecha_actual - ultima_compra).days
    producto_mas_comprado = cliente_data.groupby('PRODUCT_DESCRIPTION')['TOTAL_QUANTITY'].sum().idxmax()

    cliente_data = cliente_data.copy()
    cliente_data.loc[:, 'Mes'] = cliente_data['SO_FULFILMENT_DATE'].dt.to_period('M')

    if len(cliente_data) > 1:
        cliente_data['Días entre compras'] = cliente_data['SO_FULFILMENT_DATE'].diff().dt.days
        dias_promedio = round(cliente_data['Días entre compras'].mean(), 1)
    else:
        dias_promedio = "No es posible calcular el promedio con una sola compra"

    mes_mas_compras = cliente_data.groupby('Mes')['TOTAL_QUANTITY'].sum().idxmax()
    mes_menos_compras = cliente_data.groupby('Mes')['TOTAL_QUANTITY'].sum().idxmin()
    nombre_mes_menos_compras = obtener_nombre_mes(mes_menos_compras)
    promedio_1P = cliente_data[cliente_data['LISTING_TIER'] == '1P']['TOTAL_QUANTITY'].mean()
    promedio_3P = cliente_data[cliente_data['LISTING_TIER'] == '3P']['TOTAL_QUANTITY'].mean()

    # Get the top 3 products by quantity
    top_3_productos = cliente_data.groupby(['PRODUCT_DESCRIPTION', 'LISTING_TIER']).agg({'TOTAL_QUANTITY': 'sum', 'TOTAL_AMOUNT': 'sum'}).nlargest(3, 'TOTAL_QUANTITY')
    top_3 = [(producto, cantidad, formatear_precio(monto), tier) for (producto, tier), (cantidad, monto) in top_3_productos.iterrows()]

    meses_no_comprados_2024 = meses_sin_compras_2024(cliente_data)
    mes_no_compraba_2023 = mes_ultima_compra_2023(cliente_data)

    # Return all the variables as part of a JSON response
    return {
        'Cliente': mejor_coincidencia if tipo_busqueda in ['CUSTOMER_FULL_NAME', 'EMAIL'] else criterio,
        'Ultima compra': ultima_compra_str,
        'Dias sin comprarnos': dias_sin_compra,
        'Cada cuantos dias compra (promedio)': dias_promedio,
        'Producto mas comprado': producto_mas_comprado,
        'Mes con mas compras': obtener_nombre_mes(mes_mas_compras),
        'Mes con menos compras': nombre_mes_menos_compras,
        'Promedio cantidad 1P': round(promedio_1P, 2) if not pd.isna(promedio_1P) else 0,
        'Promedio cantidad 3P': round(promedio_3P, 2) if not pd.isna(promedio_3P) else 0,
        'Top 3 productos': top_3,
        'Meses sin compras en 2024': meses_no_comprados_2024,
        'Desde que mes no compraba en 2023': mes_no_compraba_2023,
    }

@app.after_request
def set_utf8_charset(response):
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    return response

@app.route('/buscar_por_id', methods=['POST'])
def buscar_por_id():
    data = request.get_json()
    cliente_id = data.get('buscar_por_id')
    if not cliente_id:
        return jsonify({'error': 'El campo buscar_por_id es requerido'}), 400
    resultado = buscar_cliente(cliente_id, tipo_busqueda='CUSTOMER_MOS_ID')
    return jsonify(resultado)

@app.route('/buscar_por_nombre', methods=['POST'])
def buscar_por_nombre():
    data = request.get_json()
    nombre_cliente = data.get('buscar_por_nombre')
    if not nombre_cliente:
        return jsonify({'error': 'El campo buscar_por_nombre es requerido'}), 400
    resultado = buscar_cliente(nombre_cliente, tipo_busqueda='CUSTOMER_FULL_NAME')
    return jsonify(resultado)

@app.route('/buscar_por_correo', methods=['POST'])
def buscar_por_correo():
    data = request.get_json()
    correo_cliente = data.get('buscar_por_correo')
    if not correo_cliente:
        return jsonify({'error': 'El campo buscar_por_correo es requerido'}), 400
    resultado = buscar_cliente(correo_cliente, tipo_busqueda='EMAIL')
    return jsonify(resultado)

if __name__ == '__main__':
    app.run(debug=True)
