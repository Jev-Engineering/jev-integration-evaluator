from pathlib import Path
import sys,copy
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from jev_integration_evaluator.config import load_config
from jev_integration_evaluator.io import read_json,read_jsonl

@pytest.fixture
def cfg():
    c=load_config();c['validation']['bootstrap_samples']=120;c['validation']['bayesian_samples']=200
    return c

@pytest.fixture
def root(): return ROOT

@pytest.fixture
def example_event(): return read_jsonl(ROOT/'examples/research/decisions.jsonl')[0]

@pytest.fixture
def response(): return next(iter(read_json(ROOT/'examples/research/fixture-responses.json').values()))

@pytest.fixture
def runs():
    return (read_jsonl(ROOT/'examples/research/baseline.jsonl'),read_jsonl(ROOT/'examples/research/router-verifier.jsonl'))
