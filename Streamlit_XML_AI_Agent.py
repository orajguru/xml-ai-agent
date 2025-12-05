import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO
import os
from datetime import datetime

st.sidebar.title("🔧 AI Configuration")
status_box = st.sidebar.empty()
st.set_page_config(page_title="XML AI Mapper", page_icon="🤖", layout="wide")
st.title("🔍 XML Field Mapper (AI Powered)")
st.caption("Upload → Clean → Compare → Ask AI → Export")

try:
    from ai_engine import AIEngine
    llm = AIEngine()
except Exception as e:
    print("\n==== ERROR creating AIEngine ====")
    print(repr(e))
    print("=================================\n")
    raise

if llm:
    if llm.active_model:
        status_box.success(f"🧠 Model in use: {llm.active_model}")
    else:
        status_box.info("ℹ️ AI engine has loaded. No model used yet.")
else:

    # UI Helper to mask key
    def mask(key):
        return f"****{key[-4:]}" if key else "None"

    # Status Display
    st.sidebar.subheader("API Status")

    openai_status = "🟢 Connected" if llm.openai_key else "🔴 Missing"
    grok_status = "🟢 Connected" if llm.grok_key else "🔴 Missing"

    st.sidebar.write(f"**OpenAI:** {openai_status} | {mask(llm.openai_key)}")
    st.sidebar.write(f"**Grok:** {grok_status} | {mask(llm.grok_key)}")

    # Test Button
    if st.sidebar.button("🔍 Test Connection"):
        result = llm.test_connection()

        if result.get("openai"):
            st.sidebar.success("🟢 OpenAI Responding")
        else:
            st.sidebar.error("🔴 OpenAI Failed")

        if result.get("grok"):
            st.sidebar.success("🟢 Grok Responding")
        else:
            st.sidebar.error("🔴 Grok Failed")


#st.set_page_config(page_title="XML AI Mapper", page_icon="🤖", layout="wide")
#st.title("🔍 XML Field Mapper (AI Powered)")
#st.caption("Upload → Clean → Compare → Ask AI → Export")

# Show which AI engine is active (if ai_engine exists)
#if llm and getattr(llm, "active_model", None):
#   st.sidebar.success(f"🧠 Model in use: {llm.active_model}")
#else:
 #   st.sidebar.warning("⚠️ AI model not initialized yet.")

# ------------------- Helper functions (correct algorithm) -------------------

def _split_field(text):
    """Split comma-separated attribute safely and return stripped tokens."""
    if not text:
        return []
    return [t.strip() for t in text.split(",") if t.strip()]

def _prettify_xml(elem):
    """
    Simple pretty printer to indent XML for readability.
    """
    def _indent(e, level=0):
        i = "\n" + level*"  "
        if len(e):
            if not e.text or not e.text.strip():
                e.text = i + "  "
            for child in e:
                _indent(child, level+1)
            if not child.tail or not child.tail.strip():
                child.tail = i
        if level and (not e.tail or not e.tail.strip()):
            e.tail = i
    _indent(elem)
    return ET.tostring(elem, encoding="unicode")

