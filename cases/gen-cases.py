#!/usr/bin/env python3
"""Generate cases/cases.tsv from the files found under corpus/.

Each top-level corpus folder (pdf/, text/, pwg/, ...) decides the input MIME
type, so new inputs only need to be dropped into the right folder.
"""

import argparse
import csv
import hashlib
import itertools
import random
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
DEFAULT_OUTPUT = ROOT / "cases" / "cases.tsv"

PDF = "application/pdf"
PCLM = "application/PCLm"
PWG = "image/pwg-raster"
URF = "image/urf"
CUPS_RASTER = "application/vnd.cups-raster"
TEXT = "text/plain"
BANNER = "application/vnd.cups-banner"

IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
               ".tif": "image/tiff", ".tiff": "image/tiff"}

OUTPUT_EXT = {PDF: "pdf", PCLM: "pclm", PWG: "pwg", URF: "urf", CUPS_RASTER: "ras", TEXT: "txt"}


# ---------------------------------------------------------------------------
# Option tables.  Each string is one job's options, exactly as CUPS would
# pass them; "" means "no options".
# ---------------------------------------------------------------------------

PDFTOPDF_OPTIONS = [
    "",
    # Layout
    *[f"number-up={n}" for n in (2, 3, 4, 6, 8, 9, 10, 12, 15, 16)],
    *[f"number-up=4 number-up-layout={layout}"
      for layout in ("lrtb", "rltb", "tblr", "btlr", "lrbt", "rlbt", "tbrl", "btrl")],
    *[f"number-up=2 page-border={border}" for border in ("single", "single-thick", "double", "double-thick")],
    # Orientation
    *[f"orientation-requested={o}" for o in (3, 4, 5, 6)],
    "landscape=true",
    "pdfAutoRotate=false",
    "nopdfAutoRotate=true",
    # Page selection and order
    *[f"page-ranges={r}" for r in ("1", "2-3", "1,3", "2-", "1-2,4")],
    "page-set=odd",
    "page-set=even",
    "output-order=reverse",
    "outputorder=reverse",
    # Duplex, booklet, mirror (2.1.x reads "booklet", master reads "imposition-template")
    *[f"sides={s}" for s in ("one-sided", "two-sided-long-edge", "two-sided-short-edge")],
    "sides=two-sided-long-edge even-duplex=true",
    "booklet=on",
    "booklet=on sides=two-sided-short-edge",
    "imposition-template=booklet",
    "mirror=true",
    # Scaling and position
    *[f"print-scaling={p}" for p in ("auto", "auto-fit", "fill", "fit", "none")],
    "fit-to-page=true",
    "fill=true",
    "crop-to-fit=true",
    "nofit-to-page=true",
    *[f"position={p}" for p in ("center", "top", "bottom", "left", "right", "top-left", "bottom-right")],
    "page-left=36 page-right=36 page-top=72 page-bottom=72 fit-to-page=true",
    # Media, labels, copies handling
    *[f"media={m}" for m in ("na_letter_8.5x11in", "na_legal_8.5x14in", "iso_a5_148x210mm", "iso_a3_297x420mm")],
    "page-label=REGRESSION-LABEL",
    "multiple-document-handling=separate-documents-collated-copies",
    "multiple-document-handling=separate-documents-uncollated-copies",
    "collate=true",
    "collate=false",
]

# Options most likely to interact; covered pairwise instead of exhaustively.
PDFTOPDF_PAIRWISE_FACTORS = [
    ["", "number-up=2", "number-up=4", "number-up=6"],
    ["", "orientation-requested=4", "orientation-requested=5", "orientation-requested=6"],
    ["", "print-scaling=fit", "print-scaling=fill", "print-scaling=none"],
    ["", "page-set=odd", "page-set=even"],
    ["", "sides=two-sided-long-edge", "sides=two-sided-short-edge"],
    ["", "mirror=true"],
    ["", "page-border=single"],
    ["", "media=na_letter_8.5x11in"],
    ["", "output-order=reverse"],
]

