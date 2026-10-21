#!/usr/bin/env python3
"""Bounded source -> model -> formal-script gate. No provider calls or publication.

This is not a scientific oracle: it solves declared linear circuits and checks
declared algebra under explicit assumptions. Source interpretation, device-model
adequacy, and scientific/teaching approval remain separate review obligations.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import sympy as sp
from jsonschema import Draft202012Validator

VERSION = "source-model-gate-1"
ZERO = (sp.Rational(0),) * 5  # kg, m, s, A, K
UNITS = {
    "1": ZERO, "s": (0, 0, 1, 0, 0), "Hz": (0, 0, -1, 0, 0),
    "rad/s": (0, 0, -1, 0, 0), "A": (0, 0, 0, 1, 0),
    "V": (1, 2, -3, -1, 0), "ohm": (1, 2, -3, -2, 0),
    "S": (-1, -2, 3, 2, 0), "F": (-1, -2, 4, 2, 0),
    "K": (0, 0, 0, 0, 1), "J/K": (1, 2, -2, 0, -1),
    "C": (0, 0, 1, 1, 0), "A2/Hz": (0, 0, 1, 2, 0),
    "A2": (0, 0, 0, 2, 0), "V2/Hz": (2, 4, -5, -2, 0),
}


class GateError(ValueError):
    def __init__(self, code, location, message):
        super().__init__(f"{code} at {location}: {message}")
        self.code, self.location, self.message = code, location, message

    def record(self):
        return {"code": self.code, "location": self.location, "message": self.message}


def need(ok, code, location, message):
    if not ok:
        raise GateError(code, location, message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unit(name, loc):
    need(name in UNITS, "UNKNOWN_UNIT", loc, f"Unsupported unit {name}")
    return tuple(sp.Rational(x) for x in UNITS[name])


def keys(row, required, optional, loc):
    need(isinstance(row, dict), "SCHEMA", loc, "Expected object")
    need(set(required) <= row.keys() <= set(required) | set(optional), "SCHEMA", loc,
         f"Missing or unsupported fields: required={required}, got={sorted(row)}")


def indexed(rows, loc):
    need(isinstance(rows, list), "SCHEMA", loc, "Expected list")
    out = {}
    for row in rows:
        need(isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"],
             "SCHEMA", loc, "Each row needs a non-empty stable id")
        need(row["id"] not in out, "DUPLICATE_ID", loc, row["id"])
        out[row["id"]] = row
    return out


def refs(values, targets, loc, *, nonempty=False):
    need(isinstance(values, list) and all(isinstance(v, str) for v in values),
         "SCHEMA", loc, "References must be a list of IDs")
    need(not nonempty or values, "MISSING_REFERENCE", loc, "At least one reference required")
    need(len(values) == len(set(values)), "DUPLICATE_REFERENCE", loc, "Duplicate references")
    for value in values:
        need(value in targets, "DANGLING_REFERENCE", loc, value)


def safe_path(root, relative, loc):
    need(isinstance(relative, str) and relative, "SOURCE_PATH", loc, "Missing path")
    path = (root / relative).resolve()
    need(path.is_relative_to(root.resolve()), "SOURCE_PATH", loc, "Path escapes evidence root")
    need(path.is_file(), "SOURCE_MISSING", loc, relative)
    return path


class Expression:
    """Small AST grammar; never eval/sympify arbitrary input. Dimensions are exact."""
    def __init__(self, symbols, dimensions):
        self.symbols, self.dimensions = symbols, dimensions

    def parse(self, text, loc):
        need(isinstance(text, str) and len(text) <= 3000, "EXPRESSION", loc, "Invalid expression")
        try:
            tree = ast.parse(text, mode="eval")
        except SyntaxError as exc:
            raise GateError("EXPRESSION", loc, str(exc)) from exc
        need(sum(1 for _ in ast.walk(tree)) <= 500, "EXPRESSION", loc, "Expression too large")
        return self._node(tree.body, loc)

    def _node(self, node, loc):
        if isinstance(node, ast.Name):
            if node.id in {"pi", "I"}:
                return {"pi": sp.pi, "I": sp.I}[node.id], ZERO
            need(node.id in self.symbols, "UNKNOWN_SYMBOL", loc, node.id)
            return self.symbols[node.id], self.dimensions[node.id]
        if isinstance(node, ast.Constant):
            need(type(node.value) in {int, float} and math.isfinite(node.value),
                 "EXPRESSION", loc, "Only finite numeric literals allowed")
            value = sp.Rational(str(node.value))
            return value, None if value == 0 else ZERO
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value, dim = self._node(node.operand, loc)
            return value if isinstance(node.op, ast.UAdd) else -value, dim
        if isinstance(node, ast.Call):
            need(isinstance(node.func, ast.Name) and node.func.id == "sqrt" and
                 len(node.args) == 1 and not node.keywords, "EXPRESSION", loc, "Only sqrt is supported")
            value, dim = self._node(node.args[0], loc)
            return sp.sqrt(value), None if dim is None else tuple(v/2 for v in dim)
        need(isinstance(node, ast.BinOp), "EXPRESSION", loc, "Unsupported syntax")
        a, da = self._node(node.left, loc)
        b, db = self._node(node.right, loc)
        if isinstance(node.op, (ast.Add, ast.Sub)):
            need(da is None or db is None or da == db, "UNIT_MISMATCH", loc,
                 f"Cannot add dimensions {da} and {db}")
            return a+b if isinstance(node.op, ast.Add) else a-b, da if db is None else db
        if isinstance(node.op, (ast.Mult, ast.Div)):
            need(not isinstance(node.op, ast.Div) or b != 0, "EXPRESSION", loc, "Division by zero")
            if isinstance(node.op, ast.Div) and not b.has(self.symbols["s"]):
                need(b.is_nonzero is True, "EXPRESSION_DOMAIN", loc,
                     "Parameter denominator must be provably nonzero over its declared domain before cancellation")
            sign = 1 if isinstance(node.op, ast.Mult) else -1
            dim = None if da is None or db is None else tuple(x+sign*y for x, y in zip(da, db))
            return a*b if sign == 1 else a/b, dim
        if isinstance(node.op, ast.Pow):
            need(db == ZERO and b.is_Rational and abs(b) <= 12, "EXPRESSION", loc,
                 "Only bounded rational constant exponents supported")
            if b < 0 and not a.has(self.symbols["s"]):
                need(a.is_nonzero is True, "EXPRESSION_DOMAIN", loc,
                     "Negative powers require a provably nonzero base over the declared domain")
            return a**b, None if da is None else tuple(v*b for v in da)
        raise GateError("EXPRESSION", loc, "Unsupported operator")


def model_context(model, loc):
    parameters = indexed(model["parameters"], loc+".parameters")
    need("s" not in parameters and "pi" not in parameters and "I" not in parameters,
         "SCHEMA", loc, "Reserved parameter name")
    symbols = {"s": sp.Symbol("s")}
    dimensions = {"s": unit("Hz", loc)}
    samples = {}
    for name, p in parameters.items():
        keys(p, ["id", "unit", "domain", "sample", "meaning"], [], loc+".parameters."+name)
        need(name.isidentifier(), "SCHEMA", loc, "Parameter ID must be an identifier")
        need(p["domain"] in {"positive", "nonnegative", "real"}, "SCHEMA", loc, "Unknown domain")
        need(type(p["sample"]) in {int, float} and math.isfinite(p["sample"]),
             "NUMERICAL_DOMAIN", loc, "Invalid sample")
        need(p["domain"] == "real" or p["sample"] >= 0, "NUMERICAL_DOMAIN", loc, name)
        need(p["domain"] != "positive" or p["sample"] > 0, "NUMERICAL_DOMAIN", loc, name)
        symbols[name] = sp.Symbol(name, **{p["domain"]: True})
        dimensions[name] = unit(p["unit"], loc)
        samples[symbols[name]] = sp.Rational(str(p["sample"]))
    excitation = model["excitation"]
    keys(excitation, ["symbol", "from", "to", "unit"], [], loc+".excitation")
    name = excitation["symbol"]
    need(name not in symbols and name.isidentifier(), "SCHEMA", loc, "Invalid input symbol")
    need(excitation["unit"] == "A", "UNSUPPORTED_MODEL", loc, "Only current excitation supported")
    symbols[name] = sp.Symbol(name, real=True)
    dimensions[name] = unit("A", loc)
    return Expression(symbols, dimensions), samples


def solve_mna(model, expr, loc):
    nodes = model["nodes"]
    need(isinstance(nodes, list) and len(nodes) == len(set(nodes)) and 1 < len(nodes) <= 8,
         "TOPOLOGY", loc, "Need 2–8 distinct nodes")
    ref = model["reference_node"]
    need(ref in nodes, "TOPOLOGY", loc, "Missing reference node")
    need(all(isinstance(n, str) and n.isidentifier() for n in nodes), "TOPOLOGY", loc, "Invalid node ID")
    voltages = {n: sp.Symbol("V_"+n) for n in nodes if n != ref}
    voltages[ref] = sp.S.Zero
    equations = {n: sp.S.Zero for n in nodes if n != ref}
    constraints, extra = [], []
    components = indexed(model["components"], loc+".components")
    need(0 < len(components) <= 16, "UNSUPPORTED_MODEL", loc, "Need 1–16 components")

    def stamp(p, n, current):
        need(p in nodes and n in nodes and p != n, "TOPOLOGY", loc, f"Invalid branch {p} -> {n}")
        if p != ref: equations[p] += current
        if n != ref: equations[n] -= current

    s = expr.symbols["s"]
    for cid, c in components.items():
        cloc = loc+".components."+cid
        keys(c, ["id", "kind", "from", "to", "value"], ["control_from", "control_to"], cloc)
        need(c["from"] in nodes and c["to"] in nodes, "TOPOLOGY", cloc, "Dangling terminal")
        val, dim = expr.parse(c["value"], cloc)
        need(expr.symbols[model["excitation"]["symbol"]] not in val.free_symbols,
             "NONLINEAR_MODEL", cloc, "Component coefficient cannot depend on excitation")
        p, n = c["from"], c["to"]
        voltage = voltages[p]-voltages[n]
        if c["kind"] in {"R", "C"}:
            need(set(c) == {"id", "kind", "from", "to", "value"}, "SCHEMA", cloc, "Unexpected terminals")
            need(dim == unit("ohm" if c["kind"] == "R" else "F", cloc), "UNIT_MISMATCH", cloc, "Component unit")
            need(val.is_positive, "MODEL_DOMAIN", cloc, "Passive component must be provably positive")
            stamp(p, n, voltage/val if c["kind"] == "R" else s*val*voltage)
        elif c["kind"] in {"VCCS", "VCVS"}:
            need(c.get("control_from") in nodes and c.get("control_to") in nodes,
                 "TOPOLOGY", cloc, "Dangling control terminal")
            need(dim == unit("S" if c["kind"] == "VCCS" else "1", cloc), "UNIT_MISMATCH", cloc, "Controlled-source unit")
            control = voltages[c["control_from"]]-voltages[c["control_to"]]
            if c["kind"] == "VCCS":
                stamp(p, n, val*control)
            else:
                current = sp.Symbol("J_"+cid)
                extra.append(current)
                stamp(p, n, current)
                constraints.append(voltage-val*control)
        else:
            raise GateError("UNSUPPORTED_MODEL", cloc, c["kind"])
    ex = model["excitation"]
    stamp(ex["from"], ex["to"], expr.symbols[ex["symbol"]])
    unknowns = [voltages[n] for n in nodes if n != ref] + extra
    equations = list(equations.values()) + constraints
    try:
        solutions = sp.solve(equations, unknowns, dict=True)
    except Exception as exc:
        raise GateError("MNA_UNSOLVED", loc, str(exc)) from exc
    need(len(solutions) == 1 and all(v in solutions[0] for v in unknowns),
         "MNA_UNSOLVED", loc, "No unique solution")
    solution = solutions[0]
    excitation_symbol = expr.symbols[model["excitation"]["symbol"]]
    need(all(sp.diff(solution[v], excitation_symbol, 2) == 0 and
             sp.simplify(solution[v].subs(excitation_symbol, 0)) == 0 for v in unknowns),
         "NONLINEAR_MODEL", loc, "Only linear homogeneous responses to the declared excitation are supported")
    residuals = [sp.simplify(e.subs(solution)) for e in equations]
    need(all(r == 0 for r in residuals), "MNA_RESIDUAL", loc, "KCL or source constraint did not close")
    transfers = {n: sp.factor(solution[v]/expr.symbols[ex["symbol"]]) for n, v in voltages.items() if n != ref}
    return transfers, {"equations": [str(e) for e in equations],
                       "unknowns": [str(u) for u in unknowns],
                       "solution": {str(k): str(v) for k, v in solution.items()},
                       "residuals": [str(r) for r in residuals]}


def expected_formula(formula, transfers, expr, model, facts, loc):
    method = formula["derivation"]
    need(isinstance(method, dict) and "operation" in method, "SCHEMA", loc, "Missing derivation operation")
    operation = method["operation"]
    need(method.get("node") in transfers, "DANGLING_REFERENCE", loc, "Unknown output node")
    transfer = transfers[method["node"]]
    s = expr.symbols["s"]
    if operation == "mna_transfer":
        keys(method, ["operation", "node"], ["substitute", "negate"], loc)
        result = transfer
        for name, value in method.get("substitute", {}).items():
            need(name == "s" and value == "0", "UNSUPPORTED_SUBSTITUTION", loc,
                 "Only DC s=0 evaluation is supported; use an explicit zero-parameter limit for model limits")
            val, dim = expr.parse(value, loc)
            need(dim is None or dim == expr.dimensions[name], "UNIT_MISMATCH", loc, name)
            result = result.subs(expr.symbols[name], val)
        if method.get("negate", False): result = -result
        return sp.simplify(result)
    if operation == "mna_zero_limit":
        keys(method, ["operation", "node", "parameter"], [], loc)
        name = method["parameter"]
        parameters = {p["id"]: p for p in model["parameters"]}
        need(name in parameters and parameters[name]["domain"] == "positive", "MODEL_DOMAIN", loc,
             "Zero boundary limit needs a positive declared model parameter")
        result = sp.limit(transfer, expr.symbols[name], 0, dir="+")
        need(not result.has(sp.oo, -sp.oo, sp.zoo, sp.nan), "MODEL_LIMIT", loc, "Limit is not finite")
        return result
    if operation in {"second_order_omega0", "second_order_Q"}:
        keys(method, ["operation", "node"], [], loc)
        need(formula["unit"] == ("rad/s" if operation == "second_order_omega0" else "1"),
             "FREQUENCY_CONVENTION", loc, "Natural angular frequency is rad/s; Q is dimensionless")
        num, den = sp.fraction(sp.cancel(transfer))
        poly = sp.Poly(den, s)
        need(poly.degree() == 2 and not num.has(s), "MODEL_ORDER", loc,
             "Requires a second-order all-pole voltage/current transfer")
        c0, c1, c2 = [poly.nth(i) for i in range(3)]
        need(all(v.is_positive for v in [c0, c1, c2]), "MODEL_DOMAIN", loc, "Coefficients not positive")
        return sp.sqrt(c0/c2) if operation == "second_order_omega0" else sp.sqrt(c0*c2)/c1
    if operation == "noise_projection":
        keys(method, ["operation", "node", "transconductance", "intrinsic_psd", "frequency"], ["additive_psds"], loc)
        gm, gdim = expr.parse(method["transconductance"], loc)
        intrinsic, pdim = expr.parse(method["intrinsic_psd"], loc)
        freq, fdim = expr.parse(method["frequency"], loc)
        needed_facts = {"one_sided_per_hz_psd", "unilateral_voltage_noise_projection",
                        "classical_white_noise_laws", "uncorrelated_sources"}
        need(model["role"] == "unilateral_noise_null_network" and
             all(facts.get(k) is True and formula["requirements"].get(k) is True for k in needed_facts),
             "NOISE_MODEL_SCOPE", loc, "Restricted unilateral null-network projection and all noise assumptions required")
        parameters = {p["id"]: p for p in model["parameters"]}
        need(method["transconductance"] in parameters and parameters[method["transconductance"]]["unit"] == "S" and
             parameters[method["transconductance"]]["domain"] == "positive", "NOISE_MODEL_SCOPE", loc,
             "Transconductance must be a constant positive parameter measured in siemens")
        need(method["frequency"] in parameters and parameters[method["frequency"]]["unit"] == "Hz" and
             parameters[method["frequency"]]["domain"] == "nonnegative", "NOISE_FREQUENCY_CONVENTION", loc,
             "Frequency must be a nonnegative parameter explicitly measured in Hz, not rad/s")
        need(len(model["nodes"]) == 2 and model["excitation"]["to"] == method["node"] and
             model["excitation"]["from"] == model["reference_node"] and
             len(model["components"]) == 2 and {c["kind"] for c in model["components"]} == {"R", "C"} and
             all({c["from"], c["to"]} == {method["node"], model["reference_node"]} for c in model["components"]),
             "NOISE_MODEL_SCOPE", loc, "Only a parallel R/C output-null network is supported")
        need(gdim == unit("S", loc) and pdim == unit("A2/Hz", loc) and fdim == unit("Hz", loc),
             "UNIT_MISMATCH", loc, "Noise projection units")
        need(gm.is_positive is True and intrinsic.is_nonnegative is True and intrinsic.is_real is True,
             "NOISE_LAW_DOMAIN", loc, "Each adopted noise PSD must be independently real and nonnegative")
        need(not intrinsic.has(freq, s), "NOISE_LAW_DOMAIN", loc,
             "The supported adopted white source law cannot depend on frequency or s")
        h = sp.simplify(1/(gm*transfer)).subs(s, sp.I*2*sp.pi*freq)
        result = h*sp.conjugate(h)*intrinsic
        for law in method.get("additive_psds", []):
            term, dimension = expr.parse(law, loc)
            need(dimension == unit("A2/Hz", loc), "UNIT_MISMATCH", loc, "Additive noise law unit")
            need(term.is_nonnegative is True and term.is_real is True,
                 "NOISE_LAW_DOMAIN", loc, "Each additive PSD must be independently real and nonnegative")
            need(not term.has(freq, s), "NOISE_LAW_DOMAIN", loc,
                 "The supported adopted additive white law cannot depend on frequency or s")
            result += term
        return sp.simplify(result)
    raise GateError("UNSUPPORTED_DERIVATION", loc, operation)


def validate(package, root):
    """Return identity-bound evidence. Any failure yields no downstream export."""
    loc = "$"
    schema = json.loads((Path(__file__).resolve().parents[1]/"schemas/source-model-script.schema.json").read_text())
    errors = sorted(Draft202012Validator(schema).iter_errors(package), key=lambda e: str(list(e.path)))
    if errors:
        error = errors[0]
        raise GateError("SCHEMA", "$"+"".join("."+str(v) for v in error.path), error.message)
    keys(package, ["schema_version", "scope", "sources", "regions", "claims", "assumptions",
                   "models", "knowledge", "master", "caption_refs", "coverage"], [], loc)
    need(package["schema_version"] == "source-model-script-1", "SCHEMA", loc, "Unsupported version")
    sources = indexed(package["sources"], "sources")
    regions = indexed(package["regions"], "regions")
    claims = indexed(package["claims"], "claims")
    assumptions = indexed(package["assumptions"], "assumptions")
    models = indexed(package["models"], "models")
    knowledge = indexed(package["knowledge"], "knowledge")
    need(sources and regions and claims and models and knowledge, "SCHEMA", loc, "Empty evidence stage")
    checks = {"sources": [], "regions": [], "models": [], "formulas": []}
    source_paths = {}
    for sid, source in sources.items():
        sloc = "sources."+sid
        keys(source, ["id", "path", "sha256", "page_count", "media_type", "authority", "rights"], [], sloc)
        path = safe_path(root, source["path"], sloc)
        source_paths[sid] = path
        need(sha(path) == source["sha256"], "SOURCE_HASH_MISMATCH", sloc, "Source bytes changed")
        need(type(source["page_count"]) is int and source["page_count"] > 0,
             "SCHEMA", sloc, "Invalid page count")
        need(source["rights"] in {"private_review_only", "original_public_fixture"}, "RIGHTS_SCOPE", sloc, "Unknown rights scope")
        need(source["media_type"] in {"application/pdf", "text/plain"}, "SOURCE_KIND", sloc,
             "Only PDF and original text sources are supported in this slice")
        if source["media_type"] == "application/pdf":
            try:
                info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=30, check=True)
            except (OSError, subprocess.SubprocessError) as exc:
                raise GateError("SOURCE_BINDING_UNAVAILABLE", sloc, "Cannot inspect PDF: "+str(exc)) from exc
            pages = re.search(r"^Pages:\s+(\d+)\s*$", info.stdout, re.MULTILINE)
            need(pages is not None and int(pages.group(1)) == source["page_count"], "SOURCE_PAGE_COUNT", sloc,
                 "Declared page count differs from original PDF")
        else:
            need(source["page_count"] == 1, "SOURCE_PAGE_COUNT", sloc, "Original text fixture is one logical document")
        checks["sources"].append({"id": sid, "sha256": source["sha256"], "status": "BYTES_VERIFIED"})
    render_cache = {}
    for rid, region in regions.items():
        rloc = "regions."+rid
        keys(region, ["id", "source_ref", "page", "bbox", "coordinate_system", "artifact_path",
                      "artifact_sha256", "description", "inspection", "render_recipe"], [], rloc)
        need(region["source_ref"] in sources, "SOURCE_MISSING", rloc, "Unknown source")
        need(type(region["page"]) is int and 1 <= region["page"] <= sources[region["source_ref"]]["page_count"],
             "SOURCE_REGION", rloc, "Page outside source")
        box = region["bbox"]
        need(isinstance(box, list) and len(box) == 4 and all(type(v) in {int, float} for v in box)
             and 0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1,
             "SOURCE_REGION", rloc, "Invalid normalized rectangle")
        need(region["coordinate_system"] in {"rendered_page_top_left_normalized", "original_text_whole_document"},
             "SOURCE_REGION", rloc, "Unsupported coordinates")
        path = safe_path(root, region["artifact_path"], rloc)
        need(sha(path) == region["artifact_sha256"], "SOURCE_HASH_MISMATCH", rloc, "Region artifact bytes changed")
        original = sources[region["source_ref"]]
        if original["media_type"] == "application/pdf":
            need(region["coordinate_system"] == "rendered_page_top_left_normalized" and
                 region["render_recipe"] == "pdftoppm-png-scale1600-v1", "SOURCE_REGION", rloc,
                 "PDF region requires the supported page-render recipe")
            key = (region["source_ref"], region["page"])
            if key not in render_cache:
                try:
                    with tempfile.TemporaryDirectory() as tmp:
                        target = Path(tmp)/"page"
                        subprocess.run(["pdftoppm", "-f", str(region["page"]), "-l", str(region["page"]),
                                        "-singlefile", "-scale-to", "1600", "-png",
                                        str(source_paths[region["source_ref"]]), str(target)],
                                       capture_output=True, timeout=30, check=True)
                        render_cache[key] = sha(target.with_suffix(".png"))
                except (OSError, subprocess.SubprocessError) as exc:
                    raise GateError("SOURCE_BINDING_UNAVAILABLE", rloc, "Cannot render source page: "+str(exc)) from exc
            need(render_cache[key] == region["artifact_sha256"], "SOURCE_ARTIFACT_MISMATCH", rloc,
                 "Evidence image does not match a fresh render of this source page with the declared recipe")
        else:
            need(region["coordinate_system"] == "original_text_whole_document" and
                 region["render_recipe"] == "not_applicable" and box == [0, 0, 1, 1] and
                 path == source_paths[region["source_ref"]] and region["artifact_sha256"] == original["sha256"],
                 "SOURCE_ARTIFACT_MISMATCH", rloc, "Text evidence must be the exact original source document")
        need(region["inspection"]["status"] in {"agent_visual_inspected", "original_text_inspected"},
             "SOURCE_NOT_INSPECTED", rloc, "Uninspected source is not eligible")
        checks["regions"].append({"id": rid, "status": "ARTIFACT_SOURCE_BINDING_VERIFIED",
                                  "semantic_faithfulness": "NOT_MACHINE_PROVEN"})
    for aid, assumption in assumptions.items():
        aloc = "assumptions."+aid
        keys(assumption, ["id", "fact", "value", "statement", "origin", "region_refs"], [], aloc)
        refs(assumption["region_refs"], regions, aloc, nonempty=True)
        need(assumption["origin"] in {"source_explicit", "analysis_assumption", "original_fixture"}, "SCHEMA", aloc, "Unknown origin")
    formulas = {}
    formula_models = {}
    for mid, model in models.items():
        mloc = "models."+mid
        keys(model, ["id", "role", "description", "nodes", "reference_node", "components", "parameters",
                     "excitation", "assumption_refs", "source_region_refs", "topology_review", "formulas"], [], mloc)
        refs(model["assumption_refs"], assumptions, mloc+".assumption_refs", nonempty=True)
        refs(model["source_region_refs"], regions, mloc+".source_region_refs", nonempty=True)
        need(model["topology_review"]["status"] == "agent_transcribed_requires_professional_review",
             "REVIEW_BOUNDARY", mloc, "Machine checks cannot grant topology approval")
        facts = {}
        for aid in model["assumption_refs"]:
            assumption = assumptions[aid]
            need(assumption["fact"] not in facts or (type(facts[assumption["fact"]]) == type(assumption["value"]) and facts[assumption["fact"]] == assumption["value"]),
                 "ASSUMPTION_CONFLICT", mloc, assumption["fact"])
            facts[assumption["fact"]] = assumption["value"]
        need(facts.get("linear_small_signal") is True, "ASSUMPTION_CONFLICT", mloc,
             "The supported MNA roles require linear_small_signal=true")
        expr, samples = model_context(model, mloc)
        transfers, evidence = solve_mna(model, expr, mloc)
        checks["models"].append({"id": mid, "status": "DECLARED_LINEAR_MODEL_SOLVED", **evidence,
                                 "topology_source_correspondence": "REVIEW_REQUIRED",
                                 "assumption_check_scope": "Required declarations and known role constraints only; other physical/topological compatibility requires review"})
        for fid, formula in indexed(model["formulas"], mloc+".formulas").items():
            floc = mloc+".formulas."+fid
            keys(formula, ["id", "expression", "unit", "requirements", "derivation", "steps", "claim_refs"], [], floc)
            need(fid not in formulas, "DUPLICATE_ID", floc, fid)
            need(formula["steps"], "DERIVATION_MISSING", floc, "Derivation explanation required")
            refs(formula["claim_refs"], claims, floc+".claim_refs", nonempty=True)
            need(isinstance(formula["requirements"], dict) and formula["requirements"], "ASSUMPTION_MISSING", floc, "Explicit requirements needed")
            for fact, value in formula["requirements"].items():
                need(fact in facts, "ASSUMPTION_MISSING", floc, fact)
                need(type(facts[fact]) == type(value) and facts[fact] == value, "ASSUMPTION_CONFLICT", floc,
                     f"Requires {fact}={value!r}, model declares {facts[fact]!r}")
            actual, dim = expr.parse(formula["expression"], floc+".expression")
            need(dim == unit(formula["unit"], floc), "UNIT_MISMATCH", floc, "Formula result unit mismatch")
            expected = expected_formula(formula, transfers, expr, model, facts, floc+".derivation")
            residual = sp.factor(sp.cancel(actual-expected))
            need(residual == 0 or sp.simplify(residual) == 0, "MATH_IDENTITY_FAILED", floc,
                 "Declared formula differs from solved model; residual="+str(residual))
            numeric = []
            for frequency in [0, 1e6, 1e9]:
                replacements = {**samples, expr.symbols["s"]: sp.I*2*sp.pi*frequency}
                if formula["derivation"]["operation"] == "noise_projection":
                    frequency_symbol = formula["derivation"]["frequency"]
                    if frequency_symbol in expr.symbols:
                        replacements[expr.symbols[frequency_symbol]] = frequency
                value = complex(actual.subs(replacements).evalf())
                check = complex(expected.subs(replacements).evalf())
                need(math.isfinite(value.real) and math.isfinite(value.imag), "NUMERICAL_SANITY", floc, "Nonfinite sample")
                need(abs(value-check) <= 1e-9*max(1, abs(check)), "NUMERICAL_SANITY", floc, "Symbolic-expression spot evaluations differ")
                if formula["unit"] == "A2/Hz":
                    need(abs(value.imag) < 1e-30 and value.real >= 0, "NUMERICAL_SANITY", floc, "PSD must be real and nonnegative")
                numeric.append({"s_frequency_hz": frequency, "real": value.real, "imag": value.imag})
            checks["formulas"].append({"id": fid, "model": mid, "symbol_structure": "VALID",
                                       "dimension_check": "PASS", "algebra_against_declared_model": "PASS",
                                       "residual": "0", "expected_expression": str(expected), "numeric_samples": numeric,
                                       "numeric_evidence_kind": "SPOT_EVALUATION_NOT_INDEPENDENT_CIRCUIT_SIMULATION",
                                       "noise_evidence_scope": "Projection algebra under adopted PSD laws" if formula["derivation"]["operation"] == "noise_projection" else None,
                                       "scientific_review": "NOT_GRANTED"})
            formulas[fid], formula_models[fid] = formula, mid
    for fid, formula in formulas.items():
        for cid in formula["claim_refs"]:
            need(fid in claims[cid]["formula_refs"] and formula_models[fid] in claims[cid]["model_refs"],
                 "REFERENCE_MISMATCH", "formulas."+fid, "Formula/claim/model links must be bidirectional")
    for cid, claim in claims.items():
        cloc = "claims."+cid
        keys(claim, ["id", "text", "kind", "region_refs", "model_refs", "formula_refs",
                     "coverage_status", "coverage_note", "review_status"], [], cloc)
        refs(claim["region_refs"], regions, cloc+".region_refs", nonempty=True)
        refs(claim["model_refs"], models, cloc+".model_refs")
        refs(claim["formula_refs"], formulas, cloc+".formula_refs")
        need(claim["kind"] in {"source_statement", "derived_result", "interpretation"}, "SCHEMA", cloc, "Unknown claim type")
        need(claim["coverage_status"] in {"scripted", "verified_model_only", "source_only", "blocked"}, "SCHEMA", cloc, "Unknown coverage")
        need(claim["review_status"] == "not_professionally_reviewed", "REVIEW_BOUNDARY", cloc, "No approval route in this gate")
        if claim["coverage_status"] in {"scripted", "verified_model_only"} and claim["kind"] == "derived_result":
            need(claim["formula_refs"], "DERIVATION_MISSING", cloc, "Derived result needs checked formula")
        for fid in claim["formula_refs"]:
            need(formula_models[fid] in claim["model_refs"] and cid in formulas[fid]["claim_refs"],
                 "REFERENCE_MISMATCH", cloc, "Claim/formula/model links must be bidirectional")
    for kid, k in knowledge.items():
        kloc = "knowledge."+kid
        keys(k, ["id", "goal", "prerequisite_ids", "claim_refs", "formula_refs", "assumed_prerequisite"], [], kloc)
        refs(k["prerequisite_ids"], knowledge, kloc+".prerequisite_ids")
        refs(k["claim_refs"], claims, kloc+".claim_refs", nonempty=not k["assumed_prerequisite"])
        refs(k["formula_refs"], formulas, kloc+".formula_refs")
        need(set(k["formula_refs"]) <= {f for c in k["claim_refs"] for f in claims[c]["formula_refs"]},
             "REFERENCE_MISMATCH", kloc, "Knowledge formulas must be supported by knowledge claims")
    visiting, done = set(), set()
    def visit(kid):
        need(kid not in visiting, "PREREQUISITE_CYCLE", "knowledge."+kid, "Cycle in knowledge prerequisites")
        if kid in done: return
        visiting.add(kid)
        for parent in knowledge[kid]["prerequisite_ids"]: visit(parent)
        visiting.remove(kid); done.add(kid)
    for kid in knowledge: visit(kid)
    master = package["master"]
    keys(master, ["revision", "sentences", "paragraphs", "sha256"], [], "master")
    sentences = indexed(master["sentences"], "master.sentences")
    need(sentences, "SCRIPT_MISSING", "master", "Formal manuscript cannot be empty")
    identity = digest({"revision": master["revision"], "sentences": master["sentences"], "paragraphs": master["paragraphs"]})
    need(master["sha256"] == identity, "MASTER_HASH_MISMATCH", "master", "Formal master changed")
    seen_claims, seen_formulas, seen_knowledge = set(), set(), set()
    completed_knowledge = {kid for kid, k in knowledge.items() if k["assumed_prerequisite"]}
    for sid, sentence in sentences.items():
        sloc = "master.sentences."+sid
        keys(sentence, ["id", "text", "knowledge_refs", "claim_refs", "formula_refs"], [], sloc)
        need(isinstance(sentence["text"], str) and sentence["text"].strip(), "SCRIPT_MISSING", sloc, "Empty formal text")
        refs(sentence["knowledge_refs"], knowledge, sloc+".knowledge_refs", nonempty=True)
        refs(sentence["claim_refs"], claims, sloc+".claim_refs", nonempty=True)
        refs(sentence["formula_refs"], formulas, sloc+".formula_refs")
        for cid in sentence["claim_refs"]:
            need(claims[cid]["coverage_status"] == "scripted", "UNSUPPORTED_CLAIM_IN_SCRIPT", sloc,
                 f"{cid} is {claims[cid]['coverage_status']}, not eligible for this script")
        for kid in sentence["knowledge_refs"]:
            need(set(knowledge[kid]["prerequisite_ids"]) <= completed_knowledge,
                 "PREREQUISITE_ORDER", sloc, kid)
        need(set(sentence["formula_refs"]) <= {f for c in sentence["claim_refs"] for f in claims[c]["formula_refs"]},
             "REFERENCE_MISMATCH", sloc, "Formula is not supported by sentence's claims")
        need(set(sentence["claim_refs"]) <= {c for k in sentence["knowledge_refs"] for c in knowledge[k]["claim_refs"]},
             "REFERENCE_MISMATCH", sloc, "Sentence claims must be supported by its knowledge nodes")
        need(all(set(knowledge[k]["claim_refs"]) & set(sentence["claim_refs"]) for k in sentence["knowledge_refs"]),
             "REFERENCE_MISMATCH", sloc, "A sentence cannot complete an unrelated knowledge node")
        seen_claims.update(sentence["claim_refs"]); seen_formulas.update(sentence["formula_refs"]); seen_knowledge.update(sentence["knowledge_refs"])
        completed_knowledge.update(kid for kid in seen_knowledge
                                   if set(knowledge[kid]["claim_refs"]) <= seen_claims and
                                   set(knowledge[kid]["formula_refs"]) <= seen_formulas)
    paragraphs = indexed(master["paragraphs"], "master.paragraphs")
    paragraph_spans = []
    for pid, para in paragraphs.items():
        keys(para, ["id", "sentence_ids"], [], "master.paragraphs."+pid)
        refs(para["sentence_ids"], sentences, "master.paragraphs."+pid, nonempty=True)
        paragraph_spans.extend(para["sentence_ids"])
    need(paragraph_spans == list(sentences), "SCRIPT_COVERAGE", "master.paragraphs", "Paragraph order/coverage differs from master")
    captions = indexed(package["caption_refs"], "caption_refs")
    need(len(captions) == len(sentences), "CAPTION_COVERAGE", "caption_refs", "Exactly one full-source cue per sentence required")
    resolved = []
    for (cid, cap), (sid, sent) in zip(captions.items(), sentences.items()):
        cloc = "caption_refs."+cid
        keys(cap, ["id", "span_id", "source_range", "master_sha256", "slice_sha256"], [], cloc)
        need(cap["span_id"] == sid and cap["source_range"] == [0, len(sent["text"])], "CAPTION_COVERAGE", cloc,
             "No summaries, gaps, reordering, or partial-sentence source ranges")
        need(cap["master_sha256"] == identity, "STALE_CAPTION_REFERENCE", cloc, "Master identity changed")
        need(cap["slice_sha256"] == hashlib.sha256(sent["text"].encode()).hexdigest(), "CAPTION_HASH_MISMATCH", cloc, "Slice differs")
        resolved.append({"id": cid, "span_id": sid, "text": sent["text"]})
    coverage = package["coverage"]
    keys(coverage, ["required_claim_ids", "required_formula_ids", "required_knowledge_ids", "excluded_scope"], [], "coverage")
    for field, target, seen in [("required_claim_ids", claims, seen_claims), ("required_formula_ids", formulas, seen_formulas),
                                ("required_knowledge_ids", knowledge, completed_knowledge)]:
        refs(coverage[field], target, "coverage."+field, nonempty=True)
        need(set(coverage[field]) <= seen, "SCRIPT_COVERAGE", "coverage."+field,
             "Not covered by formal master: "+", ".join(sorted(set(coverage[field])-seen)))
    need({cid for cid, c in claims.items() if c["coverage_status"] == "scripted"} <= seen_claims,
         "SCRIPT_COVERAGE", "claims", "Claim marked scripted without a formal span")
    return {"schema_version": "source-model-gate-report-1", "validator_version": VERSION,
            "status": "MACHINE_CHECKS_PASSED_REVIEW_REQUIRED", "package_sha256": digest(package),
            "master_sha256": identity, "checks": checks,
            "coverage": {"ledger_claim_count": len(claims), "scripted_claim_count": len(seen_claims),
                         "formula_count": len(formulas), "sentence_count": len(sentences),
                         "caption_count": len(resolved), "excluded_scope": coverage["excluded_scope"]},
            "resolved_captions": resolved,
            "downstream": {"technical_formal_export_allowed": True, "scientific_approval": False,
                           "audio_alignment_approval": False, "publication_allowed": False},
            "limits": ["Hashes prove byte identity, not source meaning or rights ownership.",
                       "MNA proves algebra for the declared linear model, not its adequacy for physical hardware.",
                       "Source-to-topology mapping and prose-to-claim faithfulness require independent review.",
                       "No TTS, measured timing, rendering, professional approval, or delivery authorization is created."]}


def export_formal(package, root):
    report = validate(package, root)  # Never trust a caller-supplied PASS report.
    return {"schema_version": "p1-validated-formal-export-1", "gate_report": report,
            "narration": [{"id": s["id"], "text": s["text"]} for s in package["master"]["sentences"]],
            "caption_refs": [{"id": c["id"], "narration_id": c["span_id"], "source_range": c["source_range"]}
                             for c in package["caption_refs"]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--export-formal", action="store_true")
    args = parser.parse_args()
    try:
        package = json.loads(args.package.read_text())
        result = export_formal(package, args.package.parent) if args.export_formal else validate(package, args.package.parent)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except GateError as exc:
        result = {"status": "BLOCKED", "error": exc.record(), "downstream": {"technical_formal_export_allowed": False,
                  "scientific_approval": False, "publication_allowed": False}}
    except Exception as exc:
        result = {"status": "BLOCKED", "error": {"code": "INVALID_PACKAGE", "location": "$",
                  "message": str(exc)}, "downstream": {"technical_formal_export_allowed": False,
                  "scientific_approval": False, "publication_allowed": False}}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1


if __name__ == "__main__":
    sys.exit(main())
