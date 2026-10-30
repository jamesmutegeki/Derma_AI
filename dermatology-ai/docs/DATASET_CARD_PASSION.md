# Dataset card -- PASSION for Dermatology

| Field | Value |
| --- | --- |
| Full name | PASSION for Dermatology (Ugandan / African skin tones) |
| Source | PASSION project (Makerere / Uganda Cancer Institute collaboration), https://passionderm.github.io/ |
| Access | Separate data-use agreement; not redistributable |
| Size | ~19k clinical images (as published); the repository ships none of them |
| Labels | 12 disease categories; BCC/SCC excluded from the 3-class mapping and logged when skipped |
| Fitzpatrick | Balanced I-VI by design, with explicit Ugandan sourcing |
| Licence | Research use under the PASSION agreement; ethics approval required per project |
| Known biases | Clinical (phone-camera) rather than dermoscopic images -- different distribution from HAM10000 |
| Used for | Evaluation (`run_evaluation_passion.py`); training only once the DUA and IRB approval are in place |
| Caveat | Until S1-1 is frozen and IRB is granted, PASSION must not be loaded into a running service |