RASTER_OPTIONS = [
    "",
    "print-color-mode=monochrome",
    "print-color-mode=color",
    "printer-resolution=600dpi",
    "print-quality=3",
    "print-quality=5",
    "sides=two-sided-long-edge",
    "sides=two-sided-short-edge",
    "orientation-requested=4",
    "number-up=2",
    "media=na_letter_8.5x11in",
    "print-scaling=fill",
]

TEXT_OPTIONS = [
    "",
    "prettyprint=true",
    "columns=2",
    "cpi=12 lpi=8",
    "wrap=false",
    "orientation-requested=4",
    "page-left=72 page-right=72 page-top=72 page-bottom=72",
    "media=na_letter_8.5x11in",
]

IMAGE_OPTIONS = [
    "",
    "fit-to-page=true",
    "scaling=50",
    "ppi=150",
    "position=top-left",
    "orientation-requested=4",
    "print-scaling=fill",
    "print-scaling=fit",
    "print-scaling=none",
    "mirror=true",
    "media=na_letter_8.5x11in",
]

RASTER_INPUT_OPTIONS = ["", "print-color-mode=monochrome"]


# ---------------------------------------------------------------------------
# Case model
# ---------------------------------------------------------------------------

@dataclass
class Case:
    id: str
    group: str
    input: str
    in_type: str
    out_type: str
    chain: str          # comma-separated filters; "" = let cfFilterUniversal() pick
    color: int = 1      # emulated printer supports color
    duplex: int = 1     # emulated printer supports duplex
    media: str = "iso_a4_210x297mm"
    copies: int = 1     # passed like CUPS argv[4], not in the options string
    options: str = ""


COLUMNS = list(Case.__dataclass_fields__)


