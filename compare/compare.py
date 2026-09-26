#!/usr/bin/env python3
"""Compare the outputs of two runner results directories and write a report.

usage: compare.py --baseline results/baseline --candidate results/candidate --out report
"""

import argparse
import difflib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from raster import RasterError, read_raster

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "third_party" / "image-eval"))

# Worst first; a case takes the worst class of any of its checks.
SEVERITY = ["CRASH", "TIMEOUT", "EXIT_DIFF", "STRUCT_DIFF", "VISUAL_DIFF", "BOTH_FAIL", "VISUAL_EQUAL", "IDENTICAL"]
PASSING = {"IDENTICAL", "VISUAL_EQUAL", "BOTH_FAIL"}

PDF_TYPES = {"application/pdf", "application/PCLm"}
RASTER_TYPES = {"image/pwg-raster", "image/urf", "application/vnd.cups-raster"}


def worst(*classes):
    return min(classes, key=SEVERITY.index)


# ---------------------------------------------------------------------------
# Loading pages
# ---------------------------------------------------------------------------

def pdf_structure(path):
    """Page count plus per-page boxes and rotation from pdfinfo."""
    out = subprocess.run(["pdfinfo", "-box", "-f", "1", "-l", "100000", str(path)],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    pages = {}
    count = 0
    for line in out.stdout.splitlines():
        if line.startswith("Pages:"):
            count = int(line.split()[1])
        m = re.match(r"Page\s+(\d+)\s+(size|rot|MediaBox|CropBox):\s+(.*)", line)
        if m:
            value = m.group(3).strip()
            if m.group(2) in ("MediaBox", "CropBox"):
                value = [round(float(v), 1) for v in value.split()]
            elif m.group(2) == "size":
                value = value.split(" pts")[0]
            pages.setdefault(int(m.group(1)), {})[m.group(2)] = value
    return {"pages": count, "per_page": [pages.get(i, {}) for i in range(1, count + 1)]}


def render_pdf(path, dpi):
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(path), f"{tmp}/p"],
                       capture_output=True, check=False)
        files = sorted(Path(tmp).glob("p-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
        return [np.asarray(Image.open(f).convert("RGB")) for f in files]


def raster_pages(path, dpi):
    pages = read_raster(path)
    images, headers = [], []
    for page in pages:
        header = page["header"]
        img = Image.fromarray(page["image"])
        res = header.get("HWResolutionX") or dpi
        if res != dpi:
            img = img.resize((max(1, round(img.width * dpi / res)), max(1, round(img.height * dpi / res))),
                             Image.Resampling.BOX)
        images.append(np.asarray(img))
        headers.append(header)
    return images, headers


def load_output(path, out_type, dpi):
    """Return (structure dict, list of RGB page images) for one output file."""
    if out_type in PDF_TYPES:
        return pdf_structure(path), render_pdf(path, dpi)
    if out_type in RASTER_TYPES:
        images, headers = raster_pages(path, dpi)
        ignore = {"MediaClass", "MediaColor", "MediaType", "OutputType"}
        return {"pages": len(images), "per_page": [{k: v for k, v in h.items() if k not in ignore} for h in headers]}, images
    return None, []


# ---------------------------------------------------------------------------
# Page comparison
# ---------------------------------------------------------------------------

def quick_diff(a, b, level):
    """Fraction of pixels whose largest channel difference exceeds `level`."""
    delta = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2)
    return float((delta > level).mean())


def best_rotation(base, cand):
    """Which multiple of 90 degrees makes the candidate page look most like the baseline."""
    from skimage.metrics import structural_similarity as ssim

    def gray(img):
        return img.mean(axis=2).astype(np.uint8)

    scores = {}
    for k in range(4):
        rotated = np.rot90(base, k)
        if rotated.shape == cand.shape and min(cand.shape[:2]) >= 7:
            scores[k * 90] = float(ssim(gray(rotated), gray(cand)))
    return max(scores, key=scores.get) if scores else 0, scores


def deep_compare(base, cand, workdir, args):
    """Tier 2: image-eval metrics for a page that failed the quick check."""
    import cv2
    from enhanced_comparison import ImageComparator

    workdir.mkdir(parents=True, exist_ok=True)
    b_bgr = cv2.cvtColor(base, cv2.COLOR_RGB2BGR)
    c_bgr = cv2.cvtColor(cand, cv2.COLOR_RGB2BGR)

    comp = ImageComparator(b_bgr, c_bgr, output_dir=str(workdir))
    metrics = comp.basic_metrics()
    colour = comp.color_monochrome_detection()
    comp.generate_visual_diff()
    skew_base = comp.rotation_detection()["rotation_angle"]
    skew_cand = ImageComparator(c_bgr, b_bgr, output_dir=str(workdir)).rotation_detection()["rotation_angle"]
    rot, _ = best_rotation(base, cand)

    result = {
        "ssim": float(metrics["ssim"]),
        "psnr": float(metrics["psnr"]),
        "mse": float(metrics["mse"]),
        "skew_delta": float(abs(skew_base - skew_cand)),
        "baseline_gray": bool(colour["original_is_grayscale"]),
        "candidate_gray": bool(colour["processed_is_grayscale"]),
        "rotated_by": rot,
    }
    problems = []
    if result["ssim"] < args.ssim_threshold:
        problems.append(f"SSIM {result['ssim']:.3f}")
    if result["skew_delta"] > 1.0:
        problems.append(f"skew changed by {result['skew_delta']:.1f} deg")
    if result["baseline_gray"] != result["candidate_gray"]:
        problems.append("colour -> gray" if result["candidate_gray"] else "gray -> colour")
    if rot:
        problems.append(f"content rotated {rot} deg")
    result["problems"] = problems
    return result


def page_integrity(base_pages, cand_pages, workdir):
    from enhanced_comparison import ImageComparator
    import cv2

    workdir.mkdir(parents=True, exist_ok=True)
    thumbs = lambda pages: [cv2.cvtColor(np.asarray(Image.fromarray(p).resize((200, 280))), cv2.COLOR_RGB2BGR)
                            for p in pages]
    b, c = thumbs(base_pages), thumbs(cand_pages)
    res = ImageComparator(b[0], c[0], output_dir=str(workdir)).page_integrity_comparison(True, b, c)
    return {k: res[k] for k in ("missing_pages", "duplicated_pages", "page_ordering_correct") if k in res}


def save_thumb(img, path, max_side=320):
    im = Image.fromarray(img)
    im.thumbnail((max_side, max_side))
    im.save(path)


def diff_image(a, b):
    delta = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2)
    out = np.full(a.shape, 255, np.uint8)
    out[delta > 16] = (255, 0, 0)
    return out


