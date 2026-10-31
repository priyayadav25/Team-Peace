# VyaparSaathi — Your Business, Your Saathi

A responsive small-business finance dashboard inspired by the supplied WhatsApp UI references and the VyaparSaathi pastel-gradient logo. The React interface adapts to desktop and mobile; Flask provides persistent transaction and reporting APIs.

## Included features

- Responsive desktop sidebar and mobile bottom navigation
- Logo-led ivory, coral, orange, lavender and mint visual system
- English / Hindi interface toggle
- Dashboard: sales, expenses, net profit, customer credit and supplier dues
- Add and record sales, expenses, purchases, collections and supplier payments
- Customer credit sales with pending/paid status and due dates
- Supplier and customer directories
- Transaction search, filtering and deletion
- 30-day cash-flow projection based on the previous 30 days of paid inflow/outflow; assumptions are shown
- Gemini-powered Hindi/Hinglish/English business Q&A using saved business records as context
- Browser speech-to-text voice input (Chrome/Edge support recommended)
- CSV import and CSV export (opens in Excel / Google Sheets)
- Downloadable JSON business summary and credit-readiness information report
- SQLite persistence by default; optional Firebase Authentication and Firestore mirror for newly created records
- Cloud Run-ready Flask container

> Credit-readiness is an informational summary of records, not a lender decision, credit score or loan approval. The 30-day projection is an estimate based on historical paid transactions, not a guarantee.

## 1. Run the backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Windows: copy .env.example .env
# Add GEMINI_API_KEY to .env to enable AI Q&A
python app.py
```

Backend runs at `http://localhost:5000`. SQLite database is created automatically at `backend/vyaparsaathi.db`.

## 2. Run the frontend

In a second terminal:

```bash
cd frontend
npm install
cp .env.example .env   # Windows: copy .env.example .env
npm start
```

Open `http://localhost:3000`.

## 3. Gemini API

Create a Gemini API key in Google AI Studio and set `GEMINI_API_KEY=...` in `backend/.env`. Restart Flask. Without a key, the rest of the app works and the AI assistant returns a clear setup message.

## 4. Firebase Authentication + Firestore (optional cloud identity and mirror)

1. Create a Firebase project and register a Web App.
2. Enable **Authentication → Email/Password**.
3. Create a **Cloud Firestore** database.
4. Copy the Firebase Web App values into `frontend/.env` using the `REACT_APP_FIREBASE_*` variables.
5. Set Firestore rules so signed-in users can only read/write their own `users/{uid}` subtree. A starting rule is:

```text
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId}/{document=**} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
  }
}
```

6. Restart/rebuild the frontend. When Firebase config is present, the app shows a sign-in/sign-up screen and mirrors newly created transactions, suppliers and customers to the signed-in user's Firestore workspace. The Flask SQLite database remains the operational source for dashboard calculations and exports; configure backups for both stores before production use.

## 5. CSV format

Required columns: `kind`, `amount`. Optional: `txn_date`, `category`, `party`, `note`, `payment_mode`, `status`, `due_date`.

Allowed `kind` values: `sale`, `expense`, `purchase`, `collection`, `supplier_payment`. `status` should be `Paid` or `Pending`. Example:

```csv
kind,amount,txn_date,category,party,status,payment_mode
sale,1250,2026-10-30,Counter sale,Rahul,Paid,UPI
expense,300,2026-10-30,Transport,,Paid,Cash
sale,900,2026-10-31,Credit sale,Meena,Pending,Credit
```

## 6. Deploy backend to Google Cloud Run

From the `backend` directory:

```bash
gcloud run deploy vyaparsaathi-api --source . --region asia-south1 --allow-unauthenticated --set-env-vars GEMINI_MODEL=gemini-2.5-flash
```

Set `GEMINI_API_KEY` as a Secret Manager-backed environment variable in Cloud Run. For production, use a persistent database (Firestore or Cloud SQL) rather than the container's local SQLite filesystem, restrict CORS to the deployed frontend domain, and require authenticated API access. Deploy the React frontend on Firebase Hosting or another static host and set `REACT_APP_API_URL` to the Cloud Run URL before building.

## Project structure

```text
VyaparSaathi_Final_Build/
  backend/       Flask API, SQLite storage, Gemini integration, Cloud Run Dockerfile
  frontend/      React app, responsive styling, logo and supplied UI references
```
