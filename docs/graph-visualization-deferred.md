# Graph visualization roadmap (deferred items)

Implementing these well requires extra telemetry shape, tooling, or layout beyond what the TerraMetric SPA uses today:

- **OHLC candlestick charts** — The timeseries payload is a single aggregated value per timestamp (typically mean per bucket after binning). Candlesticks need explicit open/high/low/close per interval from the backend or a client-side rollup when raw points remain available inside each bucket.
- **Financial-style intraday overlays** — Volume or bid/ask are out of scope for plant telemetry.
- **Horizon graphs and streamgraphs** — Dense multi-series summaries are better suited to libraries such as Vega-Lite/D3 than to Chart.js on the researcher cards; optionally export CSV and analyse in Jupyter.
- **Autocorrelation / partial ACF plots** — Need a uniformly spaced numeric series across a stationary window plus a lightweight stats layer (prefer server-side pandas/NumPy for large N).
- **Seasonal decomposition (STL, Fourier)** — Likewise server-side pipelines or notebooks; exposing only in the SPA would duplicate heavy logic.
- **Stacked-area multi-series on one axes** — The product currently uses four fixed small-multiples (one environmental channel per chart). Showing `temp+humi+light+height` stacked on one timeline would distort physical units unless normalised — keep as a deliberate product trade-off unless requirements change.
