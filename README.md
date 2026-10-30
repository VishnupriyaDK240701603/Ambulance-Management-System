# Ambulance Management System — 3D Emergency Response Simulator

**Ambulance Management System** (LifeLine Dispatch) is a fully interactive, authoritative 3D emergency medical response and dispatch simulation built with **Python 3** and **Panda3D**.

The simulation features a procedural isometric city, connected navigable road network, capability-aware ambulance fleet (BLS, ALS, CCT), real-time traffic hazards, hospital capacity tracking with bed reservations, traffic police clearance, explainable algorithmic dispatch, and an authoritative state architecture.

---

## 1. Quick Start & Launch

### Prerequisites
- Python 3.10+ (tested on Python 3.11)
- Pip

### Installation
```bash
pip install -r requirements.txt
```

### Running the Application
To run the full 3D interactive application:
```bash
python main.py
```

To run in headless test mode:
```bash
python main.py --headless
```

### Running Automated Tests
```bash
python -m pytest
```

---

## 2. Controls & Operational Shortcuts

### On-Screen View & Camera Adjuster (XYZ)
In the top-right corner of the window, click the blue **`Camera Controls (XYZ)`** button to toggle the on-screen adjustment console:
- **Target X (`X - 10m` / `X + 10m`)**: Nudge focal target left/right along the street grid.
- **Target Y (`Y - 10m` / `Y + 10m`)**: Nudge focal target forward/backward.
- **Target Z (`Z - 5m` / `Z + 5m`)**: Nudge vertical focal height up/down.
- **Distance (`Zoom In` / `Zoom Out`)**: Nudge camera zoom distance.
- **Pitch Angle (`Pitch Down` / `Pitch Up`)**: Tilt between top-down map view and low-angle street perspective.
- **Yaw Rotation (`Turn Left` / `Turn Right`)**: Orbit camera around the focal center in 45° increments.
- **Presets**: Instant buttons for **Isometric 3D**, **Top-Down 2D**, **Street Level**, and **Center (0,0)**.

### Camera Navigation Shortcuts
- **Direct Target X Adjustment**: `J` (Left) / `L` (Right)
- **Direct Target Y Adjustment**: `I` (Forward) / `K` (Backward)
- **Direct Target Z (Height) Adjustment**: `U` (Up) / `O` (Down)
- **Tilt Pitch Adjustment**: `[` (Tilt Down) / `]` (Tilt Up)
- **Pan View**: Arrow Keys or Middle-Mouse Drag
- **Orbit / Rotate View**: `Q` / `E` Keys or Right-Mouse Drag
- **Zoom In / Out**: Mouse Wheel, `+` / `-`, or `PageUp` / `PageDown`
- **Reset Camera**: `Home` Key

### Operational Shortcuts
- `Space`: Pause / Resume simulation
- `1`: Deploy Basic Life Support (BLS) Ambulance
- `2`: Deploy Advanced Life Support (ALS) Ambulance
- `3`: Deploy Critical Care Transport (CCT) Ambulance
- `W / A / S / D`: Steer and drive ambulance in Manual Control Mode

---

## 3. Milestones Implemented & Verified

### Milestone 1 — Foundation & Procedural 3D City
- Procedural warm isometric city generation (`city_generator.py`) with asphalt road ribbons, yellow centerline striping, multi-story buildings, hospitals with 3D rooftop red crosses, and EMS parking depots.
- Fixed top status bar displaying sim time, fleet count, active emergencies, bed capacity, and traffic incidents.
- Fixed bottom command-center dashboard with tabbed operation consoles.

### Milestone 2 — Road Graph & Ambulance Placement
- Connected `RoadGraph` with 64 intersection nodes, legal directed/bidirectional edges, dynamic speeds, and penalties.
- Three distinct ambulance classes: **BLS** (Basic Life Support), **ALS** (Advanced Life Support), **CCT** (Critical Care Transport) with verified capability matrices.
- Initial zero-deployed state strictly enforced.
- Configurable deployment limit (set to **8 ambulances**) and road-placement validation rejecting off-road and overlapping deployments.

### Milestone 3 — Simulation Lifecycle & Patient Machine
- Atomic state machine: `Created` → `Waiting for Dispatch` → `Assigned` → `En Route` → `On Scene` → `Patient Onboard` → `Transporting` → `Hospital Arrival` → `Completed`.
- Start, Pause, Resume, and Reset commands with zero state corruption.

### Milestone 4 — A* Pathfinding & Autonomous/Manual Navigation
- A* search considering road length, speed limits, congestion factors, and closed roads.
- Route waypoints, next-turn guidance, remaining distance, and ETA telemetry.
- Autonomous movement subsystem with smooth heading rotation and inter-vehicle separation.
- Manual driving mode switchable via UI or keyboard (WASD).

