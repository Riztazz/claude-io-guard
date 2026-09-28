"""The io-guard skill page ships with the tool and code tables its declarations give, stays short enough to
load whole, and keeps the tables between the lines that mark them."""
import re
import unittest

from ioguard.lib.results import CODES, callable_name
from ioguard.mcp import skill
from ioguard.mcp.server import registry


class ThePageMatchesItsDeclarations(unittest.TestCase):
    def setUp(self):
        self.page = skill.PAGE.read_bytes().decode("utf-8")

    def test_the_shipped_tables_are_the_ones_the_declarations_give(self):
        self.assertEqual(skill.written(self.page, skill.tables()), self.page,
                         "a new tool or code needs python tools/skill.py before it ships")

    def test_every_tool_the_model_calls_and_every_code_has_a_row(self):
        tools = [spec.name for spec in registry().specs.values() if spec.input is not None]
        missing = [name for name in tools if f"`{callable_name(name)}`" not in self.page]
        missing += [spec.code for spec in CODES if f"| `{spec.code}` |" not in self.page]
        self.assertEqual(missing, [], "the page names each io tool by its callable name, and each code")
        self.assertNotIn("hook.pre_tool_use", self.page, "the hook tools, which the model never calls, are "
                                                           "left out")

    def test_the_page_loads_whole_and_its_description_fits(self):
        description = re.search(r"^description: (.*)$", self.page, re.MULTILINE)[1]
        self.assertEqual((self.page.isascii(), len(self.page.splitlines()) < 150, len(description) <= 500),
                         (True, True, True),
                         "the page is ASCII, under 150 lines, and its description at most 500 characters")


class TheTablesLandBetweenTheirLines(unittest.TestCase):
    def test_a_table_replaces_what_lies_between_its_lines(self):
        page = f"top\n{skill.begin('codes')}\nold row\n{skill.end('codes')}\nbottom\n"
        self.assertEqual(skill.written(page, {"codes": "new row"}),
                         f"top\n{skill.begin('codes')}\nnew row\n{skill.end('codes')}\nbottom\n",
                         "the text outside the two lines stays as written")

    def test_a_page_without_the_lines_is_refused(self):
        with self.assertRaises(ValueError, msg="a page that lost its lines is never written over"):
            skill.written("no lines here\n", {"codes": "row"})

    def test_a_pipe_in_a_cell_is_escaped(self):
        spec = CODES[0].__class__("X_CODE", CODES[0].layer, CODES[0].severity, "a | b", "c", "0.1")
        self.assertIn("| a \\| b | c |", skill.code_table([spec]), "a pipe inside a cell does not split it")


if __name__ == "__main__":
    unittest.main()