# ---------------------------------------------------------------------------
# Case comparison
# ---------------------------------------------------------------------------

def compare_case(cid, base_res, cand_res, args):
    report = {"id": cid, "class": "IDENTICAL", "notes": [], "pages": []}
    if base_res is None or cand_res is None:
        report.update({"class": "EXIT_DIFF", "notes": ["case missing on one side"]})
        return report

    report["group"] = cand_res["group"]
    report["options"] = cand_res["options"]
    report["baseline"] = {k: base_res[k] for k in ("exit", "signal", "timeout", "duration")}
    report["candidate"] = {k: cand_res[k] for k in ("exit", "signal", "timeout", "duration")}

    if cand_res["timeout"]:
        report.update({"class": "TIMEOUT", "notes": ["candidate timed out"]})
        return report
    if cand_res["signal"]:
        report.update({"class": "CRASH", "notes": [f"candidate crashed ({cand_res['signal']})"]})
        return report

    base_ok, cand_ok = base_res["exit"] == 0, cand_res["exit"] == 0
    if not base_ok and not cand_ok:
        report.update({"class": "BOTH_FAIL", "notes": ["both builds failed"]})
        return report
    if base_ok != cand_ok:
        side = "candidate" if base_ok else "baseline"
        report.update({"class": "EXIT_DIFF", "notes": [f"only {side} failed (exit {cand_res['exit'] if base_ok else base_res['exit']})"]})
        return report

    b_file = args.baseline / "outputs" / cid
    c_file = args.candidate / "outputs" / cid
    out_type = cand_res["out_type"]
    workdir = args.out / "cases" / cid

    if out_type not in PDF_TYPES | RASTER_TYPES:
        a, b = b_file.read_bytes(), c_file.read_bytes()
        if a != b:
            report["class"] = "VISUAL_DIFF"
            diff = difflib.unified_diff(a.decode(errors="replace").splitlines(), b.decode(errors="replace").splitlines(),
                                        "baseline", "candidate", lineterm="", n=1)
            report["notes"].append("\n".join(list(diff)[:40]))
        return report

    try:
        b_struct, b_pages = load_output(b_file, out_type, args.dpi)
        c_struct, c_pages = load_output(c_file, out_type, args.dpi)
    except (RasterError, OSError) as e:
        report.update({"class": "STRUCT_DIFF", "notes": [f"unreadable output: {e}"]})
        return report

    if b_struct is None or c_struct is None:
        report.update({"class": "STRUCT_DIFF", "notes": ["output could not be parsed"]})
        return report

    if b_struct["pages"] != c_struct["pages"]:
        report["class"] = "STRUCT_DIFF"
        report["notes"].append(f"page count {b_struct['pages']} -> {c_struct['pages']}")
        if b_pages and c_pages:
            try:
                report["integrity"] = page_integrity(b_pages, c_pages, workdir)
            except Exception as e:     # image-eval is best-effort diagnostics
                report["notes"].append(f"page integrity check failed: {e}")

    for n, (bp, cp) in enumerate(zip(b_struct["per_page"], c_struct["per_page"]), 1):
        changed = {k: (bp.get(k), cp.get(k)) for k in set(bp) | set(cp) if bp.get(k) != cp.get(k)}
        if changed:
            report["class"] = worst(report["class"], "STRUCT_DIFF")
            report["notes"].append(f"page {n}: " + ", ".join(f"{k} {a} -> {b}" for k, (a, b) in sorted(changed.items())))

    first_diff_saved = False
    for n, (bi, ci) in enumerate(zip(b_pages, c_pages), 1):
        page = {"page": n}
        if bi.shape != ci.shape:
            page["class"] = "STRUCT_DIFF"
            page["problems"] = [f"rendered size {bi.shape[1]}x{bi.shape[0]} -> {ci.shape[1]}x{ci.shape[0]}"]
        else:
            frac = quick_diff(bi, ci, args.pixel_level)
            page["changed_pixels"] = frac
            if frac == 0:
                page["class"] = "IDENTICAL"
            elif frac <= args.pixel_fraction:
                page["class"] = "VISUAL_EQUAL"
            else:
                try:
                    page.update(deep_compare(bi, ci, workdir / f"page{n}", args))
                    page["class"] = "VISUAL_DIFF" if page["problems"] else "VISUAL_EQUAL"
                except Exception as e:
                    page["class"] = "VISUAL_DIFF"
                    page["problems"] = [f"{frac:.2%} pixels changed", f"deep compare failed: {e}"]

        if page["class"] not in ("IDENTICAL", "VISUAL_EQUAL") and not first_diff_saved:
            workdir.mkdir(parents=True, exist_ok=True)
            save_thumb(bi, workdir / "baseline.png")
            save_thumb(ci, workdir / "candidate.png")
            if bi.shape == ci.shape:
                save_thumb(diff_image(bi, ci), workdir / "diff.png")
            page["thumbs"] = True
            first_diff_saved = True

        report["class"] = worst(report["class"], page["class"])
        report["pages"].append(page)

    return report