### Milestone 5 — Hospital Capacity & Dynamic Selection
- Enforced invariant: `Total Beds = Occupied Beds + Vacant Beds`.
- Atomic bed reservations prevent simultaneous inbound transports from overbooking the last vacant bed.
- Dynamic hospital selection algorithm evaluating route ETA, bed availability ratio, capability match, and switching hysteresis.

### Milestone 6 — Traffic Hazards & Traffic Police
- Road hazard creation: Complete Roadblocks (closed edges), Heavy Congestion (25% speed), and Accidents (+60s penalty).
- Police unit lifecycle: `Dispatched` → `En Route` → `Arrived` → `Clearing` (timed clearance) → `Cleared` (reopening road).
- **Can't Proceed** recovery: evaluates waiting for police clearance vs. finding an alternative detour route.

### Milestone 7 — Explainable AI ("See Reason")
- Structured `DecisionRecord` engine capturing timestamp, candidate scores, metrics breakdown, and explicit rejection reasons.
- Dedicated `DecisionInspectorModal` for visual audit of automated dispatch, hospital selection, and route recovery choices.

### Milestone 8 — Hardening & Integration Readiness
- 56 automated pytest tests passing with 100% success rate.
- `ExternalDataProvider` for ingesting external backend feeds (emergencies, traffic alerts, bed updates) with safe schema validation.

---

## 4. Architecture & Project Layout

```
ambulance_management_system/
    main.py                       # Main application entry point
    requirements.txt              # Pinned dependencies (Panda3D, pytest)
    pytest.ini                    # Test runner configuration
    config/
        simulation.json           # Timestep, hospital profiles, capability matrices, algorithm weights
        city.json                 # City grid dimensions, blocks, hospital/depot locations
    src/
        app/
            application.py        # ShowBase application wiring renderer, state, and UI
        world/
            world_coordinates.py  # Grid-to-world 3D coordinate converter
            road_graph.py         # Navigable graph, edge costs, road closures, congestion
            city_generator.py     # Procedural 3D isometric city geometry builder
            camera_controller.py  # Smooth RTS/isometric orbital camera
            visual_entity_manager.py # 3D models for vehicles, beacons, roadblocks, route ribbons
        simulation/
            simulation_state.py   # Authoritative single source of truth
            simulation_engine.py  # Fixed timestep loop and command processor
            commands.py           # Validated state mutation commands
            events.py             # Event definitions and observer payloads
            event_log.py          # Centralized event history log
            validators.py         # Scenario and deployment validation rules
        models/
            ambulance.py          # BLS, ALS, CCT models and capability matrices
            emergency.py          # Incident lifecycle state machine
            hospital.py           # Hospital model with bed capacity invariants & reservations
            police_unit.py        # Traffic police unit model
            road_incident.py      # Roadblock, congestion, and accident models
            route.py              # Active route and waypoint telemetry
            decision_record.py    # Structured explainable AI decision audit records
        ui/
            top_status_bar.py     # Fixed top telemetry bar with Start/Pause/Reset controls
            bottom_dashboard.py   # Fixed bottom tabbed command center dashboard
            notifications.py      # Banner and toast alert system
            placement_controller.py # 3D click-to-place raycasting and ghost preview
            route_map_modal.py    # 2D GPS navigation and route map overlay
            decision_modal.py     # Explainable AI decision audit inspector
            view_adjuster.py      # Camera XYZ HUD adjustment widget
    tests/
        test_ambulance_placement.py # Deployment limits, collision prevention, capability matrix tests
        test_app_smoke.py         # Panda3D full application smoke tests
        test_astar.py             # A* shortest path & closure detour tests
        test_bed_capacity.py      # Invariants and reservation mechanics tests
        test_data_provider.py     # External telemetry ingestion & schema tests
        test_dispatch.py          # Joint multi-incident optimal dispatch tests
        test_explainable_ai.py    # Explainable AI decision record audit tests
        test_hospital_selection.py # Hospital specialization and capacity selection tests
        test_manual_driving.py    # WASD manual steering and dynamic rerouting tests
        test_patient_lifecycle.py # Patient mission state machine tests
        test_placement_controller.py # 3D raycasting and placement preview tests
        test_police_system.py     # Police clearance timeout & notification tests
        test_road_graph.py        # Road graph connectivity and closure tests
        test_simulation_lifecycle.py # Start, Pause, Resume, Reset lifecycle tests
        test_traffic_recovery.py  # Traffic recovery and detour vs wait tests
```
