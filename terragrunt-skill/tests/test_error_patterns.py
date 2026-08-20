"""error-patterns.md against the numbers three other files quote about it.

The file went through two rounds of prose-vs-content drift in one day. #34 removed a
`**Match:**` field that had shipped empty in all 68 entries; #35 found that the same cleanup
had left 52 `**Solutions:**` headings with nothing under them. Both were invisible to every
structural check in the repo because both were about CONTENT, not shape.

`check_conventions.py` now asserts the ENTRY count against SKILL.md's navigation table. These
tests assert the second number the skill advertises -- how many of those entries actually carry
a fix -- because that is the one a reader acts on, and it is quoted in three places that have
no mechanical relationship to the file.
"""
import re
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
PATTERNS = SKILL / "references" / "error-patterns.md"


def entries() -> dict[str, str]:
    parts = re.split(r"(?m)^## ERROR: (.*)$", PATTERNS.read_text(encoding="utf-8"))
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts), 2)}


def with_a_fix() -> list[str]:
    return [t for t, b in entries().items() if "**Solutions:**" in b]


def test_every_entry_names_a_cause():
    """A cause is the floor. An entry with neither a cause nor a fix is a heading."""
    missing = [t for t, b in entries().items() if "**Likely causes:**" not in b]
    assert not missing, f"entries with no likely causes: {missing}"


def test_no_solutions_heading_is_empty():
    """The #35 defect, pinned. A heading that promises a fix and holds none is worse than no
    heading at all -- the reader greps, lands on it, and reads the absence as 'no fix exists'."""
    hollow = [t for t, b in entries().items()
              if re.search(r"(?m)^\*\*Solutions:\*\*[ \t]*\n\s*\Z", b)]
    assert not hollow, f"entries whose Solutions section is empty: {hollow}"


def test_the_advertised_fix_count_matches_the_file():
    """SKILL.md, README.md and the file's own header all quote this number. None of them is
    derived from the file, so all three can drift and only a reader would notice."""
    n = len(with_a_fix())
    claims = {
        "SKILL.md": (SKILL / "SKILL.md").read_text(encoding="utf-8"),
        "README.md": (SKILL / "README.md").read_text(encoding="utf-8"),
        "error-patterns.md": PATTERNS.read_text(encoding="utf-8"),
    }
    for name, text in claims.items():
        quoted = re.findall(r"(\d+)\s*(?:carry a fix|with a fix)", text)
        assert quoted, f"{name} no longer states how many entries carry a fix"
        for q in quoted:
            assert int(q) == n, f"{name} claims {q} entries carry a fix; the file has {n}"


def test_a_verified_entry_names_the_version_it_was_verified_against():
    """'Verified' with no version is the pin this skill exists to stop writing. The claim has
    to say which build it was checked on, or it decays silently the way 'current stable
    v1.1.2' did."""
    bad = [t for t, b in entries().items()
           if "Verified" in b and not re.search(r"Verified against terragrunt \d+\.\d+\.\d+", b)]
    assert not bad, f"entries claiming verification without naming a version: {bad}"


def test_no_entry_teaches_a_command_the_installed_binary_rejects():
    """Cheap containment: every `terragrunt <word>` in a fenced block must be a real
    subcommand. Does not check that the advice is good -- only that it is addressed to a CLI
    that exists. This is the failure the skill exists to prevent and could not detect in
    itself."""
    # Copied from `terragrunt --help` on 1.1.3, plus the documented aliases and the
    # OpenTofu shortcuts it forwards. CI has no terragrunt binary, so this list is static --
    # which makes it a pin, and the reason the docstring above says what this does NOT check.
    # It found `terragrunt clear-cache` on its first run: removed in the 1.0 redesign, and
    # 1.1.3 answers it with `unknown command: "clear-cache"`. scan_pre10.py could not see it,
    # because that scanner knows the RENAMED forms and this one was simply deleted.
    known = {
        # main
        "backend", "exec", "run", "stack",
        # catalog / discovery / configuration
        "catalog", "scaffold", "browse", "find", "fd", "list", "ls",
        "dag", "hcl", "info", "render",
        # OpenTofu shortcuts
        "apply", "destroy", "force-unlock", "import", "init", "output", "plan",
        "refresh", "show", "state", "test", "validate", "workspace",
        # global
        "version", "help",
    }
    used = set()
    for body in entries().values():
        for block in re.findall(r"```(?:bash|sh)?\n(.*?)```", body, re.S):
            for m in re.finditer(r"(?m)^\s*terragrunt\s+((?:--?\S+\s+)*)([a-z][\w-]*)", block):
                used.add(m.group(2))
    unknown = sorted(used - known)
    assert not unknown, f"error-patterns.md teaches unknown terragrunt subcommands: {unknown}"
