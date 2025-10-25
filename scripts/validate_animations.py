from __future__ import annotations
import os
import sys
import json
import argparse
import asyncio
from typing import Dict, Any, List, Tuple

# Allow importing project modules
PROJECT_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if PROJECT_SRC not in sys.path:
    sys.path.append(PROJECT_SRC)

# Optional import of VTS client (only used when --check-vts is provided)
try:
    from adapters.vts.vts_client import VTSClient  # type: ignore
except Exception:
    VTSClient = None  # type: ignore

ALLOWED_PARAM_PREFIXES = (
    "Param",
)


def validate_motion3_schema(data: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    # Top-level keys
    if data.get("Version") != 3:
        errors.append("Version must be 3")

    meta = data.get("Meta")
    if not isinstance(meta, dict):
        errors.append("Meta must be an object")
    else:
        dur = meta.get("Duration")
        fps = meta.get("Fps")
        loop = meta.get("Loop")
        if not isinstance(dur, (int, float)) or dur <= 0:
            errors.append("Meta.Duration must be a positive number")
        if not isinstance(fps, (int, float)) or fps <= 0:
            errors.append("Meta.Fps must be a positive number")
        if not isinstance(loop, bool):
            errors.append("Meta.Loop must be a boolean")

    curves = data.get("Curves")
    if not isinstance(curves, list) or len(curves) == 0:
        errors.append("Curves must be a non-empty array")
    else:
        # If CurveCount is present, check it
        if isinstance(meta, dict):
            curve_count = meta.get("CurveCount")
            if isinstance(curve_count, int) and curve_count != len(curves):
                errors.append(f"Meta.CurveCount={curve_count} does not match actual {len(curves)}")
        # Validate a few representative properties per curve
        for idx, cv in enumerate(curves[:50]):  # cap validation to avoid huge files
            if not isinstance(cv, dict):
                errors.append(f"Curves[{idx}] must be an object")
                continue
            tgt = cv.get("Target")
            cid = cv.get("Id")
            segs = cv.get("Segments")
            if tgt not in ("Parameter", "PartOpacity"):
                errors.append(f"Curves[{idx}].Target must be 'Parameter' or 'PartOpacity'")
            if not isinstance(cid, str) or len(cid) == 0:
                errors.append(f"Curves[{idx}].Id must be a non-empty string")
            else:
                # Only enforce 'Param*' prefix when Target is 'Parameter'
                if tgt == "Parameter" and not cid.startswith(ALLOWED_PARAM_PREFIXES):
                    errors.append(f"Curves[{idx}].Id '{cid}' not matching Hiyori_A conventions")
            if not isinstance(segs, list) or len(segs) < 2:
                errors.append(f"Curves[{idx}].Segments must be an array with values")
            else:
                # Basic sanity: values should be numbers; sample a handful
                sample = segs[:12]
                if not all(isinstance(x, (int, float)) for x in sample):
                    errors.append(f"Curves[{idx}].Segments contain non-numeric entries in sample")

    return errors


def scan_directory(dir_path: str) -> Tuple[List[Tuple[str, List[str]]], List[str]]:
    results: List[Tuple[str, List[str]]] = []
    global_issues: List[str] = []

    if not os.path.isdir(dir_path):
        global_issues.append(f"Directory not found: {dir_path}")
        return results, global_issues

    files = [f for f in os.listdir(dir_path) if f.lower().endswith(".motion3.json")]
    if not files:
        global_issues.append("No .motion3.json files found")
        return results, global_issues

    for fname in sorted(files):
        fpath = os.path.join(dir_path, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            errs = validate_motion3_schema(data)
            results.append((fname, errs))
        except Exception as e:
            results.append((fname, [f"Failed to parse JSON: {e}"]))

    return results, global_issues


async def check_vts_hotkeys_and_trigger() -> None:
    if VTSClient is None:
        print("[VTS] VTSClient not available; skip VTS check.")
        return
    vts = VTSClient()
    try:
        await vts.connect()
    except Exception as e:
        print(f"[VTS] connect failed: {e}")
        return

    # List hotkeys
    try:
        hotkeys = await vts._list_model_hotkeys()  # private but useful here
        print(f"[VTS] Hotkeys in current model: {len(hotkeys)}")
        # Filter animation-like hotkeys
        def is_anim(hk: Dict[str, Any]) -> bool:
            t = str(hk.get("type", "")).lower()
            n = str(hk.get("name", "")).lower()
            return ("anim" in n) or ("animation" in t)
        anim_hotkeys = [hk for hk in hotkeys if is_anim(hk)]
        print(f"[VTS] Animation hotkeys detected: {len(anim_hotkeys)}")
        for hk in anim_hotkeys[:10]:
            print(f"  - {hk.get('name')} ({hk.get('type')})")
        # Try triggering a few animations
        for hk in anim_hotkeys[:5]:
            name = hk.get("name") or hk.get("hotkeyName")
            if not name:
                continue
            print(f"[VTS] Trigger animation hotkey: {name}")
            await vts.trigger_hotkey_by_name(str(name))
            await asyncio.sleep(1.0)
    except Exception as e:
        print(f"[VTS] Listing/triggering hotkeys failed: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Live2D motion3 animation files for Hiyori_A")
    parser.add_argument("--dir", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "animations")), help="Directory containing .motion3.json files")
    parser.add_argument("--check-vts", action="store_true", help="Connect to VTube Studio and attempt to list+trigger animation hotkeys")
    args = parser.parse_args()

    print(f"[Validate] Scanning directory: {args.dir}")
    results, global_issues = scan_directory(args.dir)

    if global_issues:
        for issue in global_issues:
            print(f"[Validate] ERROR: {issue}")
        return 1

    total = len(results)
    ok = 0
    for fname, errs in results:
        if errs:
            print(f"[File] {fname}: INVALID")
            for e in errs[:10]:
                print(f"  - {e}")
        else:
            print(f"[File] {fname}: OK")
            ok += 1

    print(f"[Summary] Valid {ok}/{total} files")

    if args.check_vts:
        try:
            asyncio.run(check_vts_hotkeys_and_trigger())
        except Exception as e:
            print(f"[VTS] Runtime error: {e}")

    return 0 if ok == total else 2


if __name__ == "__main__":
    raise SystemExit(main())