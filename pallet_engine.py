# Fichier: pallet_engine.py

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
import random
import time
import copy
import json
import os
from ortools.sat.python import cp_model


# --- STRUCTURES DE DONNÉES ---
@dataclass
class Box:
    """Représente un seul carton avec sa position et ses dimensions."""
    idx: int
    x: int
    y: int
    w: int
    h: int
    rot: int


# --- LOGIQUE DE CALCUL DE BASE ---

def solve_layer(L: int, W: int, l: int, w: int, *, time_limit: int, workers: int, seed: int | None = None,
                obstacle: Optional[Dict[str, int]] = None) -> List[Box]:
    """
    Utilise le solveur CP-SAT pour trouver un agencement optimal de cartons sur une surface.
    """
    max_n = (L * W) // (l * w)
    m = cp_model.CpModel()
    x0s, y0s, x1s, y1s, place, rot, u0, u1 = [], [], [], [], [], [], [], []
    xi0, yi0, xi1, yi1 = [], [], [], []

    for i in range(max_n):
        p = m.NewBoolVar(f"pl[{i}]")
        r = m.NewBoolVar(f"rot[{i}]")
        a0 = m.NewBoolVar(f"u0[{i}]")
        a1 = m.NewBoolVar(f"u1[{i}]")
        place.append(p)
        rot.append(r)
        u0.append(a0)
        u1.append(a1)
        m.Add(a0 + a1 == p)
        m.Add(a1 == r)

        xs0 = m.NewIntVar(0, L - l, "")
        ys0 = m.NewIntVar(0, W - w, "")
        xi0.append(m.NewOptionalIntervalVar(xs0, l, m.NewIntVar(l, L, ""), a0, ""))
        yi0.append(m.NewOptionalIntervalVar(ys0, w, m.NewIntVar(w, W, ""), a0, ""))
        x0s.append(xs0)
        y0s.append(ys0)

        xs1 = m.NewIntVar(0, L - w, "")
        ys1 = m.NewIntVar(0, W - l, "")
        xi1.append(m.NewOptionalIntervalVar(xs1, w, m.NewIntVar(w, L, ""), a1, ""))
        yi1.append(m.NewOptionalIntervalVar(ys1, l, m.NewIntVar(l, W, ""), a1, ""))
        x1s.append(xs1)
        y1s.append(ys1)

        if obstacle:
            ox, oy, ow, oh = obstacle['x'], obstacle['y'], obstacle['w'], obstacle['h']
            b_l0 = m.NewBoolVar('');
            m.Add(xs0 + l <= ox).OnlyEnforceIf(b_l0)
            b_r0 = m.NewBoolVar('');
            m.Add(xs0 >= ox + ow).OnlyEnforceIf(b_r0)
            b_b0 = m.NewBoolVar('');
            m.Add(ys0 + w <= oy).OnlyEnforceIf(b_b0)
            b_t0 = m.NewBoolVar('');
            m.Add(ys0 >= oy + oh).OnlyEnforceIf(b_t0)
            m.AddBoolOr([b_l0, b_r0, b_b0, b_t0]).OnlyEnforceIf(a0)

            b_l1 = m.NewBoolVar('');
            m.Add(xs1 + w <= ox).OnlyEnforceIf(b_l1)
            b_r1 = m.NewBoolVar('');
            m.Add(xs1 >= ox + ow).OnlyEnforceIf(b_r1)
            b_b1 = m.NewBoolVar('');
            m.Add(ys1 + l <= oy).OnlyEnforceIf(b_b1)
            b_t1 = m.NewBoolVar('');
            m.Add(ys1 >= oy + oh).OnlyEnforceIf(b_t1)
            m.AddBoolOr([b_l1, b_r1, b_b1, b_t1]).OnlyEnforceIf(a1)

    m.AddNoOverlap2D(xi0 + xi1, yi0 + yi1)
    m.Maximize(sum(place))

    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = float(time_limit)
    s.parameters.num_search_workers = int(workers)
    if seed is not None:
        s.parameters.random_seed = seed

    s.Solve(m)
    layout = []
    for i in range(max_n):
        if s.Value(place[i]):
            is_rot = s.Value(rot[i])
            layout.append(
                Box(i, s.Value(x1s[i] if is_rot else x0s[i]), s.Value(y1s[i] if is_rot else y0s[i]), w if is_rot else l,
                    l if is_rot else w, 90 if is_rot else 0))
    return layout