def _compare_job(job):
    cid, b, c, args = job
    try:
        return compare_case(cid, b, c, args)
    except Exception as e:
        return {"id": cid, "class": "STRUCT_DIFF", "notes": [f"comparator error: {e!r}"], "pages": []}


# ---------------------------------------------------------------------------
# Known diffs and reporting
# ---------------------------------------------------------------------------

def load_known(path):
    """Lines: <case-id regex> <CLASS> <issue / note...>"""
    known = []
    if path and path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split(None, 2)
                known.append((re.compile(parts[0]), parts[1] if len(parts) > 1 else "*", parts[2] if len(parts) > 2 else ""))
    return known


def match_known(report, known):
    for rx, cls, note in known:
        if rx.fullmatch(report["id"]) and cls in ("*", report["class"]):
            return note or "known"
    return None


def write_html(reports, meta, path):
    rows = []
    for r in reports:
        if r["class"] in ("IDENTICAL", "VISUAL_EQUAL"):
            continue
        rel = f"cases/{r['id']}"
        imgs = ""
        if any(p.get("thumbs") for p in r.get("pages", [])):
            imgs = "".join(f'<figure><img src="{html.escape(rel)}/{n}.png" loading="lazy"><figcaption>{n}</figcaption></figure>'
                           for n in ("baseline", "candidate", "diff"))
        problems = [f"p{p['page']}: " + "; ".join(p.get("problems", [])) for p in r.get("pages", []) if p.get("problems")]
        details = "<br>".join(html.escape(x) for x in r.get("notes", []) + problems[:10])
        known = f'<div class="known">known: {html.escape(r["known"])}</div>' if r.get("known") else ""
        rows.append(f'<tr class="{r["class"]}"><td><b>{r["class"]}</b>{known}</td>'
                    f'<td><code>{html.escape(r["id"])}</code><br><small>{html.escape(r.get("options") or "")}</small></td>'
                    f'<td><pre>{details}</pre></td><td class="imgs">{imgs}</td></tr>')

    counts = "".join(f"<li>{c}: {meta['counts'].get(c, 0)}</li>" for c in SEVERITY)
    page = f"""<!doctype html><meta charset="utf-8"><title>libcupsfilters regression report</title>
<style>
body{{font:14px sans-serif;margin:1em}} table{{border-collapse:collapse;width:100%}}
td{{border-top:1px solid #ccc;vertical-align:top;padding:4px}} pre{{white-space:pre-wrap;margin:0}}
.imgs figure{{display:inline-block;margin:0 4px}} .imgs img{{max-width:220px;border:1px solid #999}}
.CRASH,.TIMEOUT,.EXIT_DIFF{{background:#fdd}} .STRUCT_DIFF{{background:#fed}} .VISUAL_DIFF{{background:#ffe}}
.BOTH_FAIL{{background:#eee}} .known{{color:#666;font-size:12px}}
</style>
<h1>libcupsfilters regression report</h1>
<p>baseline <code>{html.escape(meta['baseline'].get('ref', '?'))}</code> ({html.escape(meta['baseline'].get('sha', '')[:12])})
vs candidate <code>{html.escape(meta['candidate'].get('ref', '?'))}</code> ({html.escape(meta['candidate'].get('sha', '')[:12])})</p>
<ul>{counts}</ul><p>{meta['unexpected']} unexpected differences. Identical and visually-equal cases are omitted.</p>
<table>{''.join(rows)}</table>"""
    path.write_text(page)


