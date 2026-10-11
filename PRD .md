# PRD: Green Cover & Urban Heat Priority Map

**Event:** VNIT Internal Selection Hackathon, Hack for a Social Cause (October 2026)
**Theme:** Theme 7 (AI, GIS & Emerging Technologies), also supports Theme 6 (Environment & Sustainability)
**Status:** Draft for Round 1 PPT and the October 11 one-day build
**Pilot city:** Nagpur (can be changed)

---

## 1. Problem

Indian cities are getting hotter, and tree cover is shrinking. Heat hits low-income neighbourhoods hardest, because they have fewer trees, more tin or concrete roofs, and little access to cooling. City planners and NGOs often plant trees where land is easy to get, not where heat and need are highest, because they have no simple, ward-level view of where the problem is worst.

**Who is affected:** residents of dense, low-green neighbourhoods, especially children, the elderly and outdoor workers.
**Who decides:** municipal planners, ward officers, NGOs and citizen groups running plantation drives.

## 2. Existing situation and gap

- Satellite data (Landsat, Sentinel) is free, but it needs GIS skills and tools that most local planners and NGOs do not have.
- Global heat maps exist, but they are rarely shown at neighbourhood level or turned into a clear "plant here first" list.
- Plantation drives are usually planned by availability of land or by habit, not by data.

**Gap this project fills:** a simple tool that combines greenness and surface heat and turns them into a ranked, easy-to-read priority list for one city.

**Related work (cite these in your PPT, and do not copy from them):**
- *Right Place, Right Tree | Boston*: a decision tool that ranks areas by heat, heat vulnerability and planting feasibility.
- TreeGrid: a tree-planning tool for cities of the Northern Plains of India.
- The Nagpur Climate Resilient City Action Plan and several research papers already map Nagpur's green cover and land surface temperature.
- Open-source Nagpur urban heat projects on GitHub run multi-year Landsat analysis and land-cover scenarios.

**How this project differs:** it is built for non-expert users, weights heat by how many people live in each area, gives one **recommended action per cell** (plant trees, cool roof, protect, or check site), and produces a short plain-language report in Marathi or Hindi.

> Before submitting, search again for similar tools yourself, because projects change often, and update this list.

## 3. Goal and non-goals

**Goal:** In one day, build a working map for one city that shows green cover, surface temperature and a priority score for where new trees help the most, with a short plain-language recommendation.

**Non-goals (for this hackathon):**
- Measuring air temperature (we only measure *surface* temperature).
- Street-level or building-level analysis.
- Confirming exact planting sites. The tool suggests an action per cell, but field verification is still needed.
- Covering more than one city.
- User accounts, a database or public write endpoints. This is by design, to keep the attack surface small (see Section 12).

## 4. Users and use cases

| User | Need | What they do in the tool |
|---|---|---|
| Municipal planner | Decide where to plant first | Opens the map, views the top priority cells, exports the list |
| NGO / plantation group | Pick drive locations with the most impact | Zooms to a neighbourhood and reads its score |
| Citizen or student | Understand heat in their area | Clicks their area and reads the summary |

## 5. Features

### Must have (MVP)
1. **Green layer:** NDVI map of the city from satellite data.
2. **Heat layer:** land surface temperature (LST) map in °C.
3. **Heat exposure score:** hot and not green gives a high score.
4. **Interactive map:** toggle layers, click a cell to see NDVI, LST, population, score and recommended action.
5. **Top 10% list:** the highest-priority cells, with a downloadable CSV.
6. **Security and trust basics:** no secrets in code, validated inputs, HTTPS hosting, a privacy and disclaimer page, and an accessible, mobile-friendly map (see Section 12).

### New features that make this project different (added)
6. **Vulnerability weighting:** the score is weighted by population density (WorldPop), so cells where more people live rank higher. Heat hits crowded, low-green neighbourhoods hardest.
7. **Recommended action per cell:** using land-cover data (Dynamic World), each cell gets one action instead of just a colour:
   - **Plant trees** (open space is likely)
   - **Cool roof / shade structures** (mostly built-up, little space for trees)
   - **Protect existing green** (already well covered)
   - **Check site: bare land** (see feature 8)
