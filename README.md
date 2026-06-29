# 🛰️ ISRO NetOps Predictive Co-Pilot

A predictive, air-gapped, ML-powered Network Operations (NetOps) co-pilot built for secure environments. It leverages predictive analytics, RAG (Retrieval-Augmented Generation), and interactive 3D visualizations to anticipate and mitigate network failures before they happen.

## ✨ Features

- **🔒 Air-Gapped Operation:** Designed to run entirely offline with local ML models and vector embeddings. Zero egress.
- **🚀 3D Landing Page:** Immersive WebGL globe landing page.
- **🔐 Multi-Level Security (MLS) Auth:** Robust authentication portal with clearance levels and face scan/biometric simulation.
- **🔮 Predictive Analytics:** Analyzes network telemetry (SNMP) using rolling features to forecast failures using Random Forest models.
- **💬 RAG-Grounded Co-Pilot:** Built-in chat assistant that queries indexed technical runbooks to guide operators during critical alerts.
- **🕸️ Topology & Risk Graph:** Interactive visual mapping of network devices and their real-time risk scores.

## 🛠️ Architecture

- **Frontend/Dashboard:** Streamlit with custom CSS (Stitch dark theme) and embedded iframe routing.
- **Backend Analytics:** Pandas, Scikit-Learn (Random Forest) for feature engineering and ML failure classification.
- **RAG Pipeline:** Sentence-Transformers (`all-MiniLM-L6-v2`) for local embeddings, with TF-IDF fallback for strict zero-download environments.
- **Data Simulation:** Custom robust simulation for SNMP metrics and syslog generation simulating real-world network turbulence.

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- `pip` package manager

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/tanay1-techy/PS-13-.git
   cd PS-13-
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the Dashboard:**
   ```bash
   cd copilot
   streamlit run app/dashboard.py
   ```

## 🎮 Usage Flow
1. Navigate to the initial landing page.
2. Click **"Launch Dashboard"** to enter the Auth Portal.
3. Use Demo Credentials to login: 
   - **ID:** `JESH2789` or `isro_admin`
   - **Access Code:** `12345678` or `ISRO@2026`
4. The backend ML models and RAG knowledge base pre-warm during authentication.
5. Enter the main dashboard to view the predicted failure alerts and interact with the AI Co-Pilot for resolution runbooks.

## 🛡️ License
Private and Confidential. For demonstration and hackathon purposes only.