def generate_clean_xml_from_root(root):
    """
    Cleans and rebuilds <option> XML while preserving original ordering.

    Rules:
    1️⃣ Split comma-separated options into individual records.
    2️⃣ If the same value appears multiple times → treat as a single item.
    3️⃣ Union dependents for each unique value.
    4️⃣ If multiple values share identical dependents → merge under one <option>.
    5️⃣ DO NOT sort — preserve original ordering exactly as first encountered.

    Additional:
    - Dependent <name> attribute uses first occurrence name permanently.
    - Names and their corresponding values stay aligned.
    """

    def _split(text):
        return [t.strip() for t in text.split(",") if t.strip()] if text else []

    flat = []
    dep_id_to_name = {}      # Tracks first seen dependent name
    name_to_value = {}       # Tracks first mapping name->value

    # --- STEP 1: FLATTEN INPUT ---
    for opt in root.findall("option"):
        names = _split(opt.get("name", ""))
        values = _split(opt.get("value", ""))

        deps = opt.findall("dependent")
        dep_ids = []

        for d in deps:
            dep_id = d.get("id")
            dep_name = d.get("name", "")
            dep_ids.append(dep_id)

            if dep_id not in dep_id_to_name:
                dep_id_to_name[dep_id] = dep_name   # keep first seen dependent name

        for idx, name in enumerate(names):
            value = values[idx] if idx < len(values) else values[-1] if values else ""
            flat.append({"name": name, "value": value, "deps": set(dep_ids)})

            if name not in name_to_value:
                name_to_value[name] = value

    # --- STEP 2: UNION DEPENDENTS PER VALUE ---
    value_to_deps = {}
    for item in flat:
        val = item["value"]
        if val not in value_to_deps:
            value_to_deps[val] = set()
        value_to_deps[val].update(item["deps"])

    # --- STEP 3: MERGE VALUES WITH IDENTICAL DEPENDENTS ---
    merged = []
    seen_dep_sets = {}

    for item in flat:
        val = item["value"]
        dep_key = frozenset(value_to_deps[val])

        if dep_key not in seen_dep_sets:
            seen_dep_sets[dep_key] = {
                "names": [],
                "values": [],
                "deps": dep_key
            }

        group = seen_dep_sets[dep_key]
        if item["name"] not in group["names"]:
            group["names"].append(item["name"])
        if val not in group["values"]:
            group["values"].append(val)

    # Preserve first-seen group order
    merged = list(seen_dep_sets.values())

    # --- STEP 4: REBUILD CLEAN XML ---
    new_root = ET.Element("dependents", root.attrib)

    for group in merged:
        opt = ET.SubElement(new_root, "option")
        opt.set("name", ",".join(group["names"]))
        opt.set("value", ",".join(group["values"]))

        # dependents sorted only for consistent XML formatting (not required, safe)
        for dep_id in sorted(group["deps"], key=str):
            ET.SubElement(opt, "dependent", {
                "type": "0",
                "id": dep_id,
                "name": dep_id_to_name.get(dep_id, ""),
                "reset": "false",
                "retainonedit": "false"
            })

    return _prettify_xml(new_root)

# ------------------- Streamlit app UI -------------------

uploaded = st.file_uploader("📁 Upload XML file", type=["xml"])
xml_text = None
cleaned_xml = None
original_root = None

if uploaded:
    xml_text = uploaded.read().decode("utf-8")
    st.subheader("📄 Original XML Preview")
    st.code("\n".join(xml_text.splitlines()[:10]) + ("\n..." if len(xml_text.splitlines())>10 else ""), language="xml")

    # parse and clean
    try:
        original_root = ET.fromstring(xml_text)
        cleaned_xml = generate_clean_xml_from_root(original_root)
        st.subheader("🧼 Cleaned / Optimized XML Preview (Max 50 lines)")
        cleaned_lines = cleaned_xml.splitlines()
        preview_lines = cleaned_lines[:50]
        st.code("\n".join(preview_lines) + ("\n..." if len(cleaned_lines) > 50 else ""), language="xml")

        st.success("✅ Cleaned output generated (per-name aggregation & grouping by identical dependents).")

    except Exception as e:
        st.error(f"XML parse / cleaning error: {e}")

# Comparison counts
if uploaded and cleaned_xml:
    st.subheader("🔄 Summary (Before vs After)")
    df = pd.DataFrame([
        ["Option Count", len(original_root.findall('option')), cleaned_xml.count("<option")],
        ["Dependent Count", xml_text.count("<dependent"), cleaned_xml.count("<dependent")]
    ], columns=["Metric", "Original", "Cleaned"])
    st.dataframe(df)

# Download cleaned xml
if cleaned_xml:
    st.download_button("📥 Download Clean XML", cleaned_xml, file_name="cleaned_dependents.xml", mime="text/xml")

