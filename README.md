# 🤖 tradeAI

A crypto market analysis AI agent powered by a local LLM (via Ollama) and live Binance market data. Uses a ReAct (Reason + Act) loop to plan, call tools, observe results, and deliver analysis — all from your terminal.

---

## How It Works

tradeAI runs a ReAct loop: the agent reasons about your query, picks the right tool (price, RSI, EMA, order book, etc.), calls Binance's public API, observes the result, and loops until it can give you a final answer.

```
You ask → Agent plans → Calls Binance tool → Observes result → Repeats if needed → Final output
```

---

## Prerequisites

You need three things before running this project:

### 1. Python 3.10+
Download from [python.org](https://www.python.org/downloads/)

### 2. Ollama (local LLM runner)
Ollama runs the AI model locally on your machine.

**Install:**
```bash
# macOS / Linux
curl -fsSL https://ollama.com/install.sh | sh

# Windows — download installer from https://ollama.com/download
```

**Pull the required model:**
```bash
ollama pull llama3.2:3b
```

**Start Ollama** (keep this running in a separate terminal):
```bash
ollama serve
```

### 3. Internet access
Live market data is fetched from Binance's public API — no API key required.

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/ghogharimeet21/tradeAI.git
cd tradeAI

# 2. Install Python dependencies
pip install -r requirements.txt
```

---

## Running the Agent

Make sure Ollama is running (`ollama serve`), then:

```bash
python app.py
```

You'll see:
```
Market Agent ready. Type 'exit' to quit.

>>
```

Type any crypto question and hit enter.

---

## Example Queries

```
>> Is BTC overbought right now?
>> What's the current ETH price?
>> Is there a volume spike on SOLUSDT?
>> Show me the order book for BNBUSDT
>> What's the trend on ADAUSDT over the last 20 candles?
>> Give me EMA crossover signal for XRPUSDT on 1h
```

---

## Available Tools

The agent automatically picks the right tool based on your query:

| Tool | What it does | Example input |
|---|---|---|
| `get_price` | Current price | `BTCUSDT` |
| `get_ohlcv` | Recent OHLCV candles | `BTCUSDT,5m,10` |
| `get_orderbook` | Top bid/ask levels | `BTCUSDT,5` |
| `get_24h_stats` | 24h rolling stats | `BTCUSDT` |
| `calculate_sma` | SMA vs current price | `BTCUSDT,20,1m` |
| `calculate_ema` | Fast/slow EMA crossover | `BTCUSDT,9,21,1h` |
| `calculate_rsi` | RSI with overbought/oversold zones | `BTCUSDT,14,1h` |
| `detect_trend` | Uptrend / downtrend / sideways | `BTCUSDT,20,1h` |
| `check_volume_spike` | Volume vs rolling average | `BTCUSDT,20,1h` |

**Supported symbols:** `BTCUSDT`, `ETHUSDT`, `BNBUSDT`, `SOLUSDT`, `XRPUSDT`, `DOGEUSDT`, `ADAUSDT`, and most other Binance pairs.

**Supported intervals:** `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `1d`

---

## Project Structure

```
tradeAI/
├── app.py           # Main agent loop (ReAct logic, Ollama chat)
├── utils.py         # All tool functions (Binance API calls, indicators)
├── prompts.py       # System prompt with tool definitions and examples
├── constants.py     # Binance base URL
└── requirements.txt # Python dependencies
```

---

## Docker Setup (Optional)

If you prefer not to install Python or Ollama manually, Docker Compose handles everything in containers.

**`Dockerfile`**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "app.py"]
```

**`docker-compose.yml`**
```yaml
version: "3.9"

services:
  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

  tradeai:
    build: .
    stdin_open: true
    tty: true
    environment:
      - OLLAMA_HOST=http://ollama:11434
    depends_on:
      - ollama

volumes:
  ollama_data:
```

**Run with Docker:**
```bash
# Start both containers
docker-compose up --build

# In a separate terminal, pull the model into the Ollama container
docker exec -it tradeai-ollama-1 ollama pull llama3.2:3b
```

---

## Requirements

```
ollama
requests
```

Install with:
```bash
pip install -r requirements.txt
```

---

## Disclaimer

This tool is for **educational and informational purposes only**. It is not financial advice. Always do your own research before making any trading decisions. Crypto markets are highly volatile.
