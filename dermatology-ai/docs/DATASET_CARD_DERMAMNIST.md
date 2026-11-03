# Dataset card -- DermaMNIST (MedMNIST)

| Field | Value |
| --- | --- |
| Full name | DermaMNIST (MedMNIST v2 / MedMNIST+) |
| Source | Yang et al., *Scientific Data* 2023; `pip install medmnist` |
| Access | **Immediate** -- one pip install, ~20 MB at 28x28, ~1.09 GB at 224x224 |
| Provenance | HAM10000, re-split and resized by the MedMNIST authors |
| Labels | The seven HAM10000 classes (nv, mel, bkl, bcc, akiec, vasc, df) |
| Fitzpatrick metadata | **None** (inherited gap from HAM10000) |
| Licence | **CC BY-NC 4.0** |
| Known biases | 28x28 destroys texture and border detail; the official split is by image, not by lesion |
| Used for | CI, smoke runs, teaching, pipeline checks -- **not** for any clinical result |
| Caveat | A number measured on 28x28 images is a property of the resize, not of dermatology |

## Why it is in the repository

It is the fastest honest way to prove the machinery works: one command, no
download, no request, no waiting. `scripts/train_model.py --smoke` and the test
suite use data this small on purpose, and every report from it is `valid: false`
so it can never be frozen into the manifest.