def write_markdown(reports, meta, path):
    lines = [f"### libcupsfilters regression: {meta['candidate'].get('ref', '?')} vs {meta['baseline'].get('ref', '?')}", "",
             "| class | cases |", "|---|---|"]
    lines += [f"| {c} | {meta['counts'].get(c, 0)} |" for c in SEVERITY]
    lines += ["", f"**{meta['unexpected']} unexpected differences**", ""]
    unexpected = [r for r in reports if r["class"] not in PASSING and not r.get("known")]
    for r in unexpected[:50]:
        lines.append(f"- `{r['class']}` `{r['id']}` {'; '.join(r.get('notes', []))[:200]}")
    if len(unexpected) > 50:
        lines.append(f"- ... and {len(unexpected) - 50} more (see report.html)")
    path.write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", required=True, type=Path)
    ap.add_argument("--candidate", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--known-diffs", type=Path, default=HERE.parent / "known-diffs.txt")
    ap.add_argument("--strict", action="store_true", help="exit 1 on any unexpected difference")
    ap.add_argument("--dpi", type=int, default=72, help="resolution pages are compared at")
    ap.add_argument("--pixel-level", type=int, default=24, help="per-channel difference ignored as noise")
    ap.add_argument("--pixel-fraction", type=float, default=0.001, help="changed-pixel fraction still treated as equal")
    ap.add_argument("--ssim-threshold", type=float, default=0.97)
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    args = ap.parse_args()
    args.baseline, args.candidate, args.out = args.baseline.resolve(), args.candidate.resolve(), args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)

    base = json.loads((args.baseline / "results.json").read_text())
    cand = json.loads((args.candidate / "results.json").read_text())
    ids = sorted(set(base["cases"]) | set(cand["cases"]))
    jobs = [(cid, base["cases"].get(cid), cand["cases"].get(cid), args) for cid in ids]

    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        reports = list(pool.map(_compare_job, jobs, chunksize=4))

    known = load_known(args.known_diffs)
    for r in reports:
        if r["class"] not in PASSING:
            r["known"] = match_known(r, known)
    reports.sort(key=lambda r: (SEVERITY.index(r["class"]), r["id"]))

    counts = {}
    for r in reports:
        counts[r["class"]] = counts.get(r["class"], 0) + 1
    unexpected = sum(1 for r in reports if r["class"] not in PASSING and not r.get("known"))
    meta = {"baseline": base.get("build", {}), "candidate": cand.get("build", {}), "counts": counts,
            "unexpected": unexpected, "total": len(reports)}

    (args.out / "summary.json").write_text(json.dumps({"meta": meta, "cases": reports}, indent=1, default=float))
    write_html(reports, meta, args.out / "report.html")
    write_markdown(reports, meta, args.out / "summary.md")

    print(json.dumps(counts, indent=1))
    print(f"{unexpected} unexpected differences -> {args.out / 'report.html'}")
    return 1 if args.strict and unexpected else 0


if __name__ == "__main__":
    sys.exit(main())
