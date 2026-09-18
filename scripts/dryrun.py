#!/usr/bin/env python3
"""Exercise the complete pipeline in a temporary repo, without models or real servers."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from test_relay import PipelineTest

suite = unittest.TestSuite([PipelineTest('test_complete_lifecycle_and_isolation')])
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
