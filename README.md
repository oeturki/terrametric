# TerraMetric — Frontend
Indoor Plant Research Monitoring Dashboard · Group 14

## File Structure

```
terrametric/
│
├── index.html          ← Open this in a browser to run the app
│
├── css/
│   └── styles.css      ← All visual styling (colours, layout, fonts)
│
└── js/
    ├── config.js       ← ⭐ THE ONLY FILE YOU NEED TO EDIT
    ├── alerts.js       ← Toast notifications, bell icon, warning banner
    ├── charts.js       ← All graph drawing (uses Chart.js)
    ├── home.js         ← Stat cards, ESI gauge, anomaly table
    ├── samples.js      ← Manage Samples page + Gallery timeline
    ├── api.js          ← All communication with the server
    └── app.js          ← Navigation, connection check, boot sequence
```

## To connect your system

Open `js/config.js` and change one line:

```javascript
PI_IP: 'YOUR-PI-IP',   // e.g. '192.168.1.42'
```

That's it. Everything else connects automatically.

## To run it

Double-click `index.html` — it opens straight in any browser.
No installation needed.

## Pages

| Page | What it does |
|---|---|
| Home | Live stat cards, ESI gauge, recent alerts |
| View Data → Graphs | Live sensor charts with threshold lines |
| View Data → Gallery | Plant growth photo timeline per sample |
| View Data → Anomalies | Spike/drift/missing data detection |
| Control Variables | Set warning thresholds and sensor intervals |
| Manage Samples | Register plants, assign QR codes |
