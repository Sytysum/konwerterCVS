from flask import Flask, request, send_file, render_template_string
import pandas as pd
import io
import re
from datetime import datetime
import os

app = Flask(__name__)

HTML_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Konwerter Promocji</title>
</head>
<body style="font-family: sans-serif; text-align: center; padding-top: 20px;">
    <img src="/static/logo.png" alt="Vobis" style="width: 120px; margin-bottom: 20px;">
    <h1>Konwerter danych promocyjnych</h1>
    <form id="form" action="/convert" method="post" enctype="multipart/form-data">
        <div id="fileInfo" style="display:none; margin-bottom:10px;">
            <strong>Plik wgrany.</strong>
            <button type="button" onclick="clearFile()" style="color:red; margin-left:10px;">Usuń plik</button>
        </div>
        <p>Wgraj plik CSV/Excel:</p>
        <input type="file" name="file" id="fileInput" onchange="handleFileUpload()">
        <p>Lub wklej dane z Excela:</p>
        <textarea name="clipboard" rows="10" cols="100"></textarea><br>
        <input type="submit" value="Generuj CSV">
    </form>
    <script>
        function handleFileUpload() {
            document.getElementById('fileInfo').style.display = 'block';
        }
        function clearFile() {
            const input = document.getElementById('fileInput');
            input.value = '';
            document.getElementById('fileInfo').style.display = 'none';
        }
    </script>
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
    if len(df.columns) >= 5:
        df = df.iloc[:, :5]
        df.columns = ['ERP ID', 'Cena promocyjna', 'Data obowiązywania od', 'Data obowiązywania do', 'Ilość sztuk w promocji']
        df = df.dropna(subset=['ERP ID', 'Cena promocyjna'])
        print('===> Po odfiltrowaniu pustych wierszy:', df.shape)
        df = df.rename(columns={
            'ERP ID': 'sku',
            'Cena promocyjna': 'special_price',
            'Data obowiązywania od': 'special_price_from',
            'Data obowiązywania do': 'special_price_to',
            'Ilość sztuk w promocji': 'import_promo_qty',
        })
        df['special_price'] = df['special_price'].apply(parse_price)
        df['special_price_from'] = df['special_price_from'].apply(parse_date)
        df['special_price_to'] = df['special_price_to'].apply(parse_date)
        df['import_promo_qty'] = df['import_promo_qty'].fillna('').astype(str).str.strip().replace('0.0', '').replace('0', '')
        df['import_promo_qty_use_central_stock'] = df.apply(
            lambda row: '1' if row['import_promo_qty'] in ['', '0'] else '',
            axis=1
        )
        df['import_promo_qty'] = df['import_promo_qty'].replace({'': '99', '0': '99', '0.0': '99'})
        final_columns = [
            'sku', 'special_price', 'special_price_from', 'special_price_to',
            'import_promo_qty', 'import_promo_qty_use_central_stock'
        ]
        return df[final_columns]
    return pd.DataFrame()

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/convert', methods=['POST'])
def convert():
    df = None
    print("===> FORM DATA:", request.form)
    print("===> FILES:", request.files)
    if 'file' in request.files and request.files['file'].filename != '':
        f = request.files['file']
        try:
            if f.filename.endswith('.csv'):
                df = pd.read_csv(f, encoding='utf-8', sep=';', engine='python')
                print("===> CSV dane (pierwsze 10):\n", df.head(10))
                print("===> Kształt CSV:", df.shape)
            else:
                df_all = pd.read_excel(f, header=None)
                for i, row in df_all.iterrows():
                    row_str = "|".join(str(cell).strip().lower() for cell in row)
                    if "erp" in row_str and "cena" in row_str and "obowiązywania" in row_str:
                        df = df_all.iloc[i+1:].copy()
                        df.columns = df_all.iloc[i]
                        print("===> Nagłówki znalezione w wierszu", i)
                        break
                else:
                    return 'Nie znaleziono nagłówków w pliku Excel', 400
                print("===> Excel dane (pierwsze 10):\n", df.head(10))
                print("===> Kształt Excel:", df.shape)
        except Exception as e:
            return f'Błąd pliku: {e}', 400
    elif 'clipboard' in request.form and request.form['clipboard'].strip():
        text_data = request.form['clipboard']
        print("===> CLIPBOARD RAW:\n", text_data[:500])
        try:
            df = pd.read_csv(io.StringIO(text_data), sep='\t', header=None)
            if df.shape[1] <= 1:
                df = pd.read_csv(io.StringIO(text_data), sep=r'\s{2,}', engine='python', header=None)
        except Exception as e:
            return f'Błąd wklejonych danych: {e}', 400
    else:
        return 'Brak danych wejściowych', 400

    df_processed = process_dataframe(df)
    if df_processed.empty:
        return 'Niepoprawny format danych wejściowych', 400

    output = io.StringIO()
    df_processed = df_processed.astype(str).applymap(lambda x: x.rstrip('.0') if x.endswith('.0') else x)
    df_processed.to_csv(output, index=False, encoding='utf-8')
    output.seek(0)

    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='export.csv'
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