8. **Bare-soil filter:** in the dry season, fallow farmland and quarries can read hotter than the city centre. These cells are flagged and kept out of the top list so they do not distort the ranking.
9. **Cooling estimate:** a city-wide figure such as "+0.1 NDVI is associated with about X °C lower surface temperature", shown on the map with a clear note that it is a correlation, not proof.
10. **Plain-language action report:** an AI model turns the top cells' numbers and actions into a short report in English, Hindi or Marathi, for planners and NGOs who do not read maps.

### Nice to have
11. **Year comparison:** green cover change between two summers.
12. **Ward boundaries** instead of a square grid.
13. **Streamlit sliders** to change the score weights live.

## 6. How the score and actions work

```
exposure = 0.5 * normalised(LST) + 0.5 * (1 - normalised(NDVI))
priority = exposure * (0.5 + 0.5 * normalised(population))
```

- Values are scaled from 0 to 1 across the city.
- Water bodies (NDVI below 0) are removed, because they are cool but not green.
- Population weighting means a cell with no people keeps half its exposure score, and the most crowded cell keeps all of it.
- The 50/50 weights and the population factor are starting choices. Show them openly in the pitch.

**Action rules (checked in this order):**

| Condition (average over the cell) | Action |
|---|---|
| Bare-land probability above 0.5 | Check site: bare land |
| Built-up probability above 0.6 | Cool roof / shade |
| Tree probability above 0.4 | Protect existing green |
| Otherwise | Plant trees |

These thresholds are assumptions. Tune them after checking the map against places you know.

## 7. Data sources

| Data | Source | Notes |
|---|---|---|
| Surface temperature and NDVI | Landsat 8/9 Collection 2 Level 2 via Google Earth Engine | Thermal band is 100 m resampled to 30 m |
| Land cover (built-up, bare, trees) | Dynamic World (`GOOGLE/DYNAMICWORLD/V1`) | Probabilities from Sentinel-2, about 10 m; used for the action rules |
| Alternative access | Microsoft Planetary Computer | Use if Earth Engine approval is delayed |
| Population density | WorldPop 100 m | Modelled, so treat as approximate; used for vulnerability weighting |
| City boundary | Draw a box, or use OpenStreetMap boundaries | |

**Season:** March to May (summer, mostly cloud-free).

## 8. Technical approach

- **Processing:** Python, Earth Engine API, geemap, GeoPandas, pandas
- **Map:** Folium (output is a single HTML file that opens in any browser)
- **Optional AI summary:** Anthropic API (or any other LLM)
- **Optional front end:** Streamlit, if time allows. If it is added, every key and AI call stays server-side.
- **Security approach:** static-first. Results are generated offline and published as static files, with no login, database or public write endpoints (see Section 12).

```
Satellite data -> NDVI + LST -> grid cells -> priority score -> map + CSV -> AI summary
```

See `IMPLEMENTATION.md` for the step-by-step build.

## 9. Success criteria for the demo

- The map loads and shows all three layers (NDVI, LST, priority) for the city.
- Known places match common sense: parks and campuses look cooler and greener than dense markets and industrial areas.
- Recommended actions look sensible: a dense market shows "Cool roof / shade", a large park shows "Protect existing green", and bare land is kept out of the top list.
- The cooling estimate is shown with its caveat.
- The top 10% list opens as a CSV.
- Judges can click any cell and understand why it ranked high.
- The prototype runs end-to-end on the day, with a backup of pre-computed results.
- Security checks pass: the secret scan is clean, no keys appear in the HTML, the hosted link uses HTTPS, inputs are validated, and dependencies are audited.
- Quality checks pass: the map works at phone width, Lighthouse accessibility and speed checks are done, contrast is acceptable, and all links work.

## 10. Impact and scalability

