
from flask import Flask, request, send_file, render_template_string
import pandas as pd
import io
import re
from datetime import datetime
import csv

app = Flask(__name__)

HTML_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Konwerter Promocji</title>
</head>
<body>
    <h1>Konwerter danych promocyjnych</h1>
    <form action="/convert" method="post" enctype="multipart/form-data">
        <p>Wgraj plik CSV/Excel:</p>
        <input type="file" name="file">
        <p>Lub wklej dane z Excela:</p>
        <textarea name="clipboard" rows="10" cols="100"></textarea><br>
        <input type="submit" value="Generuj CSV">
    </form>
</body>
</html>
'''

POLSKIE_MIESIACE = {
    'styczeń': '01', 'luty': '02', 'marzec': '03', 'kwiecień': '04',
    'maj': '05', 'czerwiec': '06', 'lipiec': '07', 'sierpień': '08',
    'wrzesień': '09', 'październik': '10', 'listopad': '11', 'grudzień': '12'
}

def parse_price(price):
    if pd.isna(price):
        return ''
    return str(price).replace(' ', '').replace(',', '.').strip()

def parse_date(date_str):
    if pd.isna(date_str):
        return ''
    try:
        if re.match(r'\d{2}-\d{2}-\d{2} \d{1,2}:\d{2}', date_str):
            dt = datetime.strptime(date_str, '%d-%m-%y %H:%M')
        elif ',' in date_str and any(m in date_str for m in POLSKIE_MIESIACE):
            # przykład: 'piątek, 11 kwiecień 2025'
            parts = date_str.split(', ')[1].split(' ')
            dzien = parts[0]
            miesiac = POLSKIE_MIESIACE.get(parts[1].lower(), '01')
            rok = parts[2]
            dt_str = f'{rok}-{miesiac}-{dzien} 18:30'
            dt = pd.to_datetime(dt_str)
        else:
            dt = pd.to_datetime(date_str)
        return dt.strftime('%y-%m-%d %H:%M')
    except Exception:
        return date_str

def process_dataframe(df):
    rename_map = {
        'ERP ID': 'sku',
        'Cena promocyjna': 'special_price',
        'Data obowiązywania od': 'special_price_from',
        'Data obowiązywania do': 'special_price_to',
        'Ilość sztuk w promocji': 'import_promo_qty',
    }
    df = df.rename(columns=rename_map)
    df['special_price'] = df['special_price'].apply(parse_price)
    df['special_price_from'] = df['special_price_from'].apply(parse_date)
    df['special_price_to'] = df['special_price_to'].apply(parse_date)
    if 'import_promo_qty_use_central_stock' not in df.columns:
        df['import_promo_qty_use_central_stock'] = ''
    final_columns = [
        'sku', 'special_price', 'special_price_from', 'special_price_to',
        'import_promo_qty', 'import_promo_qty_use_central_stock'
    ]
    return df[final_columns]

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/convert', methods=['POST'])
def convert():
    if 'file' in request.files and request.files['file'].filename != '':
        f = request.files['file']
        if f.filename.endswith('.csv'):
            df = pd.read_csv(f, encoding='utf-8')
        else:
            df = pd.read_excel(f)
    elif 'clipboard' in request.form and request.form['clipboard'].strip():
        text_data = request.form['clipboard']
        df = pd.read_csv(io.StringIO(text_data), sep='\t', header=None)
        if df.shape[1] == 5:
            df.columns = ['ERP ID', 'Cena promocyjna', 'Data obowiązywania od', 'Data obowiązywania do', 'Ilość sztuk w promocji']
    else:
        return 'Brak danych wejściowych', 400

    df_processed = process_dataframe(df)

    output = io.StringIO()
    df_processed.to_csv(output, index=False, encoding='utf-8')
    output.seek(0)

    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='export.csv'
    )

if __name__ == '__main__':
    app.run(debug=True)
