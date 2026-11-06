"""Run the actual YAML parser and import sensor lambda with a host C++ compiler.

Uses only the Python standard library. This checks parser behavior, not ESPHome
configuration validation, ESP8266 timing, or delivery over the native API.
"""

import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ImportRecoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if compiler is None:
            raise RuntimeError("A C++ compiler (clang++ or g++) is required")
        config = (ROOT / "Veitur-P1-ESP.YAML").read_text()
        parser = textwrap.dedent(
            config.split("      - lambda: |-\n", 1)[1].split("\nglobals:", 1)[0]
        )
        globals_block = config.split("\nglobals:", 1)[1].split("\nsensor:", 1)[0]
        fields = re.findall(
            r"  - id: (\w+)\n    type: ([^\n]+)\n"
            r"    restore_value: no\n    initial_value: '([^\n]+)'",
            globals_block,
        )
        if len(fields) != globals_block.count("  - id:"):
            raise RuntimeError("Update the harness for the changed globals layout")
        sensor = re.search(
            r'name: "Cumulative Active Import"\n.*?    lambda: ([^\n]+)',
            config,
            re.DOTALL,
        ).group(1)
        declarations = "\n".join(
            f"{kind} {name} = {initial};" for name, kind, initial in fields
        )
        source = r'''
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>
using std::isnan;
#define id(x) state.x
#define ESP_LOGD(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
'''
        source += "struct State {\n" + declarations + "\n} state;\n"
        source += "void receive(const std::vector<unsigned char> &bytes) {\n"
        source += parser + "\n}\nfloat published_value() { " + sensor + " }\n"
        source += r'''
int main(int argc, char **) {
  std::string value;
  while (std::cin >> value) {
    std::string telegram = "/TEST\r\n";
    if (value != "-") telegram += "1-0:1.8.0(" + value + "*kWh)\r\n";
    telegram += "!\r\n";
    if (argc > 1) {
      for (unsigned char byte : telegram) receive({byte});
    } else {
      receive(std::vector<unsigned char>(telegram.begin(), telegram.end()));
    }
    std::cout << std::setprecision(9) << published_value() << '\n';
  }
}
'''
        cls.folder = tempfile.TemporaryDirectory(prefix="p1-import-test-")
        cls.addClassCleanup(cls.folder.cleanup)
        cpp = Path(cls.folder.name) / "parser.cpp"
        cls.binary = Path(cls.folder.name) / "parser-test"
        cpp.write_text(source)
        subprocess.run(
            [compiler, "-std=c++17", str(cpp), "-o", str(cls.binary)], check=True
        )

    def readings(self, values, expected, fragmented=False):
        result = subprocess.run(
            [str(self.binary)] + (["fragmented"] if fragmented else []),
            input="\n".join(map(str, values)),
            text=True,
            capture_output=True,
            check=True,
        )
        actual = [float(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(actual), len(expected))
        for index, (got, want) in enumerate(zip(actual, expected)):
            with self.subTest(reading=index):
                if math.isnan(want):
                    self.assertTrue(math.isnan(got))
                else:
                    # ESPHome stores these cumulative totals as float32.
                    self.assertAlmostEqual(got, want, delta=0.0021)

    def test_normal_and_unchanged_readings(self):
        self.readings([24000.945, 24000.955, 24000.955],
                      [24000.945, 24000.955, 24000.955])

    def test_recovery_after_gap_requires_three_readings(self):
        self.readings([24000.955, 24001.300, 24001.310, 24001.320, 24001.330],
                      [24000.955, 24000.955, 24000.955, 24001.320, 24001.330])

    def test_isolated_spike_does_not_publish(self):
        self.readings([1000, 1100, 1000.01], [1000, 1000, 1000.01])

    def test_backwards_readings_do_not_publish(self):
        self.readings([1000, 999, 999.01, 999.02], [1000] * 4)

    def test_candidate_going_backwards_restarts_confirmation(self):
        self.readings([1000, 1001, 1000.8, 1000.81, 1000.82],
                      [1000, 1000, 1000, 1000, 1000.82])

    def test_unstable_candidate_restarts_confirmation(self):
        self.readings([1000, 1001, 1002, 1002.01, 1002.02],
                      [1000, 1000, 1000, 1000, 1002.02])

    def test_missing_import_breaks_confirmation(self):
        self.readings([1000, 1001, "-", 1001.01, 1001.02, 1001.03],
                      [1000, 1000, 1000, 1000, 1000, 1001.03])

    def test_normal_reading_clears_pending_candidate(self):
        self.readings([1000, 1001, 1000.01, 1001.01, 1001.02, 1001.03],
                      [1000, 1000, 1000.01, 1000.01, 1000.01, 1001.03])

    def test_backwards_reading_breaks_confirmation(self):
        self.readings([1000, 1001, 999, 1001.01, 1001.02, 1001.03],
                      [1000, 1000, 1000, 1000, 1000, 1001.03])

    def test_missing_initial_reading_stays_unknown(self):
        self.readings(["-", "-", 1000], [math.nan, math.nan, 1000])

    def test_fragmented_telegram_recovery(self):
        self.readings([1000, 1001, 1001.01, 1001.02],
                      [1000, 1000, 1000, 1001.02], fragmented=True)


if __name__ == "__main__":
    unittest.main()