# ------------------- Export Mapping with Change Tracking (Hybrid G numbering) -------------------
if cleaned_xml and uploaded:

    # Parse both XMLs
    root_clean = ET.fromstring(cleaned_xml)
    root_original = ET.fromstring(xml_text)

    # ---------------- Build original groups (preserve order) ----------------
    original_groups = []  # list of dicts: {id: "G1", values_set: frozenset([...]), names: [...], dependents: [...]}
    original_group_set_to_id = {}
    value_to_original_group_sets = {}  # value -> list of frozenset group sets it belonged to (in order)
    value_to_original_deps = {}  # value -> set of "id:name" strings (union across occurrences)
    value_to_original_name = {}  # first-seen name -> value mapping (for Original Value Name column)

    g_count = 0
    for opt in root_original.findall("option"):
        g_count += 1
        gid = f"G{g_count}"
        names = _split_field(opt.get("name", ""))
        values = _split_field(opt.get("value", ""))
        # group values set (based on value ids)
        values_set = frozenset(values)

        deps = sorted([f"{d.get('id')}:{d.get('name')}" for d in opt.findall("dependent")])

        original_groups.append({
            "id": gid,
            "values_set": values_set,
            "names": names,
            "dependents": deps
        })

        # mapping group set -> id (first occurrence)
        if values_set not in original_group_set_to_id:
            original_group_set_to_id[values_set] = gid

        # register each value's original group sets (a value may appear multiple times)
        for v in values:
            value_to_original_group_sets.setdefault(v, []).append(values_set)
            # union dependents per value
            value_to_original_deps.setdefault(v, set()).update(deps)

    # ---------------- Build cleaned groups (preserve order from cleaned XML) ----------------
    cleaned_groups = []  # list of dicts: {names:[], values:[], dependents:[], final_values_set: frozenset(...) }
    for opt in root_clean.findall("option"):
        names = _split_field(opt.get("name", ""))
        values = _split_field(opt.get("value", ""))
        deps = sorted([f"{d.get('id')}:{d.get('name')}" for d in opt.findall("dependent")])
        cleaned_groups.append({
            "names": names,
            "values": values,
            "dependents": deps,
            "values_set": frozenset(values)
        })

    # ---------------- Hybrid G numbering ----------------
    # Start new G numbers from next after original groups
    next_g_index = g_count + 1
    final_group_assignments = []  # parallel to cleaned_groups: assigned final G id
    used_new_ids = []

    # We'll also keep a mapping from final values_set to final G id (to avoid duplicate new Gs)
    final_valueset_to_gid = {}

    for cg in cleaned_groups:
        fvset = cg["values_set"]
        # If this final values set exactly matches any original group set -> keep that original G id
        if fvset in original_group_set_to_id:
            gid = original_group_set_to_id[fvset]
            final_valueset_to_gid[fvset] = gid
            final_group_assignments.append(gid)
        else:
            # If we've already assigned a new G id for this final set earlier, reuse it
            if fvset in final_valueset_to_gid:
                gid = final_valueset_to_gid[fvset]
                final_group_assignments.append(gid)
            else:
                gid = f"G{next_g_index}"
                next_g_index += 1
                final_valueset_to_gid[fvset] = gid
                used_new_ids.append(gid)
                final_group_assignments.append(gid)

    # ---------------- Build per-value export rows ----------------
    export_rows = []
    # We'll need quick lookups:
    # value -> final group id and final group values_set and final dependents and final group name (joined names)
    value_to_final_info = {}
    for cg, gid in zip(cleaned_groups, final_group_assignments):
        for v in cg["values"]:
            value_to_final_info[v] = {
                "final_gid": gid,
                "final_values_set": cg["values_set"],
                "final_dependents": cg["dependents"],
                "final_group_name": ",".join(cg["names"])
            }

    # For original name mapping (first-seen)
    for opt in root_original.findall("option"):
        names = _split_field(opt.get("name", ""))
        values = _split_field(opt.get("value", ""))
        for i, name in enumerate(names):
            val = values[i] if i < len(values) else values[-1] if values else ""
            if val and val not in value_to_original_name:
                value_to_original_name[val] = name

    # Now construct rows for each final value (preserve cleaned order by iterating cleaned_groups)
    sr = 1
    for cg, gid in zip(cleaned_groups, final_group_assignments):
        final_values = cg["values"]
        final_values_set = cg["values_set"]
        final_deps = cg["dependents"]
        final_group_name = ",".join(cg["names"])
        for v in final_values:
            orig_name = value_to_original_name.get(v, "")
            # determine original group id for this value (if any)
            orig_group_id = ""
            orig_group_sets = value_to_original_group_sets.get(v, [])
            if orig_group_sets:
                # if any of the original group sets exactly match final set, take that group's id
                matched = None
                for ogs in orig_group_sets:
                    if ogs == final_values_set and ogs in original_group_set_to_id:
                        matched = original_group_set_to_id[ogs]
                        break
                if matched:
                    orig_group_id = matched
                else:
                    # otherwise pick the first original group id this value belonged to (traceability)
                    first_ogs = orig_group_sets[0]
                    orig_group_id = original_group_set_to_id.get(first_ogs, "")
            # Group Status: Modified if final_values_set not in original_group_sets for this value
            group_status = "Non-modified" if (final_values_set in orig_group_sets) else "Modified"
            # Dependency Status: compare original deps (union) vs final deps
            orig_deps_set = set(value_to_original_deps.get(v, []))
            final_deps_set = set(final_deps)
            dependency_status = "Non-modified" if orig_deps_set == final_deps_set else "Modified"

            export_rows.append([
                sr,
                v,
                orig_name,
                final_group_name,
                orig_group_id,
                gid,
                group_status,
                dependency_status,
                ";".join(sorted(orig_deps_set)),
                ";".join(sorted(final_deps_set))
            ])
            sr += 1

    # Build DataFrame and export
    df_export = pd.DataFrame(export_rows, columns=[
        "Sr No",
        "Value ID",
        "Original Value Name",
        "Final Group Name",
        "Original Group ID",
        "Final Group ID",
        "Group Status",
        "Dependency Status",
        "Original Dependents",
        "Final Dependents"
    ])

    # Date-stamped file name
    today = datetime.now().strftime("%Y%m%d")
    excel_filename = f"Cleaned_XML_Report_{today}.xlsx"

    excel_buffer = BytesIO()
    df_export.to_excel(excel_buffer, index=False, sheet_name="Mapping")
    excel_buffer.seek(0)

    st.download_button(
        "📥 Download Mapping Excel",
        data=excel_buffer,
        file_name=excel_filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# AI Suggest mapping (if ai_engine present)
st.markdown("---")
st.subheader("🤖 AI: Suggest Mapping (Optional)")

if st.button("💡 Suggest Mapping (AI)"):
    if not cleaned_xml:
        st.warning("Please upload and generate cleaned XML first.")
    else:
        if not llm:
            st.warning("No AI engine available (ensure ai_engine.py exists and secrets set).")
        else:
            with st.spinner("AI analyzing cleaned XML..."):
                try:
                    # generate prompt & call
                    prompt = f"""You are an XML expert. Given the cleaned <dependents> XML below,
explain grouping decisions, detect duplicates, and produce a suggested mapping table.
Return a short summary and a JSON mapping example.

Cleaned XML:
{cleaned_xml}
"""
                    ai_text = llm.generate(prompt)
                    st.subheader("AI Output")
                    if "⚠️" in ai_text or "Error" in ai_text:
                        st.error(ai_text)
                    else:
                        st.code(ai_text)
                except Exception as e:
                    st.error(f"AI call error: {e}")

st.caption("Built by IBL Digital Team • AI XML Mapping Assistant 🔧🚀")
