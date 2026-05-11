# Epistemic Reclaimer — Step 6 of the Scribalicious Pipeline

This tool helps you reclaim authorship over AI-assisted or AI-suspected text by disrupting common AI fingerprinting patterns and embedding a **custom authorship watermark**. It's designed for anyone who wants to retain creative sovereignty, prevent invisible tagging, or declare epistemic responsibility over their words.

---

## 🚀 What It Does

- **Detects** suspected AI fingerprint patterns (e.g. GPT-typical vocabulary, invisible formatting tokens)
- **Disrupts** those patterns using controlled entropy injection
- **Embeds** your own semantic watermark:
  - a visible integrity signature block
  - an invisible Unicode-based fingerprint
  - an optional poetic or declarative tagline

---

## ✍️ Personalize It

Open `epistemic_reclaimer.py` and edit this section:

```python
# === PERSONALIZE THIS BLOCK ===
AUTHOR_NAME = "Your Name or Alias Here"
WATERMARK_TAGLINE = "Custom message or signature phrase here."
INVISIBLE_WATERMARK = '\u200c\u200b\u200d'  # Can be customized
# ===============================
