# Vibes Frontend

React-based frontend for the Vibes inventory and restaurant management platform.

---

## Tech Stack

- **Framework:** React 19
- **Build Tool:** Vite
- **Styling:** Tailwind CSS v4
- **Routing:** React Router DOM v7
- **HTTP Client:** Axios
- **Charts:** Recharts
- **Icons:** Lucide React, React Icons, Phosphor React
- **Notifications:** React Toastify
- **Excel:** SheetJS (xlsx)

---

## Project Structure

```
frontend/
├── public/                   # Static assets & Excel template downloads
│   ├── inventory_upload_sample.xlsx
│   ├── dish_upload_sheet.xlsx
│   ├── wastage_excel_format.xlsx
│   └── ...
├── src/
│   ├── api/
│   │   └── axios.js          # Axios instance & interceptors
│   ├── components/
│   │   ├── Inventory Management/
│   │   ├── Dish Management/
│   │   ├── WastageManagement/
│   │   ├── OrderManagement/
│   │   ├── MonthlyReconciliation/
│   │   ├── RemainingInventory/
│   │   └── ReportAndAnalysis/
│   ├── context/              # Theme & sidebar context
│   ├── layouts/              # Dashboard layout
│   ├── pages/                # Login, alerts, protected routes
│   ├── services/             # API service functions
│   └── utils/                # Excel download helpers, text utils
├── package.json
└── vite.config.js
```

---

## Setup

### 1. Navigate to frontend directory

```bash
cd VIBES/frontend
```

### 2. Install dependencies

```bash
npm install
```

### 3. Configure API base URL

In `src/api/axios.js`, make sure the base URL points to your running backend:

```js
baseURL: "http://localhost:8000"
```

### 4. Start the dev server

```bash
npm run dev
```

App will be available at `http://localhost:5173`.

---

## Available Scripts

```bash
npm run dev        # Start development server
npm run build      # Build for production
npm run preview    # Preview production build locally
npm run lint       # Run ESLint
```

---

## Connecting to Backend

Make sure the backend is running before starting the frontend. If using Docker:

```bash
# From VIBES/backend
docker-compose -f docker-compose-local.yml up -d --build
```

Backend API: `http://localhost:8000`  
Frontend dev server: `http://localhost:5173`
