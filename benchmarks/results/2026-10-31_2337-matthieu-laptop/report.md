# Benchmark · matthieu-laptop · 2026-10-31 23:37

- Machine: Intel Core i5-1335U, 16 GB RAM, integrated graphics only (CPU inference)
- CPU: 13th Gen Intel(R) Core(TM) i5-1335U · RAM: 15.3 GiB · Linux 6.8.0-147-generic
- Ollama 0.34.2
- Generation: temperature=0.0, seed=42, num_ctx=4096, num_predict=1024
- Questions: 14 (11 from the use case)

## Speed and memory

| Model | Size | Quant. | Load (s) | First token (s) | Generation (tok/s) | Prompt (tok/s) | Answer time (s) | Memory (GiB) | Of which VRAM (GiB) |
|---|---|---|---|---|---|---|---|---|---|
| llama3.2:3b | 3.2B | Q4_K_M | 2.8 | 1.2 | 11.6 | 201.7 | 33.6 | 2.39 | 0.00 |
| llama3.1:8b | 8.0B | Q4_K_M | 10.6 | 2.9 | 5.3 | 74.6 | 58.6 | 5.19 | 0.00 |
| qwen2.5:7b | 7.6B | Q4_K_M | 10.0 | 2.8 | 5.6 | 73.5 | 69.9 | 4.71 | 0.00 |

## Answer quality

| Model | Use case correct | Generic correct | Final line given | Truncated | Errors | Judge (1-5) |
|---|---|---|---|---|---|---|
| llama3.2:3b | 6/10 | 2/3 | 12/14 | 1 | 0 | - |
| llama3.1:8b | 7/10 | 2/3 | 13/14 | 0 | 0 | - |
| qwen2.5:7b | 10/10 | 1/3 | 13/14 | 0 | 0 | - |

## Per question

✓ correct · ✗ wrong · - nothing to check (judge only) · ! error · (t) truncated

| Question | Topic | llama3.2:3b | llama3.1:8b | qwen2.5:7b |
|---|---|---|---|---|
| second-degre | Second degré | ✓ | ✓ | ✓ |
| derivee-polynome | Dérivation | ✗ | ✓ | ✓ |
| derivee-exponentielle | Fonction exponentielle | ✓ | ✓ | ✓ |
| limite-quotient | Limites | ✓ | ✗ | ✓ |
| suite-arithmetique | Suites | ✗ | ✗ | ✓ |
| recurrence | Raisonnement par récurrence | - (t) | - | - |
| integrale | Intégration | ✓ | ✓ | ✓ |
| logarithme-domaine | Fonction logarithme | ✗ | ✓ | ✓ |
| loi-binomiale | Probabilités | ✓ | ✓ | ✓ |
| probabilites-totales | Probabilités conditionnelles | ✗ | ✗ | ✓ |
| vecteurs-orthogonaux | Géométrie dans l'espace | ✓ | ✓ | ✓ |
| capitale | Culture générale | ✓ | ✓ | ✓ |
| duree-trajet | Raisonnement | ✓ | ✓ | ✗ |
| lettres | Comptage | ✗ | ✗ | ✗ |

Every answer, final line and judge reason is in `results.json`.
