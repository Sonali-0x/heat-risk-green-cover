# Urban heat and green-cover action summary

**Nagpur** · 2026-03-01 to 2026-05-31 · 100 m grid

## Analysis overview

- Cells processed: 46,018
- Priority-eligible cells: 45,531
- Cells in the highest-priority 10%: 4,554

## Recommended actions by cell

- Check site: bare land: 29
- Cool roof / shade: 20,618
- Plant trees: 24,222
- Protect existing green: 735
- Unavailable: 414

## Highest-priority cells (up to five)

| Cell | Priority | Action |
|---|---:|---|
| cell_e5629288cafa33c3 | 0.701 | Cool roof / shade |
| cell_1e4505098e35a968 | 0.696 | Cool roof / shade |
| cell_dd538d6619ac653e | 0.679 | Cool roof / shade |
| cell_c1e68a583b7271a3 | 0.679 | Cool roof / shade |
| cell_04406caafcf615ce | 0.678 | Cool roof / shade |

## NDVI/LST association

- Pearson correlation: -0.435
- Associated LST change per +0.1 NDVI: -1.573 °C

> **This is an observational correlation, not proof of causation and not a guaranteed cooling effect of planting or another intervention.**

## Method and assumptions

- Exposure = 0.5 × normalized LST + 0.5 × (1 − normalized NDVI). Priority = exposure × (0.5 + 0.5 × normalized population).
- Normalization uses complete, non-water, non-bare cells eligible for ranking. Bare-land cells are flagged and excluded from the ranked list.

## Data sources

- Landsat 8/9 Collection 2 Level 2: NDVI and land-surface temperature.
- Google Dynamic World: tree, built-up, and bare-land probabilities.
- WorldPop: modelled population estimates (reference year 2020).
- Source-specific licensing and attribution must be verified before publication.

## Limitations

- Land-surface temperature (LST) is not air temperature.
- Grid cells are neighborhood-scale, not street- or building-level.
- WorldPop values are modelled population estimates.
- A high score does not establish land ownership, availability, or site suitability. Field verification is required.

*Generated deterministically from scored cells; no AI service was used.*
