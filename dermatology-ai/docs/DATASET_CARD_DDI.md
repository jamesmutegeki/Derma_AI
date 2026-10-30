# Dataset card -- DDI (Diverse Dermatology Images)

| Field | Value |
| --- | --- |
| Full name | Diverse Dermatology Images |
| Source | Stanford AIMI / Daneshjou et al. (2022) |
| DOI | 10.71718/kqee-3z39 |
| Access | Request from Stanford AIMI; governed by its own data-use agreement |
| Size | **656 images from 570 patients** |
| Fitzpatrick distribution | 208 (I-II), 241 (III-IV), 207 (V-VI) |
| Labels | Pathologically confirmed across three groups: benign, malignant, non-neoplastic |
| Licence | Research use under the DDI data-use agreement -- **not redistributable** |
| Known biases | Small; dermatologist-selected difficult cases, so it is deliberately harder than a random sample |
| Used for | Fairness auditing of skin-tone performance (not for training unless the agreement allows it) |
| Correction | Earlier documents in this repository described DDI as "12k images, 30+ classes". That was wrong; the published set is 656 images |
