import tempfile
import textwrap
import unittest
from pathlib import Path

from services.analyzer import ProjectAnalyzer


class TreeSitterAnalysisTests(unittest.TestCase):
    def test_extracts_php_test_function_details(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            test_dir = root / "tests" / "Unit"
            test_dir.mkdir(parents=True)

            (test_dir / "ExampleTest.php").write_text(
                textwrap.dedent(
                    """
                    <?php

                    use PHPUnit\\Framework\\TestCase;

                    class ExampleTest extends TestCase
                    {
                        public function testBooleanTrueIsTrue(): void
                        {
                            $this->assertTrue(true);
                        }
                    }
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            results = ProjectAnalyzer(str(root)).analyze()

            self.assertIn("test_analysis", results)
            self.assertGreater(len(results["test_analysis"]), 0)

            test_case = results["test_analysis"][0]
            self.assertEqual(test_case["name"], "testBooleanTrueIsTrue")
            self.assertEqual(test_case["file"], "tests/Unit/ExampleTest.php")
            self.assertEqual(test_case["framework"], "PHPUnit")
            self.assertIn("assertTrue(true)", test_case["assertions"])
            self.assertIn("true", test_case["summary"].lower())


if __name__ == "__main__":
    unittest.main()
