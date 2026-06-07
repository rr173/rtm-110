from typing import List, Tuple, Dict
from dataclasses import dataclass


CARGO_COLORS = [
    "#E74C3C", "#3498DB", "#2ECC71", "#F39C12", "#9B59B6",
    "#1ABC9C", "#E67E22", "#34495E", "#E91E63", "#00BCD4",
    "#8BC34A", "#FF5722", "#795548", "#607D8B", "#9C27B0",
    "#FFC107", "#CDDC39", "#009688", "#673AB7", "#FF9800"
]


@dataclass
class CargoVisual:
    cargo_id: int
    cargo_name: str
    x: float
    y: float
    z: float
    length: float
    width: float
    height: float
    weight: float
    color: str
    label: str


def _generate_cargo_visuals(placed_cargos: List[dict]) -> List[CargoVisual]:
    visuals = []
    for idx, cargo in enumerate(placed_cargos):
        color_idx = idx % len(CARGO_COLORS)
        label = str(idx + 1)
        visuals.append(CargoVisual(
            cargo_id=cargo["cargo_id"],
            cargo_name=cargo["cargo_name"],
            x=cargo["x"],
            y=cargo["y"],
            z=cargo["z"],
            length=cargo["length"],
            width=cargo["width"],
            height=cargo["height"],
            weight=cargo["weight"],
            color=CARGO_COLORS[color_idx],
            label=label
        ))
    return visuals


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def _lighten_color(hex_color: str, factor: float = 0.7) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def _darken_color(hex_color: str, factor: float = 0.3) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    r = int(r * (1 - factor))
    g = int(g * (1 - factor))
    b = int(b * (1 - factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def render_top_view(
    container_length: float,
    container_width: float,
    placed_cargos: List[dict],
    svg_width: int = 600,
    padding: int = 40
) -> str:
    """
    俯视图：从上方看（z轴方向），看到 x-y 平面
    箱门位置：y = container_width 一侧

    Args:
        container_length: 集装箱长度 (x方向)
        container_width: 集装箱宽度 (y方向)
        placed_cargos: 已放置货物列表
        svg_width: SVG宽度
        padding: 内边距
    """
    svg_height = int(svg_width * container_width / container_length + 2 * padding)
    view_width = svg_width - 2 * padding
    view_height = svg_height - 2 * padding

    scale_x = view_width / container_length
    scale_y = view_height / container_width

    visuals = _generate_cargo_visuals(placed_cargos)

    sorted_by_z = sorted(visuals, key=lambda v: v.z)

    svg_parts = []

    svg_parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}">')

    svg_parts.append(f'<rect x="{padding}" y="{padding}" width="{view_width}" height="{view_height}" '
                    f'fill="#f5f5f5" stroke="#333" stroke-width="2"/>')

    door_x1 = padding + view_width * 0.3
    door_x2 = padding + view_width * 0.7
    door_y = padding
    svg_parts.append(f'<line x1="{door_x1}" y1="{door_y}" x2="{door_x2}" y2="{door_y}" '
                    f'stroke="#e74c3c" stroke-width="3" stroke-dasharray="8,4"/>')
    svg_parts.append(f'<text x="{padding + view_width / 2}" y="{padding - 10}" '
                    f'text-anchor="middle" fill="#e74c3c" font-size="12" font-weight="bold">箱门</text>')

    for v in sorted_by_z:
        px = padding + v.x * scale_x
        py = padding + v.y * scale_y
        pw = v.length * scale_x
        ph = v.width * scale_y

        svg_parts.append(f'<rect x="{px:.2f}" y="{py:.2f}" width="{pw:.2f}" height="{ph:.2f}" '
                        f'fill="{v.color}" fill-opacity="0.85" stroke="#333" stroke-width="1"/>')

        if pw > 30 and ph > 20:
            text_x = px + pw / 2
            text_y = py + ph / 2 + 5
            font_size = min(14, min(pw, ph) * 0.4)
            svg_parts.append(f'<text x="{text_x:.2f}" y="{text_y:.2f}" '
                            f'text-anchor="middle" fill="white" font-size="{font_size:.0f}" font-weight="bold">{v.label}</text>')

    svg_parts.append(f'<text x="{padding + view_width / 2}" y="{svg_height - 10}" '
                    f'text-anchor="middle" fill="#666" font-size="11">俯视图 (Top View)</text>')

    svg_parts.append('</svg>')

    return '\n'.join(svg_parts)


def render_front_view(
    container_length: float,
    container_width: float,
    container_height: float,
    placed_cargos: List[dict],
    svg_width: int = 600,
    padding: int = 40
) -> str:
    """
    正视图：从箱门方向看（y轴正方向看向y轴负方向），看到 x-z 平面

    Args:
        container_length: 集装箱长度 (x方向)
        container_width: 集装箱宽度 (y方向)
        container_height: 集装箱高度 (z方向)
        placed_cargos: 已放置货物列表
        svg_width: SVG宽度
        padding: 内边距
    """
    svg_height = int(svg_width * container_height / container_length + 2 * padding)
    view_width = svg_width - 2 * padding
    view_height = svg_height - 2 * padding

    scale_x = view_width / container_length
    scale_z = view_height / container_height

    visuals = _generate_cargo_visuals(placed_cargos)

    sorted_by_y = sorted(visuals, key=lambda v: v.y + v.width, reverse=False)

    svg_parts = []

    svg_parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}">')

    svg_parts.append(f'<rect x="{padding}" y="{padding}" width="{view_width}" height="{view_height}" '
                    f'fill="#f5f5f5" stroke="#333" stroke-width="2"/>')

    svg_parts.append(f'<line x1="{padding + view_width * 0.3}" y1="{padding + view_height}" '
                    f'x2="{padding + view_width * 0.7}" y2="{padding + view_height}" '
                    f'stroke="#e74c3c" stroke-width="3" stroke-dasharray="8,4"/>')

    for v in sorted_by_y:
        px = padding + v.x * scale_x
        pz = padding + view_height - (v.z + v.height) * scale_z
        pw = v.length * scale_x
        ph = v.height * scale_z

        max_y = container_width if container_width > 0 else 1
        depth_factor = 0.3 + 0.7 * (v.y + v.width) / max_y
        r, g, b = _hex_to_rgb(v.color)
        r = int(r * (0.6 + 0.4 * depth_factor))
        g = int(g * (0.6 + 0.4 * depth_factor))
        b = int(b * (0.6 + 0.4 * depth_factor))
        face_color = f"#{r:02x}{g:02x}{b:02x}"

        svg_parts.append(f'<rect x="{px:.2f}" y="{pz:.2f}" width="{pw:.2f}" height="{ph:.2f}" '
                        f'fill="{face_color}" fill-opacity="0.9" stroke="#333" stroke-width="1"/>')

        if pw > 30 and ph > 20:
            text_x = px + pw / 2
            text_y = pz + ph / 2 + 5
            font_size = min(14, min(pw, ph) * 0.4)
            svg_parts.append(f'<text x="{text_x:.2f}" y="{text_y:.2f}" '
                            f'text-anchor="middle" fill="white" font-size="{font_size:.0f}" font-weight="bold">{v.label}</text>')

    svg_parts.append(f'<text x="{padding + view_width / 2}" y="{svg_height - 10}" '
                    f'text-anchor="middle" fill="#666" font-size="11">正视图 (Front View - 从箱门看)</text>')

    svg_parts.append('</svg>')

    return '\n'.join(svg_parts)


