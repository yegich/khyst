---
name: stress-review
description: Review Ukrainian text for correct stress mark placement. Useful when preparing TTS scripts.
allowed-tools: Read, Edit, Grep, Glob
---

Review the Ukrainian text in the given file for stress mark accuracy.

For each word:
1. Check if the stress mark (combining acute accent U+0301) is on the correct vowel
2. Flag words with missing stress marks
3. Flag words where stress placement looks wrong based on standard Ukrainian pronunciation rules

Output a summary of issues found and fix them if the user confirms.
