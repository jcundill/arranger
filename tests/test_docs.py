"""The documents must describe the code that actually exists.

Phase 8 exists because of one measured fact: `AGENTS.md` had grown to 1710 lines and
had gone stale in ways an agent would act on. It described a single 4290-line
`arranger.py` (it is a package of eleven modules), gave `pyright arranger.py` as the
typecheck command, and stated the version as both `0.8.0` and `0.7.0` while
`__version__` was `0.9.0`. It had **zero** mention of the walking bass, which ships in
0.9.0.

Staleness is invisible to a linter and to a test suite that only tests behaviour, so
these assertions make the drift fail instead. They are deliberately narrow — each one
is a fact that was *observed* to be wrong, not a rule invented in the abstract:

- the stated version equals `arranger.__version__`, wherever a document states one;
- every module on disk appears in the layout block of `AGENTS.md`, so a new module
  cannot be created without being documented;
- no document claims the engine is a single file, because that was the specific lie
  Phase 5 made true;
- every relative link between the documents resolves, because a routing table that
  points at a file that moved is worse than no table at all.

None of this requires a database or an optional extra, so unlike the corpus tests it
always runs.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import List, Set

import arranger

ROOT = Path(__file__).resolve().parent.parent

#: The documents an agent is most likely to read first. A fact asserted here is
#: asserted because it was wrong in one of these, not because it is worth asserting
#: in the abstract.
DOCUMENTS = [
    "AGENTS.md",
    "README.md",
    "docs/engine.md",
    "docs/renderers.md",
    "docs/corpus.md",
    "docs/open-issues.md",
]

#: Matches a version as stated in prose: `0.9.0`, `` `0.9.0` ``, "currently 0.9.0".
_VERSION = re.compile(r"\b(\d+\.\d+\.\d+)\b")

#: The layout block in AGENTS.md: a fenced code block that names the layout heading.
_LAYOUT_BLOCK = re.compile(r"## Repository layout\s*\n+```\n(.*?)```", re.DOTALL)

#: A relative markdown link - one that is not a URL and not a bare `#anchor`.
_LINK = re.compile(r"\]\((?!https?://|#)([^)\s]+)\)")

#: The CI workflow. Named here rather than inline so the tests below can say
#: which file they are about.
CI_WORKFLOW = ".github/workflows/ci.yml"


def _read(name: str) -> str:
    """Read a document relative to the repository root."""
    return (ROOT / name).read_text(encoding="utf-8")


def _layout_block() -> str:
    """The fenced tree under `## Repository layout` in `AGENTS.md`.

    A function rather than a regex call at the use site because pyright does not
    narrow through `assertIsNotNone` - a narrowing trap `AGENTS.md` records - so
    the optional has to be resolved where the type is still known.
    """
    found = _LAYOUT_BLOCK.search(_read("AGENTS.md"))
    if found is None:
        raise AssertionError("AGENTS.md has no '## Repository layout' block")
    return found.group(1)

class TestDocsMatchTheCode(unittest.TestCase):
    """Documentation drift fails the suite instead of misleading the next agent."""

    def test_the_stated_version_is_the_packages_version(self):
        """No document may state a version other than `arranger.__version__`.

        The old `AGENTS.md` said `0.8.0` in one sentence and `0.7.0` in another while
        the code said `0.9.0`. A version stated in prose has no way to be right for
        long, so this pins the number wherever a document bothers to state one.
        """
        current = arranger.__version__
        wrong = []
        for name in DOCUMENTS:
            for found in _VERSION.findall(_read(name)):
                if found != current:
                    wrong.append(f"{name} states {found}")
        self.assertEqual(
            wrong, [], f"docs disagree with arranger.__version__ == {current!r}"
        )

    def test_every_module_appears_in_the_layout(self):
        """The layout block names every module on disk.

        The old layout listed `arranger.py` and omitted nine of the eleven modules
        the split created, so an agent reading it was told the engine was one file.
        Deriving the list from the filesystem is what makes this hold as modules are
        added rather than only as they are remembered.
        """
        block = _layout_block()

        undocumented: List[str] = []
        for module in sorted((ROOT / "arranger").glob("*.py")):
            if module.name not in block:
                undocumented.append(f"arranger/{module.name}")
        for module in sorted(ROOT.glob("*.py")):
            if module.name not in block:
                undocumented.append(module.name)
        self.assertEqual(
            undocumented, [], "a module exists that the layout block does not name"
        )

    def test_no_document_calls_the_engine_a_single_file(self):
        """`arranger.py` is gone; a document must not tell an agent to edit it.

        The phase this replaces was written against a module that no longer exists,
        and every reference to it was an instruction that could not be followed. This
        is the assertion that would have caught the original drift.
        """
        offenders = [
            f"{name}:{number}"
            for name in DOCUMENTS
            for number, line in enumerate(_read(name).splitlines(), 1)
            if "arranger.py" in line
        ]
        self.assertEqual(
            offenders, [], "a document still points at the pre-split single module"
        )

    def test_the_relative_links_between_documents_resolve(self):
        """A routing table must point at files that exist.

        `AGENTS.md` now routes every subsystem to its own document, so a stale link
        is a wrong turn on the first page an agent reads. The check is on the file
        part only: an anchor is GitHub's business, and asserting them would make this
        brittle for no gain.
        """
        broken: List[str] = []
        for name in DOCUMENTS:
            for target in _LINK.findall(_read(name)):
                path = (ROOT / name).parent / target.split("#", 1)[0]
                if not path.exists():
                    broken.append(f"{name} -> {target}")
        self.assertEqual(broken, [], "a document links to a file that does not exist")

    def test_the_routing_table_reaches_every_document(self):
        """Each topic document is reachable from `AGENTS.md`.

        The point of splitting the old file is that an agent is *sent* to the right
        one. A topic document nothing links to is a document nobody reads, which is
        the same failure as never having written it.
        """
        linked: Set[str] = {
            target.split("#", 1)[0]
            for target in _LINK.findall(_read("AGENTS.md"))
        }
        unreachable = [
            name
            for name in DOCUMENTS
            if name != "AGENTS.md" and name not in linked
        ]
        self.assertEqual(
            unreachable, [], "a topic document is not reachable from AGENTS.md"
        )


class TestTheCiWorkflowMatchesTheProject(unittest.TestCase):
    """A workflow that has drifted from the project it checks is worse than none.

    The same argument as the rest of this file: staleness is invisible to a
    linter, and a CI file is read far less often than it is trusted. These
    assertions are each one fact that was **measured** while writing the workflow,
    not a rule invented afterwards.
    """

    def workflow(self) -> str:
        return _read(CI_WORKFLOW)

    def test_the_matrix_covers_every_python_the_package_claims(self):
        """The matrix is `requires-python` and the classifiers, exactly.

        The package declares `>=3.11` and classifiers through 3.14. A matrix
        narrower than that is a claim of support the gate does not check; a wider
        one tests versions the metadata disclaims.

        The floor is checked in both directions because it moved once already:
        3.10 was dropped, and a stale `"3.10"` left in the matrix would spend a
        fifth of every CI run proving a version the metadata now disclaims. That
        check is worth having precisely because `tests/test_docs.py` itself reads
        `pyproject.toml` through `tomllib`, which only exists on 3.11+ - the test
        asserting the floor could not have run on the version below it.
        """
        import tomllib

        declared = tomllib.loads(_read("pyproject.toml"))
        self.assertEqual(declared["project"]["requires-python"], ">=3.11")
        self.assertNotIn(
            "Programming Language :: Python :: 3.10",
            _read("pyproject.toml"),
            "3.10 is disclaimed as a floor and must not be classified",
        )
        self.assertIn(
            "Programming Language :: Python :: 3.14",
            _read("pyproject.toml"),
            "the package claims 3.14 and the matrix must test it",
        )

        text = self.workflow()
        for version in ("3.11", "3.12", "3.13", "3.14"):
            self.assertIn(
                f'"{version}"', text, f"{version} is classified but not in the matrix"
            )
        self.assertNotIn('"3.10"', text, "the matrix tests a version metadata disclaims")
        self.assertNotIn("3.15", text, "the matrix tests a version metadata disclaims")

    def test_the_extras_are_installed_so_the_guards_do_not_silently_skip(self):
        """`.[xml,gp,dev]` is in the install step, spelled out rather than implied.

        Without the extras every `skipUnless(HAS_MUSIC21)` and
        `skipUnless(HAS_GUITARPRO)` guard skips silently, and a workflow whose
        skips come from missing packages rather than a missing database is
        quietly testing less than it looks like it is.
        """
        text = self.workflow()
        self.assertIn("pip install -e '.[xml,gp,dev]'", text)

    def test_pyright_is_given_a_filesystem_path_not_a_bare_name(self):
        """`PYTHON="$(command -v python)"`, and this is the assertion for it.

        `make typecheck` runs `pyright --pythonpath $(PYTHON)`, and pyright reads
        that as a *path to an interpreter* rather than resolving a name through
        `PATH`. Measured while writing the workflow: `PYTHON=python` runs the
        tests perfectly and makes pyright report **37 spurious import errors** on a
        clean tree, every one of them a package that was installed and importing
        fine. That is AGENTS.md's trap #2 reproduced by the very file written to
        enforce the gate, and a CI job that is red on a clean checkout teaches
        everyone to ignore it.
        """
        text = self.workflow()
        self.assertIn('PYTHON="$(command -v python)"', text)
        self.assertNotIn(
            "PYTHON=python ",
            text,
            "a bare interpreter name makes pyright blind to every installed package",
        )

    def test_the_workflow_says_the_database_tests_do_not_run(self):
        """The header states that the corpus path is skipped, and how badly.

        Measured: 85 skipped on a clean clone against 2 with the database
        present. An agent reading a green check must not conclude the Weimar path
        was exercised, so the file has to say so in its own words rather than
        leaving it to be inferred from a `skipUnless`.
        """
        header = self.workflow().split("jobs:")[0]
        self.assertIn("85", header)
        self.assertIn("does NOT mean", header)

    def test_the_corpus_job_fails_loudly_when_its_variable_is_unset(self):
        """A gated job that skips silently is indistinguishable from one that ran.

        The database has no stable download URL this repository can name, so the
        job reads `vars.WJAZZD_DB_URL`. Until that is set the job must **exit
        non-zero** rather than skip: a silently-skipped corpus job looks exactly
        like a passing one in the checks UI, which is the failure mode the header
        is warning about in the first place.
        """
        text = self.workflow()
        corpus = text.split("  corpus:")[1]
        self.assertIn("vars.WJAZZD_DB_URL", corpus)
        self.assertIn("exit 1", corpus)
        self.assertIn("workflow_dispatch", text)


if __name__ == "__main__":
    unittest.main()