def render_side_view(
    container_length: float,
    container_width: float,
    container_height: float,
    placed_cargos: List[dict],
    svg_width: int = 600,
    padding: int = 40
) -> str:
    """
    侧视图：从侧面看（x轴正方向看向x轴负方向），看到 y-z 平面
    箱门在右侧（y = container_width）

    Args:
        container_length: 集装箱长度 (x方向)
        container_width: 集装箱宽度 (y方向)
        container_height: 集装箱高度 (z方向)
        placed_cargos: 已放置货物列表
        svg_width: SVG宽度
        padding: 内边距
    """
    svg_height = int(svg_width * container_height / container_width + 2 * padding)
    view_width = svg_width - 2 * padding
    view_height = svg_height - 2 * padding

    scale_y = view_width / container_width
    scale_z = view_height / container_height

    visuals = _generate_cargo_visuals(placed_cargos)

    sorted_by_x = sorted(visuals, key=lambda v: v.x + v.length, reverse=False)

    svg_parts = []

    svg_parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}">')

    svg_parts.append(f'<rect x="{padding}" y="{padding}" width="{view_width}" height="{view_height}" '
                    f'fill="#f5f5f5" stroke="#333" stroke-width="2"/>')

    door_x = padding + view_width
    svg_parts.append(f'<line x1="{door_x}" y1="{padding}" x2="{door_x}" y2="{padding + view_height}" '
                    f'stroke="#e74c3c" stroke-width="3" stroke-dasharray="8,4"/>')
    svg_parts.append(f'<text x="{svg_width - 5}" y="{padding + 15}" '
                    f'text-anchor="end" fill="#e74c3c" font-size="12" font-weight="bold">箱门</text>')

    for v in sorted_by_x:
        py = padding + v.y * scale_y
        pz = padding + view_height - (v.z + v.height) * scale_z
        pw = v.width * scale_y
        ph = v.height * scale_z

        max_x = container_length if container_length > 0 else 1
        depth_factor = 0.3 + 0.7 * (v.x + v.length) / max_x
        r, g, b = _hex_to_rgb(v.color)
        r = int(r * (0.6 + 0.4 * depth_factor))
        g = int(g * (0.6 + 0.4 * depth_factor))
        b = int(b * (0.6 + 0.4 * depth_factor))
        face_color = f"#{r:02x}{g:02x}{b:02x}"

        svg_parts.append(f'<rect x="{py:.2f}" y="{pz:.2f}" width="{pw:.2f}" height="{ph:.2f}" '
                        f'fill="{face_color}" fill-opacity="0.9" stroke="#333" stroke-width="1"/>')

        if pw > 30 and ph > 20:
            text_x = py + pw / 2
            text_y = pz + ph / 2 + 5
            font_size = min(14, min(pw, ph) * 0.4)
            svg_parts.append(f'<text x="{text_x:.2f}" y="{text_y:.2f}" '
                            f'text-anchor="middle" fill="white" font-size="{font_size:.0f}" font-weight="bold">{v.label}</text>')

    svg_parts.append(f'<text x="{padding + view_width / 2}" y="{svg_height - 10}" '
                    f'text-anchor="middle" fill="#666" font-size="11">侧视图 (Side View)</text>')

    svg_parts.append('</svg>')

    return '\n'.join(svg_parts)


def render_three_views(
    container_length: float,
    container_width: float,
    container_height: float,
    placed_cargos: List[dict],
    view_width: int = 400
) -> Dict[str, str]:
    """
    生成三视图：
    - top_view: 俯视图（x-y平面）
    - front_view: 正视图（从箱门看，x-z平面）
    - side_view: 侧视图（y-z平面）
    """
    top_svg = render_top_view(container_length, container_width, placed_cargos, svg_width=view_width)
    front_svg = render_front_view(container_length, container_width, container_height, placed_cargos, svg_width=view_width)
    side_svg = render_side_view(container_length, container_width, container_height, placed_cargos, svg_width=view_width)

    return {
        "top_view": top_svg,
        "front_view": front_svg,
        "side_view": side_svg
    }