- **Impact:** helps direct limited planting budgets to the neighbourhoods with the greatest heat exposure.
- **Scale to other cities:** change only the boundary and the date range.
- **Scale in depth:** add rooftop and land-use data, tree-survival tracking after plantation drives, and heat-health alerts.

## 11. Risks and honest limits

| Risk | Plan |
|---|---|
| Earth Engine approval takes time | Sign up before October 11, and keep Planetary Computer as backup |
| Clouds in the images | Use the March to May median composite |
| Surface temperature is not air temperature | State this clearly in the PPT and demo |
| 30 m resolution cannot show single streets | Present the result as neighbourhood-level |
| High score does not mean land is available | Say that field verification is the next step |
| Dynamic World can misclassify cells, and the action thresholds are assumptions | Check against known places and tune the thresholds |
| WorldPop is modelled, not a census count | Describe it as an estimate of population density |
| Cooling estimate is a correlation, not a guarantee | Show the caveat on the map and in the pitch |
| An API key or credential leaks through the public repository or the HTML | Environment variables, `.gitignore`, secret scan of the full history, and rotate any key that was ever committed |
| AI output is wrong or manipulated | The AI sees only computed numbers, its output is escaped as plain text, and a person reads it before the demo |
| Cost abuse if a live AI endpoint is exposed | Keep AI offline. If it must be live, add a spending limit, rate limiting and server-side validation |
| A vulnerable dependency | Pin versions, install only what is needed, and run `pip-audit` once before release |
| Live data download fails during the demo | Keep pre-computed results saved locally |

## 12. Security, privacy and production readiness

The goal is a prototype that is built carefully, not a quick demo that leaks keys or breaks when someone opens it. No application can be called "unhackable", so we do not claim that. We reduce the attack surface, follow basic security practice, and say clearly what a full audit would add later.

### 12.1 Design principle: static-first, small attack surface

- The map, CSV and report are **generated offline by a script** and published as static files.
- **No user accounts, no login, no database and no public write endpoints.** Nothing can be changed by a visitor.
- **No personal data.** The tool only uses aggregated grid-cell data.
- The AI report is **generated offline** and saved. No AI key is ever sent to the browser.
- If a live feature is added later (for example a Streamlit app), every key and every AI call stays **server-side**.

Fewer moving parts means fewer ways to be attacked.

### 12.2 Security requirements

| ID | Requirement | How we check it | Priority |
|---|---|---|---|
| S1 | **No secrets in code or in the frontend.** API keys and credentials live only in environment variables or local credential files. A `.env.example` with fake values documents what is needed. | Search the built HTML for "key" and "token". Run a secret scanner on the repo and its full history. | Must |
| S2 | **Safe public repository.** The national portal requires a public repo, so no credential files, no keys in git history, and no personal data. Rotate any key that was ever committed. | Secret scan before making the repo public. Review `.gitignore`. | Must |
| S3 | **Least privilege and cost limits.** The AI key has a spending limit. The Earth Engine project has only the access it needs. | Check key limits in the provider dashboard. | Must |
| S4 | **Input validation.** Only allow-listed cities, a bounding box inside India, valid dates and a capped grid size. No free text goes into file paths, queries or shell commands. | Unit test the `validate()` function with bad inputs. | Must |
| S5 | **AI safety.** The AI only sees computed numbers, never user free text. Its output is treated as plain text and escaped before it is placed in HTML. | Try a prompt-injection string in test data and confirm nothing changes. | Must |
| S6 | **Dependency hygiene.** Pin versions, install only what is needed, and run a vulnerability audit once before release. | `pip-audit` on `requirements.txt`. | Must |
| S7 | **HTTPS.** Host on a platform that enforces HTTPS. No mixed content (every script and tile loads over HTTPS). | Open the link, check the padlock, and check the browser console for warnings. | Must (if hosted) |
| S8 | **Safe output.** No user-supplied HTML in map popups, and all values are escaped. | Review popup code. | Should |
| S9 | **Safe logging.** No keys, tokens or full request data in logs or error messages. | Read the logs from a test run. | Should |
| S10 | **If any live endpoint is added:** rate limiting, a cost cap, server-side validation and CORS restricted to our own domain. | Review before deploying. | Only if added |
| S11 | **Security headers** (Content-Security-Policy, X-Content-Type-Options, frame and referrer controls) through the `_headers` file on Netlify or Cloudflare Pages. The Folium map needs `'unsafe-inline'` in the policy, which is a known limitation to tighten later. | Check with securityheaders.com and the browser console. | Should |

