"""VyaparSaathi API: SQLite-backed business records + optional Gemini/Firebase integrations."""
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import date, timedelta
from pathlib import Path
import csv, io, json, os, sqlite3

load_dotenv()
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": os.getenv("CORS_ORIGINS", "*").split(",")}})
DB_PATH = os.getenv("DATABASE_PATH", str(Path(__file__).with_name("vyaparsaathi.db")))


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0), category TEXT DEFAULT '',
            party TEXT DEFAULT '', note TEXT DEFAULT '', payment_mode TEXT DEFAULT 'Cash',
            status TEXT DEFAULT 'Paid', due_date TEXT DEFAULT '', txn_date TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        con.execute('''CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT DEFAULT '',
            opening_due REAL DEFAULT 0, notes TEXT DEFAULT '')''')
        con.execute('''CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT DEFAULT '',
            notes TEXT DEFAULT '')''')


init_db()


def rows(sql, params=()):
    with db() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def money(v):
    try: return round(float(v or 0), 2)
    except (TypeError, ValueError): return 0.0


@app.get('/api/health')
def health():
    return jsonify({"status": "healthy", "service": "VyaparSaathi API", "storage": "sqlite", "gemini_configured": bool(os.getenv('GEMINI_API_KEY'))})


@app.get('/api/transactions')
def list_transactions():
    return jsonify(rows('SELECT * FROM transactions ORDER BY txn_date DESC, id DESC'))


@app.post('/api/transactions')
def add_transaction():
    d = request.get_json(silent=True) or {}
    kind = str(d.get('kind', '')).lower()
    if kind not in ('sale', 'expense', 'purchase', 'collection', 'supplier_payment'):
        return jsonify(error='Invalid transaction type'), 400
    amount = money(d.get('amount'))
    if amount <= 0: return jsonify(error='Amount must be greater than zero'), 400
    txn_date = str(d.get('txn_date') or date.today().isoformat())
    with db() as con:
        cur = con.execute('''INSERT INTO transactions(kind,amount,category,party,note,payment_mode,status,due_date,txn_date)
          VALUES(?,?,?,?,?,?,?,?,?)''', (kind, amount, d.get('category',''), d.get('party',''), d.get('note',''),
          d.get('payment_mode','Cash'), d.get('status','Paid'), d.get('due_date',''), txn_date))
        item = dict(con.execute('SELECT * FROM transactions WHERE id=?', (cur.lastrowid,)).fetchone())
    return jsonify(item), 201


@app.put('/api/transactions/<int:item_id>')
def update_transaction(item_id):
    d = request.get_json(silent=True) or {}
    allowed = ['kind','amount','category','party','note','payment_mode','status','due_date','txn_date']
    fields = {k: d[k] for k in allowed if k in d}
    if 'amount' in fields: fields['amount'] = money(fields['amount'])
    if not fields: return jsonify(error='No fields to update'), 400
    with db() as con:
        if not con.execute('SELECT id FROM transactions WHERE id=?', (item_id,)).fetchone(): return jsonify(error='Not found'), 404
        con.execute('UPDATE transactions SET ' + ','.join(f'{k}=?' for k in fields) + ' WHERE id=?', (*fields.values(), item_id))
        item = dict(con.execute('SELECT * FROM transactions WHERE id=?', (item_id,)).fetchone())
    return jsonify(item)


@app.delete('/api/transactions/<int:item_id>')
def delete_transaction(item_id):
    with db() as con:
        cur = con.execute('DELETE FROM transactions WHERE id=?', (item_id,))
        if not cur.rowcount: return jsonify(error='Not found'), 404
    return jsonify(success=True)


@app.get('/api/suppliers')
def get_suppliers(): return jsonify(rows('SELECT * FROM suppliers ORDER BY name'))


@app.post('/api/suppliers')
def add_supplier():
    d = request.get_json(silent=True) or {}
    if not str(d.get('name','')).strip(): return jsonify(error='Supplier name is required'), 400
    with db() as con:
        cur = con.execute('INSERT INTO suppliers(name,phone,opening_due,notes) VALUES(?,?,?,?)',
                          (d['name'].strip(), d.get('phone',''), money(d.get('opening_due')), d.get('notes','')))
        item = dict(con.execute('SELECT * FROM suppliers WHERE id=?', (cur.lastrowid,)).fetchone())
    return jsonify(item), 201