def options_slug(options):
    """Readable, filesystem-safe name for an option string."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", options).strip("-") or "default"
    if len(slug) > 60:
        slug = slug[:50] + "-" + hashlib.sha1(options.encode()).hexdigest()[:8]
    return slug


def input_name(path):
    """corpus/pclm/16pixels/300dpi/x.pclm -> 16pixels_300dpi_x"""
    inside_type_folder = path.relative_to(CORPUS).parts[1:]
    return "_".join(inside_type_folder).rsplit(".", 1)[0]


def case(group, path, in_type, out_type, chain, options="", **printer):
    name = options_slug(options)
    if printer.get("copies", 1) > 1:
        name += f"-copies{printer['copies']}"
    if printer.get("color") == 0:
        name += "-mono-printer"
    if printer.get("duplex") == 0:
        name += "-simplex-printer"

    return Case(
        id=f"{group}/{input_name(path)}/{name}.{OUTPUT_EXT[out_type]}",
        group=group,
        input=path.relative_to(ROOT).as_posix(),
        in_type=in_type,
        out_type=out_type,
        chain=chain,
        options=options,
        **printer,
    )


# ---------------------------------------------------------------------------
# Pairwise (all-pairs) option combinations
# ---------------------------------------------------------------------------

def pairwise(factors, candidates_per_row=50, seed=0):
    """Pick rows until every pair of values from two different factors appears
    in at least one row.  Seeded, so the output is stable between runs."""
    rng = random.Random(seed)
    factor_pairs = list(itertools.combinations(range(len(factors)), 2))

    def pairs_in(row):
        return {(i, row[i], j, row[j]) for i, j in factor_pairs}

    missing = set()
    for i, j in factor_pairs:
        for a in range(len(factors[i])):
            for b in range(len(factors[j])):
                missing.add((i, a, j, b))

    rows = []
    while missing:
        # Start every candidate from one missing pair so each row makes progress.
        i, a, j, b = min(missing)
        best_row, best_gain = None, -1
        for _ in range(candidates_per_row):
            row = [rng.randrange(len(values)) for values in factors]
            row[i], row[j] = a, b
            gain = len(pairs_in(row) & missing)
            if gain > best_gain:
                best_row, best_gain = row, gain
        missing -= pairs_in(best_row)
        rows.append(best_row)

    return [" ".join(filter(None, (factors[k][v] for k, v in enumerate(row)))) for row in rows]


# ---------------------------------------------------------------------------
# Cases per filter group
# ---------------------------------------------------------------------------

def corpus_files(folder):
    base = CORPUS / folder
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*") if p.is_file() and not p.name.startswith("."))


def pdftopdf_cases(pdf):
    combos = [c for c in pairwise(PDFTOPDF_PAIRWISE_FACTORS) if c not in PDFTOPDF_OPTIONS]
    for options in PDFTOPDF_OPTIONS + combos:
        yield case("pdftopdf", pdf, PDF, PDF, "pdftopdf", options)
    yield case("pdftopdf", pdf, PDF, PDF, "pdftopdf", "", copies=2)
    yield case("pdftopdf", pdf, PDF, PDF, "pdftopdf", "collate=false", copies=2)
    yield case("pdftopdf", pdf, PDF, PDF, "pdftopdf", "", color=0, duplex=0)


def pdftoraster_cases(pdf):
    chain = "pdftopdf,pdftoraster"
    for options in RASTER_OPTIONS:
        yield case("pdftoraster", pdf, PDF, PWG, chain, options)
    yield case("pdftoraster", pdf, PDF, PWG, chain, "", color=0)
    yield case("pdftoraster", pdf, PDF, URF, chain)
    yield case("pdftoraster", pdf, PDF, CUPS_RASTER, chain)


def pwg_pclm_cases():
    for pdf in corpus_files("pdf"):
        yield case("pwg-pclm", pdf, PDF, PCLM, "")
        yield case("pwg-pclm", pdf, PDF, PCLM, "", "print-color-mode=monochrome")

    for folder, in_type in (("pwg", PWG), ("urf", URF)):
        for raster in corpus_files(folder):
            for options in RASTER_INPUT_OPTIONS:
                yield case("pwg-pclm", raster, in_type, PDF, "pwgtopdf", options)
                yield case("pwg-pclm", raster, in_type, PCLM, "pwgtopdf", options)
            yield case("pwg-pclm", raster, in_type, PWG, "pwgtoraster")


def pclmtoraster_cases():
    for pclm in corpus_files("pclm"):
        yield case("pclmtoraster", pclm, PCLM, PWG, "pclmtoraster")
        yield case("pclmtoraster", pclm, PCLM, PWG, "pclmtoraster", "print-color-mode=monochrome")
        yield case("pclmtoraster", pclm, PCLM, URF, "pclmtoraster")


def text_banner_image_cases():
    group = "text-banner-image"

    for txt in corpus_files("text"):
        for options in TEXT_OPTIONS:
            yield case(group, txt, TEXT, PDF, "texttopdf", options)
        yield case(group, txt, TEXT, TEXT, "texttotext")

    for banner in corpus_files("banner"):
        yield case(group, banner, BANNER, PDF, "bannertopdf")

    for image in corpus_files("image"):
        in_type = IMAGE_TYPES.get(image.suffix.lower())
        if not in_type:
            continue
        for options in IMAGE_OPTIONS:
            yield case(group, image, in_type, PDF, "imagetopdf", options)
        yield case(group, image, in_type, PWG, "imagetoraster")


def all_cases():
    cases = []
    for pdf in corpus_files("pdf"):
        cases += pdftopdf_cases(pdf)
        cases += pdftoraster_cases(pdf)
    cases += pwg_pclm_cases()
    cases += pclmtoraster_cases()
    cases += text_banner_image_cases()

    ids = [c.id for c in cases]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise SystemExit("duplicate case ids:\n  " + "\n  ".join(sorted(duplicates)))
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    cases = all_cases()
    with args.output.open("w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=COLUMNS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(asdict(c) for c in cases)

    print(f"{len(cases)} cases -> {args.output}")
    for group in sorted({c.group for c in cases}):
        print(f"  {group:20s} {sum(c.group == group for c in cases)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
