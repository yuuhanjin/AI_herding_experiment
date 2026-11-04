# Xinyue — Order conversion: Improvement 1–4

Research question: how agent decisions become proposed, accepted, rejected, and filled orders.

This folder stores notebooks and uploaded run reports on the personal `xinyue` branch. It does not apply the notebooks' simulator changes directly to the repository-level `src/` tree.

The notebooks use the team's pinned Yuhan snapshot `074faff3c8f6255c917d2a2593a5b476c947ca84`, with separate working copies for the order-size cap and lifecycle logging. Creating this personal branch from `main` does not change that experimental source version.

## Included files and evidence scope

| Step | Notebook | Uploaded run report | Scope of included evidence |
|---|---|---|---|
| 1 | [Order-size cap](step1/AI_Herding_Step1_Order_Size_No_API.ipynb) | [HTML](step1/AI_Herding_Step1_Order_Size_No_API.html) | Offline constructed-order checks: 32 cases per implementation and 3 existing matching regressions; zero model calls. |
| 2 | [Order lifecycle](step2/AI_Herding_Step2_Order_Lifecycle_No_API.ipynb) | [HTML](step2/AI_Herding_Step2_Order_Lifecycle_No_API.html) | 12 manual-response cases. 19 proposals, 16 accepted, 3 rejected; 5 trades / 780 shares; zero model calls. |
| 3 | [Controlled replay](step3/AI_Herding_Step3_Controlled_Replay.ipynb) | [HTML](step3/AI_Herding_Step3_Controlled_Replay.html) | cached_orders: 9 main replays and 9 reproducibility checks of existing decisions; zero new model calls. |
| 4 | [Shared-dividend, 15-round protocol](step4/AI_Herding_Step4_Shared_Dividend_15_Rounds.ipynb) | No user-run HTML included | Code is available. Default prepare_only generates the protocol and scripted plumbing checks. New API experiment results are not included. |

The HTML files are English translations of the uploaded reports. Comments, instructions, output messages, and table labels were translated without rerunning the saved experiments; numerical results and program control flow are preserved. No assistant-side QA runs or mock API responses have been substituted for user experiment results. Download an HTML file and open it in a browser to read the rendered run report.

## Notebook/report version note

The Step 2 notebook includes a later correction to the seventh code cell's single-order trace display: it filters out the counterparty's state rows while retaining whole-trade links. The uploaded HTML preserves the earlier display. Order-processing logic and aggregate counts were unchanged by this display correction. For an exact current notebook/HTML pair, rerun the current notebook locally, export HTML, and replace the report.

The Step 1 notebook retains saved execution outputs. Steps 2–4 are distributed with outputs cleared; the separate uploaded HTML files retain the available user-run outputs.

## Step 3 replay results

Each arm uses three historical target-response profiles, with two market makers per profile. Six is the number of market-maker decisions per arm.

| Historical target-order source | Accepted two-sided decisions | Trades | Executed shares | Oversized orders rejected |
|---|---:|---:|---:|---:|
| Current | 0/6 | 0 | 0 | 0 |
| Earliest public | 1/6 | 1 | 1,000 | 10 |
| Mandatory two-sided | 6/6 | 6 | 6,000 | 0 |

All seven trades used market-maker bids. This is a comparison of given historical target orders under fixed counterparty orders, initial state, processing priority, and the enforced 1,000-share cap. It is not a fresh prompt-to-model response experiment and should not be equated directly with the original uncontrolled probes.

## Raw result files

The `results/README.md` in each step explains what to add from the local execution directories. Original CSV files, patches, linked event logs, and generated result archives remain on the user's computer and are not included in this starter package.

For the uploaded Step 2 report, the corresponding archive is `run_20261104_172502_b2a017_Step2_Results.zip`. For the uploaded Step 3 report it is `session_20261104_181135_625d23_Step3_Results.zip`. Add newer files under their own run/session names instead of relabeling them as these runs.

## Running the notebooks

Run Steps 1, 2, 3, and 4 in order in a local Python 3.11+ Jupyter environment. Keep the generated `AI_Herding_Step1_Work` and `AI_Herding_Step2_Work` directories. Set the path override in a later notebook if it cannot locate them.

Step 3 defaults to `cached_orders` (zero new model calls); `new_mm_api` can request 18 new target-maker responses in a fresh complete plan. Step 4 defaults to `prepare_only` (zero model calls); the default full `api_experiment` plan is 3 arms × 3 seeds × 15 rounds × 8 agents = 1,080 model requests before cache reuse or manual reruns. Supplying these notebooks does not establish model/endpoint availability or a completed paid run.

## Language and rerunning

All notebooks, saved HTML reports, and Markdown instructions in this package are in English. Runtime messages and table labels are also translated so that subsequent local runs display English output. Models, prompt-condition content, numerical parameters, IDs, and data-schema keys are retained.

For a separate rerun of the translated notebooks, use a fresh working directory and run Steps 1–4 in order. Existing generated files from the earlier localized package may differ in descriptive strings; the notebooks deliberately stop instead of overwriting an unrecognized existing copy. Keep the old runs as records. No model API was called to translate this package.