@app.delete('/api/suppliers/<int:item_id>')
def delete_supplier(item_id):
    with db() as con: con.execute('DELETE FROM suppliers WHERE id=?', (item_id,))
    return jsonify(success=True)


@app.get('/api/customers')
def get_customers(): return jsonify(rows('SELECT * FROM customers ORDER BY name'))


@app.post('/api/customers')
def add_customer():
    d = request.get_json(silent=True) or {}
    if not str(d.get('name','')).strip(): return jsonify(error='Customer name is required'), 400
    with db() as con:
        cur = con.execute('INSERT INTO customers(name,phone,notes) VALUES(?,?,?)', (d['name'].strip(), d.get('phone',''), d.get('notes','')))
        item = dict(con.execute('SELECT * FROM customers WHERE id=?', (cur.lastrowid,)).fetchone())
    return jsonify(item), 201


@app.get('/api/summary')
def summary():
    tx = rows('SELECT * FROM transactions')
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    sales = sum(money(t['amount']) for t in tx if t['kind']=='sale' and t['txn_date'] >= month_start)
    expenses = sum(money(t['amount']) for t in tx if t['kind']=='expense' and t['txn_date'] >= month_start)
    credit = max(0, sum(money(t['amount']) for t in tx if t['kind']=='sale' and t['status']=='Pending') - sum(money(t['amount']) for t in tx if t['kind']=='collection'))
    supplier_due = sum(money(s['opening_due']) for s in rows('SELECT opening_due FROM suppliers'))
    supplier_due += sum(money(t['amount']) for t in tx if t['kind']=='purchase' and t['status']=='Pending')
    supplier_due = max(0, supplier_due - sum(money(t['amount']) for t in tx if t['kind']=='supplier_payment'))
    paid_in = sum(money(t['amount']) for t in tx if t['kind'] in ('sale','collection') and t['status']=='Paid')
    paid_out = sum(money(t['amount']) for t in tx if t['kind'] in ('expense','supplier_payment') and t['status']=='Paid')
    return jsonify({"sales":sales,"expenses":expenses,"profit":sales-expenses,"credit_sales":credit,
                    "supplier_dues":supplier_due,"cash_balance":paid_in-paid_out,
                    "transaction_count":len(tx),"currency":"INR"})


@app.get('/api/projection')
def projection():
    tx = rows('SELECT * FROM transactions')
    today = date.today()
    last30 = today - timedelta(days=30)
    income = [money(t['amount']) for t in tx if t['kind'] in ('sale','collection') and t['status']=='Paid' and t['txn_date'] >= last30.isoformat()]
    outgo = [money(t['amount']) for t in tx if t['kind'] in ('expense','supplier_payment') and t['status']=='Paid' and t['txn_date'] >= last30.isoformat()]
    daily_in = sum(income)/30 if income else 0
    daily_out = sum(outgo)/30 if outgo else 0
    return jsonify({"days":30,"daily_income_assumption":round(daily_in,2),"daily_expense_assumption":round(daily_out,2),
      "projected_inflow":round(daily_in*30,2),"projected_outflow":round(daily_out*30,2),
      "projected_net":round((daily_in-daily_out)*30,2),"basis":"Average paid inflow/outflow per day over the last 30 days; excludes unpaid invoices."})


@app.get('/api/credit-readiness')
def credit_readiness():
    s = summary().get_json()
    tx = rows('SELECT * FROM transactions')
    paid = sum(1 for t in tx if t['status']=='Paid')
    pending = sum(1 for t in tx if t['status']=='Pending')
    return jsonify({"disclaimer":"This is an informational business-record summary, not a lender decision, credit score, or loan approval.",
      "monthly_sales":s['sales'],"monthly_expenses":s['expenses'],"operating_surplus":s['profit'],
      "pending_customer_payments":s['credit_sales'],"supplier_dues":s['supplier_dues'],
      "recorded_transactions":len(tx),"paid_records":paid,"pending_records":pending,
      "suggestions":["Record every sale and expense with its date.","Update customer collections and supplier payments regularly.","Keep invoices and bank statements to support the business records."]})