def compact_layer(layer: List[Box]) -> List[Box]:
    """Tasse les cartons en simulant la gravité vers le bas et la gauche."""
    if not layer: return []

    # Compactage vertical
    sorted_by_y = sorted(layer, key=lambda b: b.y)
    for i, box in enumerate(sorted_by_y):
        max_y_support = 0
        for j in range(i):
            other = sorted_by_y[j]
            if (box.x < other.x + other.w) and (box.x + box.w > other.x):
                max_y_support = max(max_y_support, other.y + other.h)
        box.y = max_y_support

    # Compactage horizontal
    sorted_by_x = sorted(layer, key=lambda b: b.x)
    for i, box in enumerate(sorted_by_x):
        max_x_support = 0
        for j in range(i):
            other = sorted_by_x[j]
            if (box.y < other.y + other.h) and (box.y + box.h > other.y):
                max_x_support = max(max_x_support, other.x + other.w)
        box.x = max_x_support
    return layer


def find_compacted_layer(L: int, W: int, l: int, w: int, *, time_limit: int, workers: int,
                         obstacle: Optional[Dict[str, int]] = None) -> List[Box]:
    """Trouve une solution et la compacte pour la rendre stable."""
    layer = solve_layer(L, W, l, w, time_limit=time_limit, workers=workers, seed=random.randint(0, 999999),
                        obstacle=obstacle)
    return compact_layer(layer) if layer else []


# --- LOGIQUE DE STABILITÉ ET SCORING ---

def is_box_laterally_supported(box_to_check: Box, layer: List[Box], min_neighbors: int = 3) -> bool:
    """Vérifie si un carton est entouré par au moins `min_neighbors` voisins."""
    neighbor_count = 0
    TOLERANCE = 1.0
    for other_box in layer:
        if box_to_check.idx == other_box.idx: continue

        is_vertical_neighbor = abs((box_to_check.y + box_to_check.h) - other_box.y) < TOLERANCE or abs(
            box_to_check.y - (other_box.y + other_box.h)) < TOLERANCE
        if is_vertical_neighbor and (
                box_to_check.x < other_box.x + other_box.w and box_to_check.x + box_to_check.w > other_box.x):
            neighbor_count += 1
            continue

        is_horizontal_neighbor = abs(box_to_check.x - (other_box.x + other_box.w)) < TOLERANCE or abs(
            (box_to_check.x + box_to_check.w) - other_box.x) < TOLERANCE
        if is_horizontal_neighbor and (
                box_to_check.y < other_box.y + other_box.h and box_to_check.y + box_to_check.h > other_box.y):
            neighbor_count += 1

    return neighbor_count >= min_neighbors


def calculate_layer_stability_score(base_layer: List[Box], upper_layer: List[Box]) -> float:
    """Calcule un score de qualité pour une couche en fonction de son support."""
    if not upper_layer: return -float('inf')

    score = len(upper_layer) * 1000.0
    unstable_columns = 0
    total_support_ratio_sum = 0.0

    for upper_box in upper_layer:
        upper_box_area = upper_box.w * upper_box.h
        if upper_box_area == 0: continue

        total_supported_area = 0.0
        is_column = False

        for base_box in base_layer:
            overlap_x = max(0, min(upper_box.x + upper_box.w, base_box.x + base_box.w) - max(upper_box.x, base_box.x))
            overlap_y = max(0, min(upper_box.y + upper_box.h, base_box.y + base_box.h) - max(upper_box.y, base_box.y))
            overlap_area = overlap_x * overlap_y

            if (overlap_area / upper_box_area) > 0.90:
                is_column = True

            total_supported_area += overlap_area

        if is_column and not is_box_laterally_supported(upper_box, upper_layer):
            unstable_columns += 1

        total_support_ratio_sum += total_supported_area / upper_box_area

    score -= unstable_columns * 500.0
    score += (total_support_ratio_sum / len(upper_layer)) * 100.0

    return score


# --- FONCTIONS UTILITAIRES POUR LE FORMATAGE ---

