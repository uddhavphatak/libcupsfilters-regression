# libcupsfilters-regression

Differential regression testing for [libcupsfilters](https://github.com/OpenPrinting/libcupsfilters).

libcupsfilters 2.1.x used QPDF (C++) for PDF handling; current master uses
[PDFio](https://github.com/michaelrsweet/pdfio) (C). This repository builds a
**baseline** (latest 2.1.x release) and a **candidate** (master, or any branch)
side by side, runs both through the same inputs and print options, and reports
every difference in exit status, document structure and rendered output.

```
corpus/ ──> cases/gen-cases.py ──> cases.tsv
                                      │
      ci/build.py ─> prefix/baseline ─┼─> runner/run.py ─> results/baseline  ─┐
      ci/build.py ─> prefix/candidate ┴─> runner/run.py ─> results/candidate ─┴─> compare/compare.py ─> report/
```

## Layout

| Path | Purpose |
|---|---|
| `ci/build.py` | Build one libcupsfilters ref into a self-contained prefix (library, data files, PDFio for the candidate) |
| `harness/` | Small C program that runs one filter job through the public libcupsfilters API against a fixed emulated printer |
| `corpus/` | Test inputs; the top-level folder decides the input type (`pdf/`, `text/`, `image/`, `pwg/`, `urf/`, `pclm/`, `banner/`) |
| `cases/gen-cases.py` | Builds `cases/cases.tsv`: every input × the option sets for its filter group |
| `runner/run.py` | Runs all cases against one build in parallel and writes outputs, logs and `results.json` |
| `compare/compare.py` | Compares two result directories and writes `report.html`, `summary.json`, `summary.md` |
| `compare/raster.py` | Reader for PWG raster, CUPS raster and Apple raster (URF) |
| `compare/third_party/image-eval` | [OpenPrinting-Image-Evaluation](https://github.com/Sanskary2303/OpenPrinting-Image-Evaluation) (submodule), used for detailed image comparison |
| `known-diffs.txt` | Accepted differences |
| `.github/workflows/compare.yml` | CI workflow |

## Requirements

Ubuntu 24.04 or newer is what CI uses. To build both sides and run the
comparison locally:

```bash
python3 ci/build.py --deps-only          # apt packages (uses sudo)
sudo apt install python3-venv
```

## Running locally

All commands are run from the repository root.

```bash
# One-time setup
git submodule update --init
python3 -m venv .venv
source .venv/bin/activate
pip install -r compare/requirements.txt

# 1. Build both sides
python ci/build.py --ref 2.1.1 --side baseline --prefix prefix/baseline
python ci/build.py --ref master --side candidate --prefix prefix/candidate
#    or a local checkout / branch:
#    python ci/build.py --repo ../libcupsfilters --ref HEAD --side candidate --prefix prefix/candidate

# 2. Build the harness for each side
make -C harness PREFIX=$PWD/prefix/baseline  SIDE=baseline
make -C harness PREFIX=$PWD/prefix/candidate SIDE=candidate

# 3. Generate cases and run them on both sides
python cases/gen-cases.py
python runner/run.py --prefix prefix/baseline  --harness harness/harness-baseline  --out results/baseline
python runner/run.py --prefix prefix/candidate --harness harness/harness-candidate --out results/candidate

# 4. Compare
python compare/compare.py --baseline results/baseline --candidate results/candidate --out report
xdg-open report/report.html
```

Useful runner options (use the same ones for both sides):

- `--group pdftopdf` — only one filter group (`pdftopdf`, `pdftoraster`, `pwg-pclm`, `pclmtoraster`, `text-banner-image`)
- `--filter 'test_file_4pg'` — only case ids matching a regex
- `--jobs N`, `--timeout SECONDS`

Before trusting a report, do a control run: comparing a build with itself must
give only `IDENTICAL` / `VISUAL_EQUAL`.

```bash
python compare/compare.py --baseline results/baseline --candidate results/baseline --out report-control
```

## Adding test inputs

Drop files into the matching `corpus/` folder and rerun `cases/gen-cases.py`;
no registration is needed. Inputs must be freely licensed, since cases may be
promoted to the upstream libcupsfilters test suite. Large files (the PCLm set)
belong in Git LFS:

```bash
git lfs track "corpus/pclm/**"
```

To test more options, add strings to the option lists at the top of
`cases/gen-cases.py`. Each string is one job's options as CUPS would pass them.

## How outputs are compared

Every case gets one class; the worst finding wins:

| Class | Meaning |
|---|---|
| `CRASH` | Candidate died on a signal |
| `TIMEOUT` | Candidate exceeded the time limit |
| `EXIT_DIFF` | Only one side failed |
| `STRUCT_DIFF` | Different page count, page size, boxes, rotation or raster header fields |
| `VISUAL_DIFF` | Rendered pages differ beyond tolerance |
| `BOTH_FAIL` | Both sides failed (reported, not counted as a regression) |
| `VISUAL_EQUAL` | Small pixel differences within tolerance |
| `IDENTICAL` | Pixel-identical rendering |

PDF and PCLm outputs are rendered with `pdftoppm`; raster outputs are decoded
by `compare/raster.py`. Pages are first checked with a fast pixel difference.
Only pages that fail it go through the image-eval `ImageComparator` (SSIM,
skew, colour vs. grayscale) plus a 90°-rotation check, and multi-page outputs
with a different page count get a page-integrity check (missing, duplicated or
reordered pages). Tolerances can be tuned with `--dpi`, `--pixel-level`,
`--pixel-fraction` and `--ssim-threshold`.

### Known differences

Accepted differences go into `known-diffs.txt`, one per line:

```
<case-id regex>  <CLASS or *>  <issue link / reason>
text-banner-image/.*/default\.pdf  VISUAL_DIFF  banners print the current time
```

Known differences still appear in the report, but are not counted as
unexpected. `compare.py --strict` exits non-zero on unexpected differences.

## CI

`.github/workflows/compare.yml` runs on push to `main`, weekly, manually
(**Actions → compare → Run workflow**) and on `repository_dispatch`. Manual
inputs:

| Input | Default |
|---|---|
| `libcupsfilters_repo` | `https://github.com/OpenPrinting/libcupsfilters.git` |
| `baseline_ref` | latest `2.1.x` tag |
| `candidate_ref` | `master` |
| `strict` | `false` (report only) |

Builds are cached per commit. Each filter group runs as its own job and uploads
a `report-<group>` artifact; the summary appears on the run page.

To test a fix before sending it upstream, run the workflow with
`libcupsfilters_repo` set to your fork and `candidate_ref` set to the branch.

From another repository, trigger a run with:

```bash
gh api repos/<owner>/libcupsfilters-regression/dispatches \
  -f event_type=compare \
  -F client_payload[candidate_ref]=my-branch \
  -F client_payload[repo]=https://github.com/<owner>/libcupsfilters.git
```

## Workflow for fixing regressions

1. Open an issue for each unexpected difference, with the case id and report.
2. Add it to `known-diffs.txt` with the issue link.
3. Fix it in libcupsfilters, run this workflow against the fix branch, and link
   the report in the upstream pull request.
4. Add a matching case to `cupsfilters/test-filter-cases.txt` upstream.
5. Remove the `known-diffs.txt` entry.

## License

Apache License 2.0, see [LICENSE](LICENSE). The image-eval submodule is
BSD-2-Clause.