@app.post('/api/import')
def import_csv():
    if 'file' not in request.files: return jsonify(error='Upload a CSV file using the file field'), 400
    f = request.files['file']
    try:
        raw = f.stream.read()
        if f.filename.lower().endswith(('.xlsx', '.xlsm')):
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            ws = wb.active
            values = ws.iter_rows(values_only=True)
            headers = [str(v or '').strip().lower() for v in next(values, ())]
            reader = [dict(zip(headers, row)) for row in values]
        else:
            stream = io.StringIO(raw.decode('utf-8-sig'))
            reader = csv.DictReader(stream)
        imported = 0
        with db() as con:
            for r in reader:
                kind = str(r.get('kind') or r.get('type') or '').strip().lower()
                if kind not in ('sale','expense','purchase','collection','supplier_payment'): continue
                amount = money(r.get('amount'))
                if amount <= 0: continue
                con.execute('''INSERT INTO transactions(kind,amount,category,party,note,payment_mode,status,due_date,txn_date)
                  VALUES(?,?,?,?,?,?,?,?,?)''',(kind,amount,r.get('category',''),r.get('party',''),r.get('note',''),r.get('payment_mode','Cash'),r.get('status','Paid'),r.get('due_date',''),r.get('txn_date') or date.today().isoformat()))
                imported += 1
        return jsonify(imported=imported, message=f'{imported} transactions imported')
    except Exception as e: return jsonify(error=f'Could not read CSV: {e}'), 400


@app.get('/api/export')
def export_csv():
    data = rows('SELECT id,kind,amount,category,party,note,payment_mode,status,due_date,txn_date FROM transactions ORDER BY txn_date DESC')
    fields = ['id','kind','amount','category','party','note','payment_mode','status','due_date','txn_date']
    if request.args.get('format') == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter
        output = io.BytesIO(); wb = Workbook(); ws = wb.active; ws.title = 'Transactions'
        ws.append(fields)
        for cell in ws[1]:
            cell.font = Font(bold=True, color='FFFFFF'); cell.fill = PatternFill('solid', fgColor='9678BE')
        for item in data: ws.append([item.get(k) for k in fields])
        for col in ws.columns:
            width = min(28, max(12, max(len(str(c.value or '')) for c in col)+2))
            ws.column_dimensions[get_column_letter(col[0].column)].width = width
        wb.save(output); output.seek(0)
        return Response(output.getvalue(), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition':'attachment; filename=vyaparsaathi-transactions.xlsx'})
    output = io.StringIO(); writer = csv.DictWriter(output, fieldnames=fields); writer.writeheader()
    for item in data: writer.writerow(item)
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition':'attachment; filename=vyaparsaathi-transactions.csv'})


@app.post('/api/chat')
def chat():
    data = request.get_json(silent=True) or {}
    message = str(data.get('message','')).strip()
    language = data.get('language','English')
    if not message: return jsonify(error='Please enter a question'), 400
    try:
        from google import genai
        key = os.getenv('GEMINI_API_KEY')
        if not key: return jsonify(error='Gemini is not configured. Add GEMINI_API_KEY in backend/.env.'), 503
        client = genai.Client(api_key=key)
        business = summary().get_json()
        recent = rows('SELECT kind,amount,category,party,status,txn_date FROM transactions ORDER BY id DESC LIMIT 30')
        instruction = ("You are VyaparSaathi, a careful financial assistant for Indian small merchants. "
          "Answer in the requested language. Use only the supplied business records for personal financial claims. "
          "Never invent numbers. Clearly state when records are insufficient. Do not claim loan approval or give guaranteed forecasts. "
          "For transaction-entry requests, explain that the user must confirm/add the transaction in the app; do not claim it was saved.")
        prompt = f"{instruction}\nLanguage: {language}\nBusiness summary: {json.dumps(business,ensure_ascii=False)}\nRecent transactions: {json.dumps(recent,ensure_ascii=False)}\nQuestion: {message}"
        response = client.models.generate_content(
    model=os.getenv('GEMINI_MODEL', 'gemini-3.8-flash'),
    contents=prompt
), 
        return jsonify(response=response.text or 'I could not prepare an answer. Please try again.')
    except Exception as e: return jsonify(error=f'Gemini request failed: {e}'), 502


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT',5000)), debug=False)
