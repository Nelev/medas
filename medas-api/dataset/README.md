# Synthetic test dataset

Test data for the retrieval and document-ingest paths: two more patient records, 16 PDFs for the seeded patient (appointments, prescriptions, a lab report, letters, and the documents that must be turned away), and 32 evaluation questions. **Everything here is invented.** The people, clinicians, organisations, hospital numbers and phone numbers are all fictional (phone numbers use the 01632 960 range, which Ofcom reserves for drama).

The dataset's "today" is **2026-09-28**. Some questions ("next appointment", "which injection now") only have one right answer relative to that date.

```
dataset/
  records/pat_ferrante.json      second patient, for isolation and per-record answers
  records/pat_okoro.json         sparse, pregnant, edge-case record
  documents/D01..D16_*.pdf       PDFs for the seeded patient (Mattia Smacchia)
  documents/manifest.json        the expected ingest outcome for each PDF, and why
  generate_pdfs.py               rebuilds the PDFs
  eval/questions.jsonl           questions, the sources each answer must cite, the expected severity
```

Rebuild the PDFs (reportlab and pypdf come from `--with`, so they don't end up in the lockfile):

```bash
uv run --with reportlab --with pypdf python dataset/generate_pdfs.py
```

## What the new data adds to the seeded record

The documents follow on from `rag_pipeline/medical_history.json`, whose latest entry is the 2026-07-28 annual review:

| Date       | Doc | What happens                                                                                 |
| ---------- | --- | -------------------------------------------------------------------------------------------- |
| 2026-08-09 | D08 | Otitis externa on holiday in Italy; ear drops (report in Italian)                            |
| 2026-08-18 | D04 | GP starts omeprazole for GORD (the JSON lists GORD with no treatment); nasal spray and rinse |
| 2026-08-20 | D13 | Pharmacy collection receipt, with a marketing page attached                                  |
| 2026-09-02 | D06 | Bloods: vitamin D low (new finding), IgE high, eosinophils suppressed                        |
| 2026-09-10 | D02 | ENT: nasal polyps have come back; switch mepolizumab to dupilumab; follow-up 3 Dec           |
| 2026-09-15 | D01 | Physio appointment on 14 Oct                                                                 |
| 2026-09-22 | D03 | Dupilumab prescribed from 6 Oct, **mepolizumab discontinued**                                |
| 2026-09-25 | D05 | Dentist prescribes **naproxen**, an NSAID, to a patient with a severe NSAID hypersensitivity |
| 2026-09-26 | D07 | ENT follow-up **moved** from 3 Dec to 17 Dec                                                 |

There are three deliberate conflicts. D03 contradicts `current_medication` in the JSON, D07 contradicts D02, and D05 contradicts the allergy list. Real records contain conflicts like these all the time, and they're the cases a retrieval-only system gets wrong.

## Edge cases covered

| Case                                         | Where                   | What breaks without a safeguard                                                 |
| -------------------------------------------- | ----------------------- | ------------------------------------------------------------------------------- |
| Newer source supersedes older                | D03 vs JSON, D07 vs D02 | Assistant says "you're on mepolizumab" or gives the cancelled date              |
| Genuine but dangerous prescription           | D05                     | Assistant confirms the painkiller the patient was handed                        |
| Tables, units, `<` / `>` symbols             | D06, D04, D03           | "28" without "nmol/L" and its range means nothing                               |
| Repeated header/footer, page break           | D02                     | Boilerplate chunks crowd the top-k, and the plan is split away from its context |
| Non-English document                         | D08, Q11                | An English query misses the passage, or the reply switches language             |
| Image-only scan                              | D09                     | Empty chunk indexed, or the model claims to have read it                        |
| Namesake: same name, different DOB           | D10                     | Another person's pacemaker and warfarin join this record                        |
| Hidden prompt injection                      | D11                     | Instruction text reaches the model as a "record passage"                        |
| Non-medical document with the patient's name | D12                     | An identity-only gate lets it through; insurance premiums get "cited"           |
| Mixed relevance within one file              | D13                     | "What supplements do I take?" answered from an advert                           |
| Byte-identical duplicate                     | D14                     | Two copies of every chunk; top-5 halves its diversity                           |
| Encrypted / truncated file                   | D15, D16                | Whole batch crashes on one bad upload                                           |
| Cross-patient leakage                        | Ferrante vs Smacchia    | Penicillin anaphylaxis reported for the wrong patient                           |
| Same question, different answer              | Q28 vs the seeded demo  | Ibuprofen is dangerous for both, for different reasons                          |
| Explicit "no known allergies"                | Okoro                   | Treated the same as "nothing found"                                             |
| Stale "current" medication                   | Okoro folic acid        | Reported as current when its own dose says it ended at 12 weeks                 |
| Empty section                                | Okoro `pathologies: []` | Pregnancy reported as a condition, or an invented diagnosis                     |
| Leap-day DOB, hyphenated name                | Okoro                   | Date parsing and identity matching                                              |
| Pregnancy red flag                           | Q29                     | Headache and blurred vision triaged S3 instead of S1                            |

## Ingest pipeline for PDFs

[`rag_pipeline/pdf.py`](../rag_pipeline/pdf.py) (`aindex_pdfs`) runs every PDF in `dataset/documents/` through four checks, from `langchain_agent/rag.py`. A refused file is printed with its reason and contributes no chunks, and one bad file never stops the batch.

| #   | Check          | Rule                                                             | Stops                                    |
| --- | -------------- | ---------------------------------------------------------------- | ---------------------------------------- |
| 1   | Readable       | `pdfplumber` can open and read it                                | D15 encrypted, D16 truncated             |
| 2   | Has text       | Some text extracted (no OCR)                                     | D09 scan                                 |
| 3   | No hidden text | No character under 3 pt, or white                                | D11 injection                            |
| 4   | This patient's | The record's DOB is in the text, as `07/06/1980` or `1980-06-07` | D10 namesake, D11 leaflet, D12 insurance |

Check 4 also keeps unrelated files out: a non-medical document almost never carries the patient's date of birth.

Pages are loaded with LangChain's `PDFPlumberLoader` and split with `RecursiveCharacterTextSplitter` (1,000 characters, 100 overlap), so most pages are one chunk (D03 is two). Every chunk is `kind: document`. Its text is the identity line from `chunks.py`, then `Document <filename>, page <n>.`, then the split's text. The id is `{patient_id}:pdf:{sha256(file)[:12]}:p{n}:{start_index}`, so a copy under another name (D14) gets the same ids and is embedded once. Chunks are embedded and written through the shared store in `rag_pipeline/vector_store.py`, so they use the same model as search.

Deliberately left out, each with the eval question that shows when it's needed:

| Not done                             | Consequence                                                       | Revisit when                           |
| ------------------------------------ | ----------------------------------------------------------------- | -------------------------------------- |
| Per-page relevance                   | D13's advert page is indexed                                      | Q17 mentions collagen                  |
| Superseded marking                   | The model reads "discontinued" / "cancelled" and the dates itself | Q02 or Q04 gives the old answer        |
| Drug-vs-allergy alert                | Relies on the prompt's allergy cross-check                        | Q05 misses the NSAID. Add this first   |
| OCR, header stripping, date metadata | Not needed at this size                                           | Scans arrive, or footers get retrieved |

## Query-time safeguards against unrelated content

Ingest keeps unrelated documents out. These keep unrelated _questions_ and weak matches from turning into confident answers:

- **Distance threshold.** `search_record` returns the nearest passages however far away they are. Drop passages above a cosine distance cutoff, calibrated on the eval set. Record the distances for Q16, Q20 and Q25, which should match nothing, and for Q01–Q10, which should match. Set the cutoff between the two groups. The prompt already says "nearest isn't relevant", and the threshold enforces it.
- **Off-topic and third-party questions** (Q24–Q26) are the prompt's job. The eval checks that no search runs for Q25.
- **Retrieval budget.** The known gap (the unbounded search loop) gets worse as the corpus grows. Put the tool budget in place before relying on this dataset.
- **k and listing questions.** `n_results=5` can't answer Q21 ("every appointment") once letters mentioning dates compete with the appointment chunks. Options: a `kind` filter as a second tool argument (safe, because the patient id stays in the context), or a larger k for listing intents.
- **Active over superseded.** Rank `status: active` first, or filter superseded chunks out unless the question is about history.

## Using the extra patients

`agent/patient.py` derives the record id as `pat_{users.id}`. Retrieval-isolation tests only need the chunks, so ingest the records with those ids. To _chat_ as Ferrante or Okoro end to end, you need a `users` row whose id is the uuid after `pat_`. `chunks.py` handles both files as they are, and Okoro's empty `pathologies` yields no chunks, as intended.

## Evaluation

`eval/questions.jsonl` is scored by the eval pipeline in `eval/`. The root README's [Evaluation](../../README.md#evaluation) section explains how it works, how to run it, the rubric, and the latest results. Several questions (Q02, Q07, Q13–Q17) have a different correct answer before and after ingest, so running it at both stages tests each ingest check.
