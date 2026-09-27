from jev_placement.config import load_config
from jev_placement.runtime import SafeRouter, HostGate
from adapter import propose, create_router

class MustNotCall:
    is_remote = False
    def evaluate(self, *args):
        raise AssertionError("Default-off integration called a model")

def test_default_off_preserves_baseline():
    with create_router(MustNotCall(), load_config()["runtime"]) as router:
        result = propose(router, task_id="smoke", state={}, baseline="inspect",
                         gate=HostGate(("inspect",)))
        assert result.action == "inspect"
        assert result.reason == "feature_off"
        assert router.require_expiring_activation is True
