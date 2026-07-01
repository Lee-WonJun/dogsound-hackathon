import unittest

from processor.ui import _wrapped_box_lines


class DashboardWrappingTests(unittest.TestCase):
    def test_wrapped_lines_default_to_head(self) -> None:
        lines = "\n".join(_wrapped_box_lines("one\ntwo\nthree", 24, max_lines=2))

        self.assertIn("one", lines)
        self.assertIn("two", lines)
        self.assertNotIn("three", lines)
        self.assertIn("...", lines)

    def test_wrapped_lines_can_show_tail_for_live_output(self) -> None:
        lines = "\n".join(_wrapped_box_lines("one\ntwo\nthree", 24, max_lines=2, tail=True))

        self.assertNotIn("one", lines)
        self.assertIn("... two", lines)
        self.assertIn("three", lines)


if __name__ == "__main__":
    unittest.main()
