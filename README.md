📈 AlphaPulse Crypto Screener & Backtester

AlphaPulse is a lightweight, open-source quantitative crypto screener and backtesting terminal. Designed for day traders and swing traders, it autonomously scans the top 50 Binance USDT pairs to detect high-probability mean-reversion setups driven by institutional volume spikes.

Built natively in Python using Pandas math to ensure maximum compatibility and zero C++ compilation errors, this dashboard goes beyond simple charting by offering an integrated historical backtesting engine to instantly validate signals.

✨ Key Features

Algorithmic Scanning: Filters out market noise by exclusively flagging assets that meet a strict, 3-part quantitative criteria.

Native Vectorized Math: Calculates RSI, EMA, and SMA using pure Pandas. No heavy libraries like pandas_ta or numba required, guaranteeing a flawless installation on any machine or cloud server.

Integrated Backtesting: Instantly simulate the strategy's historical performance on any asset with 1-click, utilizing the backtesting.py engine.

Zero-Cost Architecture: Pulls live market data entirely for free via the public CCXT Binance API (no API keys required).

Interactive UI: Built with Streamlit for a clean, responsive, and dynamic web-based dashboard.

🧠 The Strategy Logic

AlphaPulse does not rely on lagging indicator crosses. It hunts for the "Institutional Reload"—a specific setup where an asset in a macro uptrend experiences a brief, oversold pullback followed by aggressive buying volume.

A BUY signal is only triggered when ALL of the following conditions are met on the 1-Day timeframe:

The Macro Trend (EMA 200): The current price must be above the 200-day Exponential Moving Average. This ensures we are buying dips in a bull market, avoiding "falling knives."

The Exhaustion (RSI 14): The 14-period Relative Strength Index must drop below 30, signaling immediate short-term exhaustion.

The Catalyst (Volume Surge): The current 24-hour volume must be strictly greater than 150% of the 20-day Simple Moving Average of volume. This proves that smart money is actively stepping in to buy the dip.

🚀 Quick Start (Local Deployment)

1. Clone the repository

git clone https://github.com/YourUsername/AlphaPulse.git
cd AlphaPulse


2. Set up the virtual environment

It is highly recommended to use Python 3.10 or 3.11.

python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate


3. Install dependencies

pip install -r requirements.txt


4. Launch the dashboard

streamlit run app.py


The dashboard will automatically open in your default web browser at http://localhost:8501.

☁️ Cloud Deployment (Streamlit Community Cloud)

This project is fully optimized for free deployment on Streamlit Community Cloud.

Push this repository to your GitHub.

Visit share.streamlit.io.

Click "Create App", select your repository, and set the main file path to app.py.

Click Deploy. The built-in @st.cache_data decorators will automatically manage Binance API rate limits to prevent your server from getting temporarily banned.

⚠️ Disclaimer

Not Financial Advice. AlphaPulse is an educational and research tool. Cryptocurrency trading involves substantial risk of loss and is not suitable for every investor. The backtesting results presented by this software are hypothetical and do not guarantee future results. Always conduct your own due diligence and consult with a licensed financial advisor before making trading decisions.