### 12.3 Privacy

- We use **aggregated, grid-level data only**. WorldPop is a modelled population estimate, not personal data.
- A short **privacy and disclaimer page** states: what data is used, that no personal data is collected, which data sources are used, and that AI is used to explain results.
- If any personal data is ever collected (for example a feedback form), check the requirements of India's Digital Personal Data Protection Act, 2023, and keep only what is needed. This is not legal advice.

### 12.4 Launch-readiness checklist

This list is based on a common pre-launch checklist for web apps. Some items are security. Many are polish for public websites, so we mark what applies to a hackathon prototype. The script `publish_site.py` (IMPLEMENTATION.md, Section 10.11) generates the landing page, privacy and terms pages, 404 page, favicon, sitemap, robots.txt and security headers file, so most of these items cost only minutes.

| Item | Applies? | Our plan |
|---|---|---|
| Privacy policy | Yes, if hosted | Short plain-language page (see 12.3), generated as `privacy.html` |
| Terms and conditions | Yes, short | A disclaimer: informational use, surface temperature only, not official advice. Generated as `terms.html`. |
| Remove frontend secrets | **Critical** | See S1 and S2 |
| Enforce HTTPS | Yes, if hosted | See S7 |
| Cookie consent banner | Only if we use cookies or tracking | We plan **no tracking cookies**, so no banner is needed. If analytics is added, add a banner or use cookie-free analytics. |
| Meta titles and descriptions | Yes, if hosted | Added to every page by `publish_site.py` |
| Social preview image | Yes | The Open Graph tags are generated. Add `site/og-image.png`, a compressed screenshot of the real map. |
| Favicon | Yes | One small icon, generated as `favicon.svg` |
| Sitemap and robots.txt | Yes, cheap | Generated by `publish_site.py`. Note that robots.txt does not protect anything. |
| Image alt text | Yes | Text alternative for the map: the ranked CSV and a written summary |
| Image compression | Yes | Compress screenshots. Simplify and round the GeoJSON so the map file stays small. |
| Page load speed check | Yes | Run Lighthouse. Keep the cell count reasonable for phones. |
| Colour contrast fixes | Yes | Meet WCAG AA contrast. Use a colour-blind-safe palette. Never rely on colour alone, since the tooltip names the action in text. |
| Mobile responsiveness | Yes | Test at phone width |
| Custom 404 page | Yes, cheap | Generated as `404.html`, with links back to the home page and the map |
| Broken link fixes | Yes | Check all links and source credits before submitting |
| Form validation | Only if there are inputs | The city and date selection is allow-listed (see S4) |
| Spam protection | Only if public forms exist | We have none by design. If a feedback form is added, rate-limit it and add a honeypot or CAPTCHA. |
| Analytics setup | Optional | Not needed for the hackathon. If added, use privacy-friendly analytics. |
| Single clear call to action | Yes | The landing page (`index.html`) has one main button: "Explore the priority map", with "Download ranked list" as the second |

### 12.5 What we will say honestly

- We designed the tool to keep the attack surface small and followed basic security practice.
- We have **not** had an independent security audit. That is a next step before any real city uses it.
- Open data licences (Landsat, Dynamic World, WorldPop) are checked, and each source is credited.

## 13. Open questions

- Which city will you use? (Nagpur is suggested so you can check results against places you know.)
- May teams prepare data before October 11? Ask the organisers.
- Will the demo be hosted online (needs HTTPS, a privacy page and a link check) or run locally?
- Which language should the action report use for the demo: Marathi, Hindi or English?
- Are the action thresholds (bare 0.5, built-up 0.6, trees 0.4) sensible for Nagpur? Tune them on the day.
