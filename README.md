# Dermatology AI

AI-powered dermatology triage and diagnosis support system with clinician-in-the-loop (HITL) reinforcement learning.

## Overview

Dermatology AI is a clinical decision support system designed to assist dermatologists in triaging skin lesions and making more accurate diagnoses. The system uses machine learning models to analyze dermoscopic images and provide AI-assisted diagnoses, while keeping the clinician in the loop through a Human-in-the-Loop (HITL) approach.

### Key Features

- **AI-Powered Triage**: Automatically triages skin lesions based on ABCD criteria (Asymmetry, Border, Color, Diameter)
- **Clinician-in-the-Loop (HITL)**: Reinforcement learning module that incorporates clinician feedback to improve accuracy
- **Fairness & Equity**: Built-in bias detection and dataset equity analysis to ensure fair treatment across all Fitzpatrick skin types
- **Metrics Tracking**: Comprehensive analytics dashboard for monitoring system performance
- **Case History Management**: Full patient case history tracking with visit notes and AI findings

## System Requirements

- Python 3.10+
- Windows/Linux/macOS
- Web browser (Chrome, Firefox, Edge, Safari)

## Installation

1. **Clone the repository**
```bash
git clone https://github.com/jamesmutegeki/Derma_AI.git
cd Derma_AI
```

2. **Create and activate virtual environment**
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/macOS
source venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

## How to Run

1. **Start the virtual environment** (if not already activated)
```bash
# Windows
venv\Scripts\activate

# Linux/macOS
source venv/bin/activate
```

2. **Run the application**
```bash
python main.py
```

3. **Access the application**
Open your browser and navigate to:
```
http://localhost:7860
```

## Login Credentials

### Admin Account
- **Username**: `admin`
- **Password**: `admin123`

### Doctor Accounts
Use your registered email and the default password `Doctor123!`

| Name | Email |
|------|-------|
| Dr. James Doe | j.doe@hospital.org |
| Dr. Mercy Okonkwo | m.okonkwo@hospital.org |
| Dr. Sarah Kimani | s.kimani@hospital.org |
| Dr. Grace Wanjiku | g.wanjiku@hospital.org |
| Dr. Peter Kamau | p.kamau@hospital.org |
| Dr. Linda Nyambura | l.nyambura@hospital.org |

## Project Structure

```
Dermatology_AI/
├── main.py              # Application entry point
├── server.py            # Backend server (FastAPI)
├── ui.py                # User interface components
├── model.py             # ML model for diagnosis
├── hitl_pipeline.py     # Human-in-the-Loop reinforcement learning
├── rl_module.py         # Reinforcement learning module
├── dashboard.html       # Analytics dashboard
├── poster.html          # Project poster
├── slides.html          # Presentation slides
├── doctors.json         # Doctor accounts data
├── patients.json        # Patient records
├── case_history.json   # Case history data
├── activity.json        # Activity log
├── notes.json           # Clinical notes
├── agent_params.pt     # ML model parameters
├── metrics_tracker.py   # Performance metrics
├── datasetEquity.py     # Fairness analysis
├── samplesEquity.py     # Sample equity analysis
├── requirements.txt     # Python dependencies
└── render.yaml         # Render deployment config
```

## Technology Stack

- **Backend**: Python with FastAPI
- **ML Model**: PyTorch (CNN-based dermatology classifier)
- **Frontend**: HTML/CSS/JavaScript
- **Data Storage**: JSON files
- **Deployment**: Docker-ready (Render.com compatible)

## Supported Diagnoses

The system can assist with triage for:
- Melanoma
- Basal Cell Carcinoma (BCC)
- Squamous Cell Carcinoma (SCC)
- Dysplastic Nevus
- Actinic Keratosis
- Hemangioma
- Vitiligo
- Acne
- Psoriasis
- And more...

## Fitzpatrick Skin Types

The system supports all Fitzpatrick skin types (I-VI) and includes equity analysis to ensure fair diagnosis across diverse patient populations.

## License

MIT License

## Author

Dr. James Doe - Board-Certified Dermatologist

## Acknowledgments

- Research team
- Contributing clinicians
- Open source community
