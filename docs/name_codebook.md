# Staff name codebook — information theory under Whisper’s token budget

**Status:** living methods note (dissertation / book trail)  
**Companion:** [`whisper_prompt_budget.md`](whisper_prompt_budget.md)  
**Code:** `edupulse/name_codebook.py` → wired from `build_enhanced_initial_prompt` + `semantic_map` resolver  
**Artifact:** `~/edupulse/name_codebook.json` (regenerated when the live fingerprint is built)

---

## 1. Idea

Whisper’s fingerprint is a **rate-limited channel** (~223 BPE tokens). We cannot feed 90 full last names. The natural next step is:

1. **Encode** staff names into the smallest *usable* package  
2. Put that package in `initial_prompt`  
3. **Decode** ASR output back to canonical `staff_names.txt` lines on the backend  

That is classic source → channel → sink thinking. The twist is what “bit” means here.

---

## 2. Why not true binary packing?

| Scheme | Prompt contains | When someone says “Yannett” | Works? |
|--------|-----------------|------------------------------|--------|
| Huffman / bitstring | `0x4F`, `10110` | Whisper emits English-ish text, not your bits | **No** |
| Opaque IDs | `T17` | Model does not learn ID↔name from `initial_prompt` alone | **No** |
| **Phonetic short codes** | `Yann`, `Maye` | Model may emit `Yann` / `Yannett` / `Deannette` → codebook expands | **Yes** |

`initial_prompt` **biases orthography**; it is not a programmable codec. Opaque codes are a useful **negative result** for the book: Shannon compression of the *name list* is not the same as compression of a *prompt that must still look like speech*.

**Cost unit = Whisper BPE length**, not raw bits. Uniform identity needs only \(\log_2(90)\approx 6.5\) bits, but the channel that must carry *speakable* aliases is far greedier.

---

## 3. Codebook v1 (constrained min-BPE prefixes)

For each unique last name:

1. Consider prefixes of the real spelling with length ≥ **4** (phonetic floor — naive SUP yields useless `Y` for Yannett).  
2. Keep prefixes that no other last name shares (unique prefix / separating system).  
3. Among survivors, pick **minimum BPE cost** (tie → longer, closer to full name).  
4. Merge hand ASR confusions (`deannette`→`yannett`, `mase`→`mayes`, …) into decode keys.  

**Encode (prompt):** space-separated `Codes: Yann Maye …` plus hot `Call:` / `Phrases:` tail.  
**Decode (backend):**  
1. `expand_transcript_names` — terminal + sidecar `transcription` show **canonical last names** (`Yannett`, not `Yanne`); optional `transcription_raw` keeps pre-expand ASR.  
2. token → codebook / hand aliases → title-aware staff resolve → enrollment uses full `Ms. Cheryl Yannett`, never the short code.

```text
staff_names.txt  ──build──►  NameCodebook  ──pack≤223──►  Whisper initial_prompt
                                   │
                                   ▼
                            ASR transcript
                                   │
                                   ▼
                         normalize_with_codebook
                                   │
                                   ▼
                      parse_radio_call / enroll (canonical)
```

---

## 4. Metrics to report

From `NameCodebook.metrics()` / `name_codebook.json`:

- `n_last_names`  
- `bpe_sum_full` vs `bpe_sum_alias` (compression on the name list itself)  
- `shannon_bits_uniform` = \(\log_2 n\) (theoretical ID cost — contrast with BPE)  
- How many aliases fit in the live prompt under 223 after terms + hot tail  

---

## 5. Gold case

Live miss: `Deannette to Mr. Mase.`  
Decode keys map both inventions → Yannett / Mayes even before ASR improves.  
Compressed + codebook prompt aims for `Yannett to Mr. Mayes` at the ASR layer and two-ID enrollment at the protocol layer.

---

## 6. Future (not v1)

- Frequency-weighted lengths (Huffman-flavored: hot radio names get shorter codes / guaranteed slots).  
- Title-bearing codes for ambiguous lasts (`Medlin` ×3).  
- Learned aliases from confusion matrices on gold WAVs.
