#!/usr/bin/env python3
"""Render images/banner.svg from images/banner.svg.tmpl and the INSTALLED terragrunt.

WHY THIS EXISTS. The banner shows `terragrunt 1.1.3`. That is a version number baked into an
image -- a pin written somewhere nothing enforces, which is the exact failure this whole skill
was hardened against on 2026-08-19. SKILL.md used to say "current stable v1.1.2"; the claim
expired within a fortnight, the binary on the author's own machine was already 1.1.3, and
nothing noticed. Putting the same claim in a PNG makes it WORSE, because a PNG cannot be
grepped and nobody re-reads a picture.

So the banner is a build artifact too. The volatile parts are placeholders filled from
`scripts/preflight.py`, which reads `terragrunt --version` rather than asserting one, and the
banner is regenerated rather than edited.

WHAT IS AND IS NOT A PLACEHOLDER, because the distinction is the skill's own hard policy 3.
`v1.1.0+ autoinclude ...` and `v1.1.1+ oci:// sources` are facts about WHEN A FEATURE LANDED.
Those do not rot, so they stay in the template as literal text. What rots is the transcript
line -- which binary this was run against -- and which upgrade hazard is newest. Those two are
filled here.

DRIFT WARNS, IT DOES NOT BLOCK. `--check` reports that the committed banner no longer matches
the installed binary and exits 0 anyway. A check that fails the build the day Terragrunt ships
a patch is a check that gets commented out, and then the real drift arrives unannounced. Same
reasoning as preflight.py itself.

Usage:
    python3 scripts/make_banner.py            # rewrite banner.svg, and the rasters if the tools are here
    python3 scripts/make_banner.py --check    # say whether it is stale; never fails
    python3 scripts/make_banner.py --svg-only # skip rsvg-convert/cwebp/magick
"""

import argparse
import pathlib
import re
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
TMPL = ROOT / "images" / "banner.svg.tmpl"
SVG = ROOT / "images" / "banner.svg"
PNG = ROOT / "images" / "banner.png"          # intermediate, not committed
WEBP = ROOT / "images" / "banner.webp"
SOCIAL = ROOT / "images" / "social-preview.png"

W, H = 2752, 1536
# GitHub's social card is 2:1 and is uploaded by hand under Settings > General. It is NOT the
# README's first image and no workflow can carry it, because it does not live in the git tree.
SOCIAL_W, SOCIAL_H = 1280, 640

# The panel line is one row of a fixed-width box. A hazard longer than this pushes past the
# window edge, so it is truncated here rather than silently overflowing the image.
HAZARD_CHARS = 34


def preflight_text() -> str:
    if not shutil.which("terragrunt"):
        raise SystemExit(
            "terragrunt is not on PATH, so there is no version to read.\n"
            "That is the whole point of this script: it will not invent one."
        )
    proc = subprocess.run([sys.executable, str(HERE / "preflight.py")],
                          capture_output=True, text=True, check=False)
    return proc.stdout


def fields(text: str) -> dict[str, str]:
    """Pull the two volatile values out of preflight's report."""
    # x.y.z REQUIRED. `\S+` matched the word "is" out of "terragrunt is not installed" and
    # would have baked that into the image -- inventing a version by accident, which is the
    # one thing this script exists not to do. Caught by a test, not by reading it.
    m = re.search(r"^terragrunt\s+v?(\d+\.\d+\.\d+\S*)", text, re.M)
    if not m:
        raise SystemExit(f"could not read a version out of preflight.py's output:\n{text[:300]}")
    out = {"VERSION": m.group(1)}

    # `  ! 1.1.3: --filter now reserves ( and ) for the bounded-discovery ...`
    hazards = re.findall(r"^\s*!\s*(\d+\.\d+\.\d+):\s*(.+)$", text, re.M)
    if hazards:
        version, blurb = hazards[0]
        # First clause only. The full hazard is a paragraph; the banner has one line, and the
        # reference is where the detail belongs.
        blurb = re.split(r"(?<=[a-z\)])\s+for\s+|\.\s", blurb)[0].strip().rstrip(".")
        if len(blurb) > HAZARD_CHARS:
            blurb = blurb[: HAZARD_CHARS - 1].rstrip() + "…"
        out["HAZARD_VERSION"] = version
        out["HAZARD_TEXT"] = blurb
    else:
        # A build with no hazards in effect is a real state, not an error.
        out["HAZARD_VERSION"] = out["VERSION"]
        out["HAZARD_TEXT"] = "no upgrade hazards in effect"
    return out


def render(values: dict[str, str]) -> str:
    svg = TMPL.read_text(encoding="utf-8")
    for key, value in values.items():
        svg = svg.replace("{{" + key + "}}", value)
    left = re.findall(r"\{\{[A-Z_]+\}\}", svg)
    if left:
        raise SystemExit(f"template placeholders with no value: {sorted(set(left))}")
    return svg


def rasterise() -> list[str]:
    """SVG -> WebP for the README, plus the 2:1 PNG for the social card. Skipped, with a named
    reason, when a tool is missing -- the SVG is the source and is always written."""
    missing = [t for t in ("rsvg-convert", "cwebp", "magick") if not shutil.which(t)]
    if missing:
        return [f"skipped the rasters: {', '.join(missing)} not on PATH",
                "  brew install librsvg webp imagemagick"]
    subprocess.run(["rsvg-convert", "-w", str(W), "-h", str(H), str(SVG), "-o", str(PNG)],
                   check=True)
    subprocess.run(["cwebp", "-quiet", "-q", "92", str(PNG), "-o", str(WEBP)], check=True)
    subprocess.run(["magick", str(PNG), "-gravity", "center",
                    "-crop", f"{W}x{W // 2}+0+0", "+repage",
                    "-resize", f"{SOCIAL_W}x{SOCIAL_H}", "-strip", str(SOCIAL)], check=True)
    PNG.unlink()   # intermediate only; the committed rasters are the WebP and the social PNG
    return [f"wrote {WEBP.name} and {SOCIAL.name}"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="report drift against the installed terragrunt; never fails")
    ap.add_argument("--svg-only", action="store_true", help="do not rasterise")
    args = ap.parse_args()

    values = fields(preflight_text())
    fresh = render(values)

    if args.check:
        if not SVG.exists():
            print("WARN images/banner.svg has not been generated yet")
            print("     python3 scripts/make_banner.py")
            return 0
        if SVG.read_text(encoding="utf-8") == fresh:
            print(f"ok   banner matches the installed terragrunt {values['VERSION']}")
            return 0
        print(f"WARN banner is stale: the installed terragrunt is {values['VERSION']}")
        print("     the image is a pin nothing enforces unless it is regenerated:")
        print("     python3 scripts/make_banner.py")
        return 0

    SVG.write_text(fresh, encoding="utf-8")
    print(f"wrote {SVG.name} for terragrunt {values['VERSION']}")
    if not args.svg_only:
        for line in rasterise():
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