def determine_label_face(box: Box, layer: List[Box], L: int, W: int) -> int:
    """Détermine la face physiquement accessible. 1:Bas, 2:Droite, 3:Haut, 4:Gauche."""
    TOL = 1.0
    faces = {1: True, 2: True, 3: True, 4: True}

    for other in layer:
        if box.idx == other.idx: continue
        if abs(other.y + other.h - box.y) < TOL and max(box.x, other.x) < min(box.x + box.w, other.x + other.w): faces[
            1] = False
        if abs(other.x - (box.x + box.w)) < TOL and max(box.y, other.y) < min(box.y + box.h, other.y + other.h): faces[
            2] = False
        if abs(other.y - (box.y + box.h)) < TOL and max(box.x, other.x) < min(box.x + box.w, other.x + other.w): faces[
            3] = False
        if abs(other.x + other.w - box.x) < TOL and max(box.y, other.y) < min(box.y + box.h, other.y + other.h): faces[
            4] = False

    if box.y < TOL: faces[1] = False
    if abs(box.x + box.w - L) < TOL: faces[2] = False
    if abs(box.y + box.h - W) < TOL: faces[3] = False
    if box.x < TOL: faces[4] = False

    return next((face for face, visible in faces.items() if visible), 1)


def format_layer_for_json(layer: List[Box], L: int, W: int) -> List[Dict[str, Any]]:
    """Formate une couche de cartons pour la sortie JSON, incluant l'ordre de pose."""
    order_map = {b.idx: i + 1 for i, b in enumerate(sorted(layer, key=lambda b: (b.y, b.x)))}

    output_boxes = []
    for box in layer:
        output_boxes.append({
            "placement_order": order_map[box.idx],
            "x": box.x, "y": box.y,
            "width": box.w, "height": box.h,
            "rotation": box.rot,
            "label_face": determine_label_face(box, layer, L, W)
        })
    return sorted(output_boxes, key=lambda b: b['placement_order'])


# --- FONCTION PRINCIPALE DU MOTEUR ---

def generate_pallet_solutions(pallet_dims: Dict[str, int], box_dims: Dict[str, int], num_solutions: int,
                              workers: int = 4) -> Dict[str, Any]:
    """
    Fonction principale du moteur. Génère plusieurs templates de palettisation.
    Cette fonction est PUREMENT calculatoire et n'a pas de connaissance du cache.
    """
    L, W = pallet_dims['L'], pallet_dims['W']
    l, w = box_dims['l'], box_dims['w']

    print("ENGINE: Démarrage de la génération de solutions...")
    start_time = time.time()

    layer1 = find_compacted_layer(L, W, l, w, time_limit=10, workers=workers)
    if not layer1:
        return {"error": "Impossible de générer la couche de base."}

    templates = []
    found_patterns = set()
    # On fait plus de tentatives pour avoir plus de choix uniques (par ex, 5 fois plus)
    for i in range(num_solutions * 5):
        if len(templates) >= num_solutions: break

        print(f"ENGINE: Recherche du candidat #{len(templates) + 1}...")
        obstacle = {'x': random.randint(l // 4, l), 'y': random.randint(w // 4, w), 'w': 1, 'h': 1}
        layer2 = find_compacted_layer(L, W, l, w, time_limit=5, workers=workers, obstacle=obstacle)

        if not layer2: continue

        pattern_signature = tuple(sorted([(b.x, b.y, b.w, b.h) for b in layer2]))
        if pattern_signature in found_patterns: continue
        found_patterns.add(pattern_signature)

        score = calculate_layer_stability_score(layer1, layer2)

        # Le formatage JSON est crucial pour la BDD et le sender
        template_data = {
            "score": score,
            "layer1_box_count": len(layer1),
            "layer2_box_count": len(layer2),
            "layer1": format_layer_for_json(layer1, L, W),
            "layer2": format_layer_for_json(layer2, L, W)
        }
        templates.append(template_data)

    # Trier les templates trouvés par score (du meilleur au moins bon)
    sorted_templates = sorted(templates, key=lambda t: t['score'], reverse=True)

    final_output = {
        "generation_info": {
            "duration_seconds": round(time.time() - start_time, 2),
            "num_solutions_found": len(sorted_templates)
        },
        "pallet_dimensions": pallet_dims,
        "box_dimensions": box_dims,
        "templates": [
            # L'ID du template sera géré par la base de données
            template_data for template_data in sorted_templates
        ]
    }

    print(f"ENGINE: Génération terminée. {len(sorted_templates)} solutions uniques trouvées.")
    return final_output