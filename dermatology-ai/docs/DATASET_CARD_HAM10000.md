# Dataset card -- HAM10000

| Field | Value |
| --- | --- |
| Full name | Human Against Machine with 10000 training images |
| Source | Tschandl, Rosendahl & Kittler (2018), *Scientific Data* 5:180161 |
| Access | Public (Harvard Dataverse / Kaggle mirrors) |
| Size | 10,015 dermoscopic images, 7 diagnostic categories |
| Labels | Actinic keratosis, basal cell carcinoma, benign keratosis, dermatofibroma, melanoma, melanocytic nevus, vascular lesion |
| Mapping used here | Collapsed to 3 classes: `benign`, `melanoma`, `kaposi_sarcoma` (see `datasetEquity.CLASSES`) |
| Fitzpatrick metadata | **Not provided.** The pipeline uses a placeholder value; treat every per-type result on HAM10000 as meaningless |
| Licence | CC BY-NC 4.0 -- non-commercial use only |
| Known biases | Predominantly light skin; dermoscopic (not phone-camera) images; single-centre acquisition |
| Used for | Training and hold-out evaluation (`run_evaluation_ham.py`) |
| Caveat | Any fairness statement computed on HAM10000 alone is unsupported -- HAM10000 cannot measure the Fitzpatrick IV-VI gap |
