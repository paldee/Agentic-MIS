# Agentic-MIS: Optimized BI Agent with Hybrid Architecture

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Google ADK](https://img.shields.io/badge/Framework-Google%20ADK-orange)
![Gemini](https://img.shields.io/badge/LLM-Gemini%202.5%20Flash-green)
![Gradio](https://img.shields.io/badge/UI-Gradio-lightgrey)

An intelligent, highly optimized Business Intelligence (BI) Assistant that converts natural language into SQL, executes queries against an MS SQL Server, and automatically generates visualizations and business insights. 

This project evolved from a standard Linear Agentic Workflow into a **Hybrid Orchestration Architecture**, reducing response latency by **~70%** and API cost by **>50%**.

## 🚀 Key Features

- **High-Accuracy Text-to-SQL:** Utilizes compressed schema injection and few-shot prompting to achieve a 10/10 SQL generation accuracy, specifically optimized for MS SQL Server (T-SQL).
- **Hybrid Orchestration:** Bypasses LLM for deterministic tasks (like SQL execution) by using direct Python functions, drastically reducing API dependency and preventing HTTP 429 (Resource Exhausted) errors.
- **Fast Track (Heuristic Visualization):** A Python-based routing logic that detects simple data shapes (e.g., 2 columns, < 20 rows) and generates Altair charts instantly, bypassing the LLM analysis step for lightning-fast responses.
- **Unified Analysis Agent:** Merges visualization and explanation tasks into a single LLM call for complex queries, complete with robust JSON parsing.

## 🧠 Architecture Evolution: The Optimization Journey

### 🔴 V1: The Baseline (Full Sequential Agent)
Initially built using a strict Sequential Agent chain: 
`Text-to-SQL -> SQL Executor (AI) -> Data Formatter (AI) -> Visualization (AI) -> Explanation (AI)`
- **Issues:** High latency, frequent API quota limits (4-5 calls/query), and inconsistent visualization choices.

### 🟢 V2: The Final Hybrid Architecture
Redesigned the system to use **Manual Orchestration (`app.py`)**:
1. **AI Generation:** LLM generates SQL based on a filtered, compressed database schema.
2. **Python Execution:** Python directly executes the SQL (Zero API calls, < 3 seconds).
3. **Smart Routing:** - *Fast Track:* Simple data is visualized instantly via Python rules.
   - *Deep Analysis:* Complex data is sent to a single, unified 2-in-1 AI Agent.

## 📊 Performance Metrics

| Architecture Phase | Accuracy | Latency | API Calls/Query | Visualization Quality |
| :--- | :---: | :---: | :---: | :--- |
| **1. Original Baseline** | 5/10 | 32.4s | 4 - 5 | Poor (Wrong chart types) |
| **2. Cut Middleman** | 5/10 | ~28.0s | 3 - 4 | Poor |
| **3. Prompt Engineering** | 10/10 | ~27.8s | 3 - 4 | Average (Fixed SQL, bad charts) |
| **4. Final Hybrid (Fast Track)**| **10/10** | **~10.0s** ⚡️ | **1 - 2** | **Excellent (Context-aware)** |

## 🛠️ Tech Stack

- **Core Logic:** Python, Pandas
- **LLM & Framework:** Google Gemini 2.5 Flash, Google ADK (Agent Development Kit)
- **Database:** Microsoft SQL Server
- **Visualization:** Altair
- **Frontend:** Gradio

## ⚙️ Installation & Setup

1. Clone the repository:
   ```bash
   git clone [https://github.com/your-username/Agentic-MIS.git](https://github.com/your-username/Agentic-MIS.git)
   cd Agentic-MIS

