# Commercial Wake-Word Licensing Note & Alternatives

## Current Model License Constraint
- **openWakeWord library:** Apache License 2.0 (`Apache-2.0`).
- **Included Pretrained Models (e.g., `hey_jarvis_v0.1.onnx`):** Creative Commons Attribution-NonCommercial-ShareAlike 4.0 (**`CC-BY-NC-SA-4.0`**).
- **Implication:** Personal, educational, and non-commercial use is permitted with attribution, while commercial redistribution requires replacing the `CC-BY-NC-SA-4.0` `.onnx` model weights with a permissively licensed or custom-trained model.

## Commercial-Friendly Options (Future Reference)
1. **Custom-Trained openWakeWord Model (Apache-2.0 Runtime):**
   - Train a brand-new custom `.onnx` wake-word model solely on commercially cleared/synthetic audio datasets while keeping the Apache-2.0 `openWakeWord` inference library.
2. **Permissive Open-Source Alternatives:**
   - **Silero VAD + Small Local Keyword Classifier (MIT/Apache-2.0):** Combine MIT-licensed Silero VAD gating with a custom Apache-2.0/MIT-trained keyword spotter (e.g. ONNX ResNet/DS-CNN trained on permissively licensed datasets).
   - **Vosk / Kaldi Small English Keyword Spotter (Apache-2.0):** Local grammar-constrained keyword recognition under Apache-2.0.
3. **Commercial Licensed SDKs (if external licensing is acceptable):**
   - Proprietary commercial wake-word engines with explicit per-seat/commercial agreements (note: requires reviewing offline & privacy requirements).
