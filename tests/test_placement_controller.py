"""Tests for interactive 3D placement controller and raycast snapping."""
from src.ui.placement_controller import PlacementController
from src.world.city_generator import CityGenerator


class MockTaskManager:
    def add(self, fn, name):
        pass

    def remove(self, name):
        pass

class MockBase:
    def __init__(self, render):
        self.render = render
        self.taskMgr = MockTaskManager()
        self.mouseWatcherNode = None
        self.camNode = None
        self.cam = None

    def accept(self, ev, cb):
        pass

def test_placement_controller_lifecycle():
    gen = CityGenerator(grid_width=8, grid_height=8, block_size=28.0)
    graph = gen.build_road_graph()

    # Import Panda3D NodePath
    from panda3d.core import NodePath
    dummy_render = NodePath("DummyRender")
    mock_base = MockBase(dummy_render)

    confirmed_calls = []
    def on_confirm(tool, payload, pos):
        confirmed_calls.append((tool, payload, pos))

    cancelled_calls = []
    def on_cancel():
        cancelled_calls.append(True)

    ctrl = PlacementController(
        base=mock_base,
        road_graph=graph,
        on_confirm_placement=on_confirm,
        on_cancel_placement=on_cancel
    )

    assert ctrl.active_tool is None
    assert ctrl.preview_root.isHidden()

    # Start placement of BLS
    ctrl.start_placement("DEPLOY_BLS", {"unit_class": "BLS"})
    assert ctrl.active_tool == "DEPLOY_BLS"
    assert not ctrl.preview_root.isHidden()
    assert ctrl.ghost_model is not None

    # Cancel placement
    ctrl.cancel_placement()
    assert ctrl.active_tool is None
    assert ctrl.preview_root.isHidden()
    assert ctrl.selected_edge is None
    assert len(cancelled_calls) == 1

    # Destroy controller
    ctrl.destroy()
