"""Smoke test verifying LifeLineDispatchApp initializes and steps frames cleanly in headless mode."""
from src.app.application import LifeLineDispatchApp


def test_app_initialization_and_stepping():
    app = LifeLineDispatchApp(headless=True)
    assert app is not None
    assert app.state is not None
    assert len(app.road_graph.nodes) == 64
    assert len(app.state.hospitals) == 3
    assert len(app.state.fleet) == 0

    # Step simulation frames
    for _ in range(10):
        app.taskMgr.step()

    # Verify simulation remains stable
    assert app.state.simulation_time == 0.0  # Not started yet
    assert len(app.state.fleet) == 0

    # Clean up app
    app.destroy()
    import builtins
    if hasattr(builtins, "base"):
        delattr(builtins, "base")
