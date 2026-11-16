"""The hashed private-term guard: the repo scan, and the hashing on synthetic text.

This file holds no term. Synthetic terms are built at run time from ROT13 so the
history rewrite leaves this file alone and the repo scan does not flag it.
"""

import codecs
import contextlib
import io
import os
import unittest

from scripts import private_terms

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _term(rot13):
    return codecs.decode(rot13, "rot13")


TOKEN = _term("barncc")          # index 0
FIRST_NAME = _term("znuzbhq")    # index 5
LAST_NAME = _term("ununo")       # index 4
PAIR = _term("jbexfgernzf znantre")  # index 6, a pair


class HashingTest(unittest.TestCase):
    def test_a_denylisted_token_hits(self):
        self.assertEqual(private_terms.line_hits(f"see the {TOKEN} app"), [0])

    def test_case_does_not_matter(self):
        self.assertEqual(private_terms.line_hits(TOKEN.upper()), [0])

    def test_a_denylisted_pair_hits(self):
        first, second = PAIR.split()
        self.assertEqual(private_terms.line_hits(f"the {first.title()} {second} plugin"), [6])
        self.assertEqual(private_terms.line_hits(f"{first}-{second}"), [6])

    def test_each_half_of_the_pair_alone_does_not_hit(self):
        for word in PAIR.split():
            self.assertEqual(private_terms.line_hits(f"a {word} here"), [])

    def test_a_users_path_hits(self):
        line = "cd " + "/" + "Users/someone/project"
        self.assertEqual(private_terms.line_hits(line), [private_terms.USERS_PATH])

    def test_a_placeholder_users_path_does_not_hit(self):
        self.assertEqual(private_terms.line_hits("/" + "Users/<name>/x"), [])

    def test_the_owner_name_does_not_hit(self):
        owner = FIRST_NAME.title() + LAST_NAME.title() + "Taher"
        self.assertEqual(private_terms.line_hits(owner), [])

    def test_a_dotted_name_splits_into_tokens_that_hit(self):
        self.assertEqual(private_terms.line_hits(f"{FIRST_NAME}.{LAST_NAME}"), [5, 4])

    def test_text_hits_names_the_line(self):
        text = "clean\nalso clean\nthe " + TOKEN + "\n"
        self.assertEqual(list(private_terms.text_hits(text)), [(3, 0)])

    def test_a_reported_hit_names_the_index_not_the_term(self):
        text = f"{TOKEN} and {PAIR} and " + "/" + "Users/someone"
        lines = [private_terms._format("f.md", n, label)
                 for n, label in private_terms.text_hits(text)]
        self.assertEqual(lines, ["f.md:1: term 0", "f.md:1: term 6", "f.md:1: users-path"])
        for term in (TOKEN, PAIR, "someone"):
            self.assertNotIn(term, "\n".join(lines))

    def test_the_module_holds_only_hashes(self):
        with open(private_terms.__file__, encoding="utf-8") as f:
            source = f.read().lower()
        for term in (TOKEN, FIRST_NAME, LAST_NAME, PAIR):
            self.assertNotIn(term, source)


class RepoScanTest(unittest.TestCase):
    def _run(self, argv):
        out = io.StringIO()
        cwd = os.getcwd()
        os.chdir(ROOT)
        try:
            with contextlib.redirect_stdout(out):
                code = private_terms.main(argv)
        finally:
            os.chdir(cwd)
        return code, out.getvalue()

    def test_the_default_scan_is_clean(self):
        code, output = self._run([])
        self.assertEqual(output.strip().splitlines()[-1], "0 hits", output)
        self.assertEqual(code, 0)

    def test_output_never_contains_the_term(self):
        code, output = self._run(["--all"])
        lowered = output.lower()
        for term in (TOKEN, FIRST_NAME, LAST_NAME, PAIR):
            self.assertNotIn(term, lowered)
        for line in output.strip().splitlines()[:-1]:
            self.assertTrue(line.startswith("workstreams/"), line)


if __name__ == "__main__":
    unittest.main()
