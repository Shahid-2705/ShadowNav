# How SIH Winners Build Their Idea Decks: Research Report

*Generated: 2026-09-06 | Sources: 22 | Confidence: Medium (high on the template and the three inspected decks, medium on judging weights, low on ISRO-specific winner decks, which are not public)*

Companion deliverable: [submission/ShadowNav_SIH2026_Idea.pptx](../submission/ShadowNav_SIH2026_Idea.pptx) and its PDF, built directly on the official `SIH2026-IDEA-Presentation-Format.pptx` template using the findings below. The build is reproducible from [submission/build_deck.py](../submission/build_deck.py).

## Executive Summary

Smart India Hackathon idea decks are not free-form pitches. The organisers ship a fixed six-slide template (Title, Idea Title, Technical Approach, Feasibility and Viability, Impact and Benefits, Research and References) and instruct teams to keep the pointers, avoid paragraphs, and submit as PDF. Every winning deck I could actually inspect keeps that template byte-for-byte and wins inside it: one or two real diagrams per slide, bold-lead bullets, stakeholder-segmented impact, and quantified claims. The best of them add a competitor comparison matrix and prototype screenshots. The common failure modes are also consistent across sources: walls of text, "does everything with AI" kitchen-sink stacks, unedited template artefacts, and impact slides with no numbers.

For ISRO problem statements specifically, no winning deck is public. What is public is the pattern of what ISRO poses (algorithmic, data-driven, evaluated by SAC/URSC scientists) and who won (IIT Guwahati on the 2024 map-matching PS, NIT Durgapur on the 2023 geospatial NLP PS). The inference, marked as inference, is that ISRO evaluators reward measured results on a named dataset, an explicit error budget, and honest limits over breadth of features.

The user's draft seven-slide outline does not fit the template: it has two problem-statement slides and a thank-you slide the template does not allow, and it is missing three mandatory slides (Feasibility, Impact, References). It also carries four technical claims the project has since dropped or banned. Section 6 maps every draft item to its template home and records each correction.

## 1. What the organisers actually require

The 2026 template's own instructions slide (verbatim, slide 7 of `SIH2026-IDEA-Presentation-Format.pptx`, downloaded from sih.gov.in/letters/2026/):

- "Kindly keep the maximum slides limit to six (6). (Including the title slide)"
- "Avoid paragraphs, use points / diagrams / infographics / pictures"
- "Be precise" and "be unique / novel"
- "Use the provided template without changing the pointers"
- "Save and upload as PDF only"
- "Delete this instructions slide before submitting"

The pointers, verbatim, per slide:

| Slide | Title text (do not change) | Body pointers to answer |
|---|---|---|
| 1 | SMART INDIA HACKATHON 2026 / TITLE PAGE | Problem Statement ID, Problem Statement Title, Theme, PS Category (Software/Hardware), Team ID, Team Name |
| 2 | IDEA TITLE (replace with your idea's title) | Proposed Solution (describe your idea/solution/prototype); detailed explanation; how it addresses the problem; innovation and uniqueness |
| 3 | TECHNICAL APPROACH | Technologies to be used (languages, frameworks, hardware); methodology and process for implementation (flow charts / images / working prototype) |
| 4 | FEASIBILITY AND VIABILITY | Analysis of feasibility; potential challenges and risks; strategies for overcoming them |
| 5 | IMPACT AND BENEFITS | Potential impact on the target audience; benefits (social, economic, environmental, etc.) |
| 6 | RESEARCH AND REFERENCES | Details / links of the reference and research work |

Fixed furniture on slides 2 to 6: a team-name oval top-left (0.36 in, 0.28 in), the SIH 2026 logo top-right (10.70 in, 0.00 in), a blue footer bar (RGB 0070C0) at 6.95 in, a footer placeholder reading "@SIH Idea submission- Template", and a slide number. Slide size is 13.33 by 7.50 in. Title font is Times New Roman 36 pt bold; pointer text is Arial 28 pt. The 2025 template is structurally identical, so 2024 and 2025 winner decks are directly comparable to what 2026 asks for.

## 2. What judges score

The SIH portal's FAQ does not publish a rubric (checked: sih.gov.in/faqs). Three secondary guides converge on the same parameter list and give weightings that should be read as reported, not official:

- **Parameters** most often cited: novelty, complexity, clarity, feasibility, practicability, sustainability, scale of impact, user experience, future scope ([lets-code SIH 2025 guide](https://www.lets-code.co.in/blogs/sih-2025-complete-guide-ppt-template/); [Reskilll SIH 2026 template guide](https://reskilll.com/blogs/sih-2026-ppt-template-exact-format-slides-evaluators-score/)).
- **Internal-round weights** reported by one guide: Problem Understanding 25, Innovation 30, Feasibility 25, Presentation 20 ([lets-code](https://www.lets-code.co.in/blogs/sih-2025-complete-guide-ppt-template/)). Unverified by a second source.
- **Reskilll's rubric**: 20 / 25 / 20 / 20 / 15 across problem understanding, innovation, technical feasibility, impact, and presentation, with the explicit advice "Diagrams > text: evaluators scan visually first", at most six bullets per slide, and a 14 pt minimum font ([Reskilll](https://reskilll.com/blogs/sih-2026-ppt-template-exact-format-slides-evaluators-score/)). Unverified by a second source.
- **Common rejection reasons** named by both guides: too much text, a solution that "does everything with AI", weak or unquantified impact analysis, and incomplete submissions (missing PDF, missing pointers).

Inference: even if the exact weights are wrong, innovation and feasibility together carry half or more of the score, and presentation is scored separately. A deck that proves feasibility with measurements is doing double duty.

## 3. Anatomy of three real winning decks (visual audit)

Three decks from a community "SIH Winners Vault" ([Aadiii00/SIH-Winners-PPt-and-Sources](https://github.com/Aadiii00/SIH-Winners-PPt-and-Sources)) were rendered page by page and inspected. Provenance caveat: the repository labels them winners; the official result pages list team names, not decks, so the label cannot be cross-checked. Treat them as strong, representative decks rather than certified grand-finale winners.

### 3.1 GeoGuards, SIH 2025, PS SIH25071 (rockfall prediction for open-pit mines, Disaster Management)

| Slide | What is on it | Visual components |
|---|---|---|
| 1 | Template title page, all six pointers filled | Template brain graphic only |
| 2 | One-sentence proposed solution; three-column layout: "Addressing the Problem" box (2 bullets), annotated open-pit mine cutaway, "Solution overview" as three rounded boxes with one bullet each | 1 picture, 4 callout boxes |
| 3 | Vertical five-step flowchart (Step I to V) with icons, a DATA hub fanning to Low / Medium / High risk, each pointing at a screenshot of the prototype dashboard | 1 flowchart, 3 prototype screenshots |
| 4 | Four rounded boxes with bold lead-ins (Time-feasible, Scalable, Low cost, Modular design); a pie chart of rockfall causes with callouts pairing each cause with a mitigation | 1 chart, 10 callouts |
| 5 | "Impacts" box (5 bullets); Social / Economic / Environmental tiles; two 3-D geological model renders; a six-panel evolution figure | 3 pictures, 4 tiles |
| 6 | Text only: three research bullets, one link, two reference lines | none |

Strengths: every content slide has a real picture or chart, bullets are short phrases with bold lead-ins, the prototype is shown as screenshots rather than described, and the feasibility slide pairs each risk with a strategy visually. Weaknesses: the slide-2 heading was left as the literal "IDEA TITLE", the references slide is thin, and "Technologies" on slide 3 is a label with almost nothing under it.

### 3.2 TechPioneers, SIH 2025, same PS ("RockVision AI")

| Slide | What is on it | Visual components |
|---|---|---|
| 2 | Six bold-lead bullets (platform, real-time monitoring, historical data, AI chat, pre-project safety analysis, blast planning, alerts) plus a system architecture diagram | 1 architecture diagram |
| 3 | Technology stack in five categories (Frontend, Backend, AI/ML, API services, Cloud) and a wall of roughly twenty vendor logos | logo wall |
| 4 | Dense two-column numbered list: Feasibility (technical / economic / operational), Viability, Challenges, Use cases, Business potential, Solutions; a "supporting facts" box | icons, 1 box; body text well under 14 pt |
| 5 | Benefits tree (Social / Technological / Economic / Environmental) and impact by stakeholder (Mining executives, Miners and engineers, Regulators, Local communities) with quantified claims ("70 to 90 % reduction", "15 to 60 minutes advance notice", "$2 to 5 million annually") | 1 tree diagram |
| 6 | Reference links, plus a **feature comparison matrix** against four named competitors with tick / cross cells | 1 table |

Strengths: stakeholder-segmented impact, quantified benefit claims, and the comparison matrix, which is the single most persuasive element across all three decks. Weaknesses: the stack is the "does everything" anti-pattern both guides warn about (React, Next.js, Kubernetes, AWS, OpenAI API, Twilio for a rockfall predictor), the feasibility slide is a text wall in small type, and the impact numbers carry no source.

### 3.3 Innovators, SIH 2024, PS 1605 (women safety analytics)

| Slide | What is on it | Visual components |
|---|---|---|
| 2 | An underlined paragraph (against the template's own advice), then three coloured tiles labelled with the template pointers ("#DETAILED PROBLEM PROPOSED SOLUTION", "#HOW IT ADDRESSES PROBLEM", "#INNOVATION AND UNIQUENESS"), then three stock images | 3 tiles, 3 stock pictures |
| 3 | Three tiles (Programming language, Framework and Library, Hardware) and a hand-drawn-style app flowchart | 3 tiles, 1 flowchart |
| 4 | Three stacked colour-coded rows (Feasibility / Challenges and Risks / Strategies) with generic bullets ("Technical feasibility", "Financial feasibility") and an illustration | 3 rows, 1 illustration |
| 5 | Three audience columns (For women / For law enforcement / For urban communities), a chevron list of Social / Economic / Environmental benefits, an app logo | columns, chevrons |
| 6 | Concentric-circle graphic labelled "Links for analytics / technology / hardware" with URLs | 1 graphic |

Strengths: it makes the template pointers visually explicit, which helps a judge (or a keyword screen) tick boxes fast. Weaknesses: the footer still reads "@SIH Idea submission- Template", text overflows tiles ("Empowerme nt"), the feasibility content is generic, and stock clip-art carries no information.

### 3.4 Cross-cutting pattern (the checklist the ShadowNav deck follows)

1. **Template fidelity.** All three keep the title-page pointer list, the per-slide title text, the oval, the logo, the footer bar, and slide numbers. Nobody redesigns the frame.
2. **One real visual per content slide, minimum.** A flowchart or architecture diagram on slide 3 is universal. Charts and prototype screenshots appear on slides 2, 4, and 5 in the stronger decks.
3. **Bold lead-in, short phrase.** "Time-feasible: dataset, training, dashboard." Never a sentence longer than a line and a half.
4. **Chunk the pointers into boxes or tiles.** Rounded callouts, coloured tiles, or rows that visibly correspond to the template's pointers.
5. **Stakeholder-split impact** (who benefits, by group) plus the Social / Economic / Environmental triad the pointer literally asks for.
6. **Quantify.** The strongest slides carry numbers; the weakest carry adjectives.
7. **Comparison matrix** against named alternatives on slide 6 (only TechPioneers did this, and it is the most memorable slide of the set).
8. **Show the prototype**, as screenshots, not as a promise.
9. **Mistakes to avoid**, all observed: unedited footer text, "IDEA TITLE" left literal, underlined paragraphs, sub-12 pt body text, text overflowing tiles, logo walls, unsourced impact numbers, thin references.

## 4. What the winners say in their own write-ups

- **Match the problem statement's own words.** A 2022 winner advises reusing the PS keywords in the deck because the first screen may be a keyword or "ATS-like" pass, and warns against over-promising ([Arinjay Pathak, SIH 2022](https://medium.com/@arinjay_11020/how-i-won-smart-india-hackathon-2022-a-step-by-step-guide-by-arinjay-pathak-501529c00abb)). Single source; the ATS claim is unverified.
- **State completion honestly.** The same author reports telling judges the prototype was roughly 30 % complete and that honesty landed better than inflated claims.
- **One presenter, a demo, and a domain expert.** 2024 winners describe rehearsing a single presenter, keeping a demo video ready, and consulting a domain expert before the finale ([Chethan, SIH 2024](https://medium.com/@acchethan15/how-we-won-smart-india-hackathon-2024-a-story-of-teamwork-innovation-afbe74e8e20c); [BlazeBrains, SIH 2024](https://how-we-won-sih-24-and-survived-it.hashnode.dev/everything-about-winning-sih-2024)).
- **Quantified results and a three-part demo.** The MathWorks-sponsored Solar Masters (SIH 2024) built the pitch around a measured "20 % higher efficiency" figure and a demo split into simulation, hardware, and dashboard ([MathWorks student lounge](https://blogs.mathworks.com/student-lounge/2025/06/13/innovation-meets-excellence-solar-masters-winning-journey-at-smart-india-hackathon-2024/)).
- **Structure.** The community vault's README recommends a ten-beat narrative (title, problem, solution, how it works, architecture, stack, innovation, feasibility, impact, future scope) and the slogan "Simple + Practical + Innovative + Impactful" ([Aadiii00 README](https://github.com/Aadiii00/SIH-Winners-PPt-and-Sources)). In a six-slide template, beats 2 to 4 collapse into slide 2 and beats 5 and 6 into slide 3.

## 5. ISRO and Department of Space specifics

**What ISRO poses.** ISRO's SIH problem statements are consistently algorithmic and data-driven rather than product-shaped. SAC posted SIH1732 to SIH1741 in 2024, including SIH1740 "Development of map-matching algorithm using AI-ML techniques to distinguish vehicular movement on highway and service road" ([VEDAS / SAC SIH 2024 page](https://vedas.sac.gov.in/en/sih2024.html)). For 2026 ISRO posted SIH26168 (this project, theme Smart Vehicles) and SIH26169 to SIH26173 under Smart Automation ([SIH 2026 listing, Smart Vehicles](https://sih2026.vuce.in/en/themes/smart-vehicles); [Smart Automation](https://sih2026.vuce.in/en/themes/smart-automation)). Note that a widely copied GitHub mirror lists SIH26168 under "Miscellaneous"; the official listing says Smart Vehicles, which is what the deck uses.

**Who won ISRO problem statements.**

| Year | PS | Team | College | Result |
|---|---|---|---|---|
| 2024 | SIH1740 (map-matching, highway vs service road) | Barely Made It | IIT Guwahati | Winner |
| 2024 | SIH1736 | Cloudweave | MIT World Peace University | First runner-up |
| 2024 | SIH1738 | DevDotCom | JIS College of Engineering | Second runner-up |
| 2024 | SIH1732, SIH1733, SIH1739 | Chandrakriti, Sarva-Conquerors, BlueSentinel | various | Consolation |
| 2023 | SIH1517 (place-name identification from natural language) | hereWeGoAgain | NIT Durgapur | Winner |
| 2023 | SIH1524 | GreyMatter | NIET | First runner-up |
| 2023 | SIH1525 | Bright | PICT Pune | Second runner-up |

Sources: [SIH 2024 grand finale results](https://www.sih.gov.in/sih2024/sih2024-grand-finale-result); [SIH 2023 grand finale results](https://www.sih.gov.in/sih2023-grand-finale-result). The 2025 results page could not be fetched; a college-level winners list ([DJSCE](https://www.djsce.ac.in/docs/SIH%20GRAND%20FINALE%202025.pdf)) shows no ISRO entry.

**What is not available.** No ISRO-PS winning deck is public. The result pages carry team and college only. Searches for the IIT Guwahati SIH1740 team's solution returned only event coverage ([PIB](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2083688)). This is the main gap in the research.

**Inference for SIH26168** (labelled as inference): the closest precedent, SIH1740, is a vehicle-navigation algorithm PS from the same SAC group, won by a team from a research institute. ISRO's evaluators are domain scientists; the things that distinguish a deck for them are a named benchmark, a stated error budget with horizon, a physics-consistent method, and candour about what does not work yet. Feature breadth and vendor logos are actively counter-productive. The project's own rule set already bans "guaranteed" confidence, novelty claims for the blend FSM, and jamming-detection claims that have not been bench-tested; the deck keeps all of those bans.

## 6. Mapping the draft outline onto the template

| Draft slide | Content | Where it lands in the six-slide deck | Correction applied |
|---|---|---|---|
| 1 Title | Project, team, illustration | Slide 1, all six pointers, no extra illustration (none of the winners add one) | Theme set to Smart Vehicles, category Software, team ID left for the portal |
| 2 Problem statement and motivation | Tunnels, drift, need | Folded into slide 2 "How it addresses the problem" and slide 5 audience tiles; the template has no problem slide and the six-slide limit is enforced | None |
| 3 Real-world alignment and gap | Millions of drivers, opportunity | Slide 5 target-audience tiles and "Numbers that matter" | Two-wheeler share and NavIC status used instead of generic "millions" |
| 4 Proposed solution | GNSS health monitor, adaptive InEKF, motion awareness, health score | Slide 2, three pointer blocks | 21-state SE2(3) InEKF replaced by the 5-state kinematic EKF actually shipped (the 21-state filter diverged on 10 Hz data); "blockage vs interference" classification dropped (AGC not bench-tested); "health score" replaced by the calibrated 90 % radius, never "guaranteed" |
| 5 Technical stack and flow | Android + native C++, optional magnetometer, Eigen/Ceres, ZUPT, adaptive Q/R | Slide 3 technologies list | Magnetometer removed (PS scope is accelerometer + gyroscope); native C++ replaced by the pure-Kotlin core that is parity-tested against Python; adaptive Q/R not claimed because it was not built; ZUPT is the stationary detector that was built |
| 6 System architecture diagram | Block diagram, on-device emphasis | Slide 3 architecture figure plus blackout-timeline strip | Drawn from the shipped pipeline, not the plan |
| 7 Thank you | Contacts, references | Dropped; the template ends with References (slide 6) | References made substantive: six papers, the dataset, the Android API, and a comparison matrix |
| (missing) | Feasibility and viability | Slide 4: drift chart from committed results, risks, strategies | Mandatory pointer, was absent from the draft |
| (missing) | Impact and benefits | Slide 5 | Mandatory pointer, was absent from the draft |

## 7. The ShadowNav deck, slide by slide

Everything quoted is from committed evaluation JSON (`eval/results/*.json`) or measured on the device; the drift chart and the trajectory figure are generated from those files and reproduce from the committed seed.

1. **Title.** Pointers filled verbatim. Team ID placeholder.
2. **ShadowNav: Dead Reckoning Through GPS Blackouts.** Left: the three pointer blocks in bold-lead bullets (proposed solution, how it addresses the problem, innovation). Right: a real IO-VNBD drive (S-Vw6) with GPS cut for 60 s, showing hidden ground-truth fixes, the ShadowNav track, the naive strapdown running off-chart, and the calibrated 90 % region. Caption states the median across all 183 sixty-second outages so one good example is not mistaken for the average.
3. **Technical Approach.** Left: technologies and a six-step methodology. Right: architecture block diagram (sensors, self-calibration, GNSS health gate, EKF core, calibrated output, app) and the AIDED / DEGRADED / DEAD RECKONING / REACQUIRING timeline.
4. **Feasibility and Viability.** Left: the drift chart, naive strapdown versus ShadowNav at 10 to 180 s over 991 outages (1.7× to 43×), with a three-line feasibility evidence block. Right: five risks and five matching strategies in colour-paired tiles, including the honest one: drift is still 77 to 108 % of distance at long horizons.
5. **Impact and Benefits.** Four audience tiles (drivers and riders, fleets, emergency services, ISRO and NavIC), four benefit tiles (social, economic, environmental, strategic), the coverage chart (17 % to 97 %), the live-app screenshot, and a "numbers that matter" box.
6. **Research and References.** Eight references with identifiers, and a six-row comparison matrix against map-app tunnel modes, industrial GNSS-INS units, and typical SIH repositories, footnoted to the research dossier and marked for re-verification before the finale.

Design choices lifted from the winners: template kept intact, footer edited (unlike Innovators), idea title replaces "IDEA TITLE" (unlike GeoGuards), bold-lead bullets, tiles per pointer, stakeholder split, quantified claims, comparison matrix, prototype screenshot. Body text runs 10.5 to 13 pt inside tiles and dense blocks and 13 to 14.5 pt elsewhere, comparable to the inspected winners but below Reskilll's 14 pt advice on four slides; the trade was made to keep every pointer answered on its own slide.

## Key Takeaways

- Build on the official template and change nothing but the body; every inspected winner did, and the instructions say so.
- Put a real figure on every content slide: the architecture diagram is table stakes, a measured chart and a prototype screenshot are what separate strong decks.
- Quantify feasibility with your own measurements and state limits plainly; for an ISRO evaluator this beats feature breadth.
- Add a comparison matrix on the references slide; it was the most persuasive element in the sample and almost nobody does it.
- Before submitting: replace the team name and team ID, add the repository link on slide 6, re-verify the comparison matrix cells, and if possible replace the idle app screenshot with one captured in the app's simulated-blackout mode.

## Gaps and unverified items

- No ISRO-PS winning deck was found; section 5's guidance is inference from PS style and winner profile.
- Judging weights come from coaching blogs, not from the organisers.
- The three decks' "winner" status rests on one community repository's labelling.
- The 2025 official results page was not reachable; ISRO 2025 winners are unknown to this report.
- Whether SIH uses any automated keyword screening is a single-source claim.

## Sources

1. [SIH 2026 idea presentation template](https://sih.gov.in/letters/2026/) (`SIH2026-IDEA-Presentation-Format.pptx`), the six-slide format and the instructions slide quoted in section 1.
2. [Reskilll: SIH 2026 PPT template, exact format, how evaluators score](https://reskilll.com/blogs/sih-2026-ppt-template-exact-format-slides-evaluators-score/), rubric weights, "diagrams > text", 14 pt and six-bullet advice.
3. [lets-code: SIH 2025 complete guide and PPT template](https://www.lets-code.co.in/blogs/sih-2025-complete-guide-ppt-template/), parameter list, internal-round weights, rejection reasons.
4. [Arinjay Pathak: How I won SIH 2022](https://medium.com/@arinjay_11020/how-i-won-smart-india-hackathon-2022-a-step-by-step-guide-by-arinjay-pathak-501529c00abb), PS keywords, honesty about completion, demo video.
5. [Chethan: How we won SIH 2024](https://medium.com/@acchethan15/how-we-won-smart-india-hackathon-2024-a-story-of-teamwork-innovation-afbe74e8e20c), single presenter, domain expert, rehearsal.
6. [BlazeBrains: Everything about winning SIH 2024](https://how-we-won-sih-24-and-survived-it.hashnode.dev/everything-about-winning-sih-2024), no over-promising, clean architecture diagrams.
7. [MathWorks: Solar Masters' winning journey at SIH 2024](https://blogs.mathworks.com/student-lounge/2025/06/13/innovation-meets-excellence-solar-masters-winning-journey-at-smart-india-hackathon-2024/), quantified result and three-part demo.
8. [Aadiii00/SIH-Winners-PPt-and-Sources](https://github.com/Aadiii00/SIH-Winners-PPt-and-Sources), the three inspected decks (GeoGuards 2025, TechPioneers 2025, Innovators 2024) and the README's ten-beat structure.
9. [SIH 2024 grand finale results](https://www.sih.gov.in/sih2024/sih2024-grand-finale-result), ISRO winners table.
10. [SIH 2023 grand finale results](https://www.sih.gov.in/sih2023-grand-finale-result), ISRO winners table.
11. [VEDAS / SAC: SIH 2024 problem statements](https://vedas.sac.gov.in/en/sih2024.html), SIH1732 to SIH1741 and the SIH1740 map-matching title.
12. [DJSCE: SIH grand finale 2025 winners](https://www.djsce.ac.in/docs/SIH%20GRAND%20FINALE%202025.pdf), one college's 2025 winners, no ISRO entry.
13. [PIB: IIT Guwahati hosts grand finale of SIH 2024](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2083688), event coverage only.
14. [SIH 2026 problem statements, Smart Vehicles theme](https://sih2026.vuce.in/en/themes/smart-vehicles), SIH26168 row.
15. [SIH 2026 problem statements, Smart Automation theme](https://sih2026.vuce.in/en/themes/smart-automation), SIH26169 to SIH26173.
16. [NoBugNinja: SIH 2026 problem statements mirror](https://github.com/NoBugNinja/Smart-India-Hackathon-SIH-2026-Problem-Statements), lists SIH26168 under Miscellaneous (disagrees with the official listing).
17. [SIH FAQ](https://www.sih.gov.in/faqs), checked, no published rubric.
18. [Sahil Ali: SIH 2023 ISRO problem statements](https://sahilali.medium.com/sih-2023-isro-introduces-new-problem-statements-smart-india-hackathon-2023-isro-eef9885ef1e6), returned 403; PS titles taken from search excerpts only.
19. [Project research dossier](SIH26168-dead-reckoning-research.md), sections 10 and 13, basis of the comparison matrix.
20. [Project external-review response](SIH26168-external-review-response.md), banned claims and the low-end Android target.
21. [Project plan](../PLAN.md), pipeline and component table used for the architecture figure.
22. Committed evaluation results, `eval/results/kinematic.json`, `baseline_naive.json`, `conformal_calibration.json`, `inference_latency.json`, all numbers in the deck.

## Methodology

The firecrawl and exa MCP tools the deep-research skill prefers were not available in this session, so searching used the built-in web search and page fetch (14 searches, 20 page fetches). Medium pages returned 403 and were read through a text proxy where possible. Three winner decks were downloaded as PDFs and rendered to images for visual inspection because they contained no extractable text. Two official result pages were parsed for ISRO rows. The 2026 and 2025 templates were opened programmatically to map every shape, font, and position. Sub-questions investigated: what the organisers require; what judges score; how winning decks are structured and drawn; what winners themselves advise; what distinguishes ISRO problem statements and their winners; how the draft outline maps to the template.
