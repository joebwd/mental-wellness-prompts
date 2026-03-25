import unittest

from rich.console import Console

from wellness_cli import cli


class CLIBrandingTests(unittest.TestCase):
    def test_animated_wordmark_mentions_moss_and_animates(self):
        first = cli._animated_wordmark(0).plain
        second = cli._animated_wordmark(1).plain

        self.assertIn("moss", first)
        self.assertNotEqual(first, second)

    def test_animated_footer_uses_mode_specific_copy(self):
        thinking = cli._animated_footer(0, mode="thinking").plain
        processing = cli._animated_footer(0, mode="processing").plain

        self.assertIn(cli.FOOTER_PULSE_FRAMES[0], thinking)
        self.assertIn(cli.FOOTER_LINES["thinking"][0], thinking)
        self.assertIn(cli.FOOTER_LINES["processing"][0], processing)
        self.assertNotEqual(thinking, processing)

    def test_user_bubble_footer_keeps_continuous_border_and_tag_spacing(self):
        console = Console(width=80, record=True, highlight=False)
        panel = cli._build_user_panel("oh fuck", name="Joe-", width=60)

        console.print(panel, justify="right")

        bottom_line = [line for line in console.export_text().splitlines() if line.strip()][-1]
        self.assertIn(" JOE- ─╯", bottom_line)
        self.assertNotIn("╰─  ─", bottom_line)


if __name__ == "__main__":
    unittest.main()
