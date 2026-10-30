"""Procedural 3D city generator for LifeLine Dispatch with vibrant isometric styling."""
from __future__ import annotations

import random

from panda3d.core import (
    CardMaker,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    LineSegs,
    NodePath,
    Vec3,
    Vec4,
)

from src.world.road_graph import RoadGraph
from src.world.world_coordinates import CoordinateConverter


def make_box(
    name: str,
    dx: float,
    dy: float,
    dz: float,
    color: Vec4,
    center_bottom: bool = True
) -> NodePath:
    """Create a colored 3D axis-aligned box geometry."""
    vformat = GeomVertexFormat.get_v3n3c4()
    vdata = GeomVertexData(name, vformat, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    col_w = GeomVertexWriter(vdata, "color")

    hx = dx / 2.0
    hy = dy / 2.0
    z_min = 0.0 if center_bottom else -dz / 2.0
    z_max = dz if center_bottom else dz / 2.0

    # 6 faces with normals: front, back, left, right, top, bottom
    faces = [
        # (normal, [corners in CCW order])
        (Vec3(0, 1, 0), [(-hx, hy, z_min), (hx, hy, z_min), (hx, hy, z_max), (-hx, hy, z_max)]),   # +Y
        (Vec3(0, -1, 0), [(hx, -hy, z_min), (-hx, -hy, z_min), (-hx, -hy, z_max), (hx, -hy, z_max)]), # -Y
        (Vec3(-1, 0, 0), [(-hx, -hy, z_min), (-hx, hy, z_min), (-hx, hy, z_max), (-hx, -hy, z_max)]), # -X
        (Vec3(1, 0, 0), [(hx, hy, z_min), (hx, -hy, z_min), (hx, -hy, z_max), (hx, hy, z_max)]),    # +X
        (Vec3(0, 0, 1), [(-hx, -hy, z_max), (hx, -hy, z_max), (hx, hy, z_max), (-hx, hy, z_max)]),  # +Z (top)
        (Vec3(0, 0, -1), [(-hx, hy, z_min), (hx, hy, z_min), (hx, -hy, z_min), (-hx, -hy, z_min)]), # -Z (bottom)
    ]

    triangles = GeomTriangles(Geom.UHStatic)
    idx = 0
    for norm, corners in faces:
        # Subtle face shading
        shade = 1.0
        if norm.z > 0.5:
            shade = 1.08
        elif norm.y > 0.5:
            shade = 0.95
        elif norm.x > 0.5:
            shade = 1.02
        else:
            shade = 0.88
        face_col = Vec4(
            min(1.0, color.x * shade),
            min(1.0, color.y * shade),
            min(1.0, color.z * shade),
            color.w
        )

        for c in corners:
            vertex.addData3(c[0], c[1], c[2])
            col_w.addData4(face_col)
            normal.addData3(norm)

        triangles.addVertices(idx, idx + 1, idx + 2)
        triangles.addVertices(idx, idx + 2, idx + 3)
        idx += 4

    geom = Geom(vdata)
    geom.addPrimitive(triangles)
    node = GeomNode(name)
    node.addGeom(geom)
    return NodePath(node)


class CityGenerator:
    """Generates the 3D procedural isometric city environment and road network."""

    def __init__(
        self,
        grid_width: int = 8,
        grid_height: int = 8,
        block_size: float = 28.0,
        road_width: float = 5.2,
        seed: int = 42
    ):
        self.grid_width = grid_width
        self.grid_height = grid_height
        self.block_size = block_size
        self.road_width = road_width
        self.seed = seed
        self.converter = CoordinateConverter(grid_width, grid_height, block_size)
        self.road_graph = RoadGraph()
        self.hospital_nodes: dict[str, tuple[int, int]] = {
            "HOSP-01": (2, 2),
            "HOSP-02": (5, 5),
            "HOSP-03": (2, 6)
        }
        self.parking_nodes: dict[str, tuple[int, int]] = {
            "DEPOT-01": (1, 1),
            "DEPOT-02": (6, 2),
            "DEPOT-03": (4, 6)
        }

    def build_road_graph(self) -> RoadGraph:
        """Create road nodes at all grid intersections and connect them with edges."""
        graph = self.road_graph

        for gy in range(self.grid_height):
            for gx in range(self.grid_width):
                node_id = self.converter.node_id(gx, gy)
                pos = self.converter.grid_to_world(gx, gy, z=0.05)
                graph.add_node(node_id, gx, gy, pos)

        # Connect horizontal and vertical edges
        for gy in range(self.grid_height):
            for gx in range(self.grid_width):
                curr_id = self.converter.node_id(gx, gy)
                # Right neighbor
                if gx + 1 < self.grid_width:
                    right_id = self.converter.node_id(gx + 1, gy)
                    graph.add_edge(curr_id, right_id, base_speed_mps=15.0, bidirectional=True)
                # Up neighbor
                if gy + 1 < self.grid_height:
                    up_id = self.converter.node_id(gx, gy + 1)
                    graph.add_edge(curr_id, up_id, base_speed_mps=15.0, bidirectional=True)

        return graph

    def generate_city_scene(self, parent_node: NodePath) -> NodePath:
        """Procedurally create and attach all 3D city geometry."""
        city_root = parent_node.attachNewNode("CityRoot")
        rng = random.Random(self.seed)

        # 1. Base terrain ground (warm urban concrete / grass base)
        total_span = (max(self.grid_width, self.grid_height) + 1) * self.block_size
        cm = CardMaker("ground_plane")
        cm.setFrame(-total_span / 2 - 20, total_span / 2 + 20, -total_span / 2 - 20, total_span / 2 + 20)
        ground = city_root.attachNewNode(cm.generate())
        ground.setP(-90)
        ground.setColor(Vec4(0.24, 0.28, 0.32, 1.0))  # Slate dark urban ground

        # 2. Roads and Intersections
        self._generate_roads(city_root)

        # 3. Blocks, Sidewalks, Buildings, Hospitals, Depots, Trees
        self._generate_blocks(city_root, rng)

        return city_root

    def _generate_roads(self, parent: NodePath) -> None:
        """Generate asphalt road strips and intersection markings."""
        asphalt_color = Vec4(0.14, 0.16, 0.19, 1.0)
        stripe_color = Vec4(0.95, 0.85, 0.25, 1.0)

        # Horizontal road strips
        for gy in range(self.grid_height):
            p_start = self.converter.grid_to_world(0, gy, z=0.02)
            p_end = self.converter.grid_to_world(self.grid_width - 1, gy, z=0.02)
            span_x = (p_end[0] - p_start[0]) + self.road_width
            center_x = (p_start[0] + p_end[0]) / 2.0
            center_y = p_start[1]

            road_box = make_box("Road_H", span_x, self.road_width, 0.04, asphalt_color, center_bottom=True)
            road_box.setPos(center_x, center_y, 0.01)
            road_box.reparentTo(parent)

            # Centerline stripes
            stripes = LineSegs("Stripes_H")
            stripes.setColor(stripe_color)
            stripes.setThickness(2.0)
            cur_x = p_start[0]
            while cur_x < p_end[0]:
                stripes.moveTo(cur_x + 1.0, center_y, 0.06)
                stripes.drawTo(min(p_end[0], cur_x + 3.0), center_y, 0.06)
                cur_x += 4.5
            parent.attachNewNode(stripes.create())

        # Vertical road strips
        for gx in range(self.grid_width):
            p_start = self.converter.grid_to_world(gx, 0, z=0.02)
            p_end = self.converter.grid_to_world(gx, self.grid_height - 1, z=0.02)
            span_y = (p_end[1] - p_start[1]) + self.road_width
            center_x = p_start[0]
            center_y = (p_start[1] + p_end[1]) / 2.0

            road_box = make_box("Road_V", self.road_width, span_y, 0.04, asphalt_color, center_bottom=True)
            road_box.setPos(center_x, center_y, 0.01)
            road_box.reparentTo(parent)

            # Centerline stripes
            stripes = LineSegs("Stripes_V")
            stripes.setColor(stripe_color)
            stripes.setThickness(2.0)
            cur_y = p_start[1]
            while cur_y < p_end[1]:
                stripes.moveTo(center_x, cur_y + 1.0, 0.06)
                stripes.drawTo(center_x, min(p_end[1], cur_y + 3.0), 0.06)
                cur_y += 4.5
            parent.attachNewNode(stripes.create())

    def _generate_blocks(self, parent: NodePath, rng: random.Random) -> None:
        """Populate city blocks between roads with sidewalks, buildings, greenery, and facilities."""
        block_inner = self.block_size - self.road_width - 1.2
        sidewalk_color = Vec4(0.76, 0.78, 0.80, 1.0)
        grass_color = Vec4(0.28, 0.62, 0.36, 1.0)
        building_palette = [
            Vec4(0.92, 0.90, 0.86, 1.0), # Warm cream residential
            Vec4(0.25, 0.45, 0.65, 1.0), # Modern blue glass office
            Vec4(0.85, 0.55, 0.35, 1.0), # Terracotta / brick
            Vec4(0.40, 0.68, 0.72, 1.0), # Cyan corporate
            Vec4(0.35, 0.38, 0.45, 1.0), # Steel charcoal tower
            Vec4(0.88, 0.82, 0.70, 1.0), # Sandstone commercial
        ]

        hosp_coords = set(self.hospital_nodes.values())
        parking_coords = set(self.parking_nodes.values())

        for gy in range(self.grid_height - 1):
            for gx in range(self.grid_width - 1):
                # Center of this block in world coords
                p1 = self.converter.grid_to_world(gx, gy)
                p2 = self.converter.grid_to_world(gx + 1, gy + 1)
                bx = (p1[0] + p2[0]) / 2.0
                by = (p1[1] + p2[1]) / 2.0

                # Sidewalk base for the block
                sidewalk = make_box("Sidewalk", block_inner, block_inner, 0.25, sidewalk_color, center_bottom=True)
                sidewalk.setPos(bx, by, 0.02)
                sidewalk.reparentTo(parent)

                # Check designated zones
                if (gx, gy) in hosp_coords:
                    self._create_hospital_building(parent, bx, by, gx, gy)
                elif (gx, gy) in parking_coords:
                    self._create_depot_zone(parent, bx, by)
                else:
                    # Choose block style: Park/Plaza or Buildings
                    roll = rng.random()
                    if roll < 0.18:
                        # Park with lawn, paths, and trees
                        park_lawn = make_box("ParkLawn", block_inner - 2.0, block_inner - 2.0, 0.15, grass_color, center_bottom=True)
                        park_lawn.setPos(bx, by, 0.26)
                        park_lawn.reparentTo(parent)
                        for _ in range(rng.randint(3, 6)):
                            tx = bx + rng.uniform(-block_inner / 3.0, block_inner / 3.0)
                            ty = by + rng.uniform(-block_inner / 3.0, block_inner / 3.0)
                            self._create_tree(parent, tx, ty, rng)
                    else:
                        # 1 to 4 buildings in this block
                        num_buildings = rng.choice([1, 2, 4])
                        if num_buildings == 1:
                            b_width = rng.uniform(block_inner * 0.6, block_inner * 0.8)
                            b_depth = rng.uniform(block_inner * 0.6, block_inner * 0.8)
                            b_height = rng.uniform(7.0, 18.0)
                            b_col = rng.choice(building_palette)
                            b_node = make_box("Tower", b_width, b_depth, b_height, b_col, center_bottom=True)
                            b_node.setPos(bx, by, 0.26)
                            b_node.reparentTo(parent)
                            # Roof mechanical box or rooftop feature
                            roof_box = make_box("RoofHvac", b_width * 0.35, b_depth * 0.35, 1.2, Vec4(0.3, 0.3, 0.35, 1.0), center_bottom=True)
                            roof_box.setPos(bx, by, 0.26 + b_height)
                            roof_box.reparentTo(parent)
                        elif num_buildings == 2:
                            # 2 buildings side-by-side
                            b_w = block_inner * 0.42
                            b_d = block_inner * 0.75
                            for offset in [-block_inner * 0.24, block_inner * 0.24]:
                                b_h = rng.uniform(6.0, 14.0)
                                b_col = rng.choice(building_palette)
                                b = make_box("MidRise", b_w, b_d, b_h, b_col, center_bottom=True)
                                b.setPos(bx + offset, by, 0.26)
                                b.reparentTo(parent)
                        else:
                            # 4 smaller buildings
                            b_sub = block_inner * 0.4
                            for ox in [-block_inner * 0.24, block_inner * 0.24]:
                                for oy in [-block_inner * 0.24, block_inner * 0.24]:
                                    b_h = rng.uniform(5.0, 11.0)
                                    b_col = rng.choice(building_palette)
                                    b = make_box("Building", b_sub, b_sub, b_h, b_col, center_bottom=True)
                                    b.setPos(bx + ox, by + oy, 0.26)
                                    b.reparentTo(parent)

    def _create_hospital_building(self, parent: NodePath, bx: float, by: float, gx: int, gy: int) -> None:
        """Create a prominent, distinct hospital building with 3D emergency red cross and helipad."""
        hosp_root = parent.attachNewNode(f"Hospital_Building_{gx}_{gy}")

        # Main medical tower
        base_h = 10.0
        med_white = Vec4(0.96, 0.96, 0.98, 1.0)
        main_tower = make_box("HospTower", 15.0, 15.0, base_h, med_white, center_bottom=True)
        main_tower.setPos(bx, by, 0.26)
        main_tower.reparentTo(hosp_root)

        # Red accent strip around top
        accent = make_box("HospAccent", 15.2, 15.2, 1.0, Vec4(0.90, 0.20, 0.20, 1.0), center_bottom=True)
        accent.setPos(bx, by, 0.26 + base_h - 1.0)
        accent.reparentTo(hosp_root)

        # Emergency Red Cross on rooftop (+)
        cross_red = Vec4(0.92, 0.15, 0.15, 1.0)
        c1 = make_box("Cross_H", 6.0, 2.0, 1.2, cross_red, center_bottom=True)
        c1.setPos(bx, by, 0.26 + base_h)
        c1.reparentTo(hosp_root)

        c2 = make_box("Cross_V", 2.0, 6.0, 1.2, cross_red, center_bottom=True)
        c2.setPos(bx, by, 0.26 + base_h)
        c2.reparentTo(hosp_root)

        # Ambulance bay canopy
        bay_canopy = make_box("AmbulanceBay", 7.0, 4.0, 0.4, Vec4(0.3, 0.6, 0.85, 1.0), center_bottom=True)
        bay_canopy.setPos(bx, by - 8.5, 3.2)
        bay_canopy.reparentTo(hosp_root)

    def _create_depot_zone(self, parent: NodePath, bx: float, by: float) -> None:
        """Create an EMS depot parking facility."""
        depot_root = parent.attachNewNode("EMS_Depot")
        # Dark tarmac bay
        tarmac = make_box("Tarmac", 16.0, 16.0, 0.1, Vec4(0.18, 0.20, 0.22, 1.0), center_bottom=True)
        tarmac.setPos(bx, by, 0.27)
        tarmac.reparentTo(depot_root)

        # Depot garage building
        garage = make_box("DepotGarage", 14.0, 6.0, 4.5, Vec4(0.4, 0.45, 0.52, 1.0), center_bottom=True)
        garage.setPos(bx, by + 4.0, 0.28)
        garage.reparentTo(depot_root)

        # Parking stripes
        lines = LineSegs("ParkingBays")
        lines.setColor(Vec4(0.95, 0.95, 0.95, 1.0))
        lines.setThickness(2.0)
        for offset_x in [-4.5, -1.5, 1.5, 4.5]:
            lines.moveTo(bx + offset_x, by - 6.0, 0.38)
            lines.drawTo(bx + offset_x, by + 0.5, 0.38)
        depot_root.attachNewNode(lines.create())

    def _create_tree(self, parent: NodePath, x: float, y: float, rng: random.Random) -> None:
        """Create a stylized tree."""
        # Trunk
        trunk_h = rng.uniform(1.2, 1.8)
        trunk = make_box("TreeTrunk", 0.4, 0.4, trunk_h, Vec4(0.45, 0.28, 0.15, 1.0), center_bottom=True)
        trunk.setPos(x, y, 0.26)
        trunk.reparentTo(parent)

        # Foliage canopy (layered green boxes)
        leaf_green = Vec4(0.20, rng.uniform(0.55, 0.72), 0.25, 1.0)
        canopy_size = rng.uniform(1.8, 2.5)
        canopy = make_box("Canopy", canopy_size, canopy_size, rng.uniform(1.8, 2.6), leaf_green, center_bottom=True)
        canopy.setPos(x, y, 0.26 + trunk_h)
        canopy.reparentTo(parent)
