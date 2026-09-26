#!/usr/bin/env python3
"""Build and install one libcupsfilters ref into a self-contained prefix."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APT_DEPS = [
    "build-essential", "autoconf", "automake", "libtool", "pkg-config", "gettext",
    "autopoint", "git", "wget", "file", "libcups2-dev", "libqpdf-dev",
    "libpoppler-cpp-dev", "libexif-dev", "liblcms2-dev", "libfontconfig1-dev",
    "libfreetype6-dev", "libjpeg-dev", "libpng-dev", "libtiff-dev", "libjxl-dev",
    "libdbus-1-dev", "poppler-utils", "ghostscript", "mupdf-tools",
    "fonts-dejavu-core", "fonts-freefont-ttf",
]


def run(cmd, cwd=None, env=None):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, check=True)


def capture(cmd, env=None):
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "none"


def install_deps():
    sudo = [] if os.geteuid() == 0 else ["sudo", "-n"]
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive", NEEDRESTART_MODE="a")
    run(sudo + ["apt-get", "update", "-y"], env=env)
    # Superset for both sides so the two builds see identical optional features.
    run(sudo + ["apt-get", "install", "-y"] + APT_DEPS, env=env)
    subprocess.run(sudo + ["apt-get", "remove", "-y", "libcupsfilters-dev"], env=env)


def build_pdfio(version, prefix, env, jobs):
    with tempfile.TemporaryDirectory() as tmp:
        name = f"pdfio-{version}"
        url = f"https://github.com/michaelrsweet/pdfio/releases/download/v{version}/{name}.tar.gz"
        run(["wget", "-q", url], cwd=tmp)
        run(["tar", "-xzf", f"{name}.tar.gz"], cwd=tmp)
        src = Path(tmp, name)
        run(["./configure", f"--prefix={prefix}", "--enable-shared"], cwd=src, env=env)
        run(["make", f"-j{jobs}", "all"], cwd=src, env=env)
        run(["make", "install"], cwd=src, env=env)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default="https://github.com/OpenPrinting/libcupsfilters.git")
    ap.add_argument("--ref")
    ap.add_argument("--prefix", type=Path)
    ap.add_argument("--side", choices=["baseline", "candidate"])
    ap.add_argument("--install-deps", action="store_true", help="apt-get install build deps (CI)")
    ap.add_argument("--deps-only", action="store_true", help="only install deps, do not build")
    ap.add_argument("--pdfio", choices=["auto", "yes", "no"], default="auto",
                    help="build PDFio into the prefix (candidate only)")
    ap.add_argument("--pdfio-version", default="1.6.4")
    ap.add_argument("--configure-arg", action="append", default=[],
                    help="extra ./configure argument; apply the same ones to both sides")
    args = ap.parse_args()

    if args.install_deps or args.deps_only:
        install_deps()
    if args.deps_only:
        return 0
    if not (args.ref and args.prefix and args.side):
        ap.error("--ref, --prefix and --side are required")

    prefix = args.prefix.resolve()
    prefix.mkdir(parents=True, exist_ok=True)
    jobs = os.cpu_count() or 2
    env = dict(os.environ)
    env["PKG_CONFIG_PATH"] = os.pathsep.join(filter(None, [str(prefix / "lib/pkgconfig"), env.get("PKG_CONFIG_PATH")]))
    env["LD_LIBRARY_PATH"] = os.pathsep.join(filter(None, [str(prefix / "lib"), env.get("LD_LIBRARY_PATH")]))

    if args.side == "candidate" and args.pdfio != "no":
        have = subprocess.run(["pkg-config", f"--atleast-version={args.pdfio_version}", "pdfio"], env=env).returncode == 0
        if args.pdfio == "yes" or not have:
            build_pdfio(args.pdfio_version, prefix, env, jobs)

    src = Path(tempfile.mkdtemp(prefix="libcupsfilters-"))
    try:
        run(["git", "clone", "--quiet", args.repo, src])
        run(["git", "checkout", "--quiet", args.ref], cwd=src)
        sha = capture(["git", "-C", str(src), "rev-parse", "HEAD"])

        run(["./autogen.sh"], cwd=src, env=env)
        run(["./configure", f"--prefix={prefix}", f"--libdir={prefix}/lib"] + args.configure_arg, cwd=src, env=env)
        run(["make", f"-j{jobs}"], cwd=src, env=env)
        # Data files normally go to the system CUPS datadir; keep them inside the prefix.
        run(["make", "install", f"CUPS_DATADIR={prefix}/share/cups"], cwd=src, env=env)

        info = prefix / "share/libcupsfilters-regression"
        info.mkdir(parents=True, exist_ok=True)
        shutil.copy(src / "config.log", info / "config.log")
        lines = {
            "side": args.side,
            "repo": args.repo,
            "ref": args.ref,
            "sha": sha,
            "cc": capture([env.get("CC", "cc"), "--version"]).splitlines()[0],
            "cups": capture(["pkg-config", "--modversion", "cups"], env),
            "pdfio": capture(["pkg-config", "--modversion", "pdfio"], env),
            "qpdf": capture(["pkg-config", "--modversion", "libqpdf"], env),
            "poppler-cpp": capture(["pkg-config", "--modversion", "poppler-cpp"], env),
        }
        text = "".join(f"{k}={v}\n" for k, v in lines.items())
        (info / "build-info.txt").write_text(text)
        print(text, end="")
    finally:
        shutil.rmtree(src, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
