"""Trace the source of phantom field names in ThemeEngine/HypothesisDrivenGenerator."""
import sys
sys.path.insert(0, '.')
from brain_alpha_ops.data import OfficialDataLoader, FieldDatasetMapper
from brain_alpha_ops.research.theme_engine import DynamicThemeEngine
from brain_alpha_ops.research.dataset_selector import DatasetSelector
from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary
from brain_alpha_ops.research.hypothesis_driven_generator import HypothesisDrivenGenerator
import re

loader = OfficialDataLoader.instance()
mapper = FieldDatasetMapper(); mapper.build(loader)
theme = DynamicThemeEngine(loader); theme.build_categories()
selector = DatasetSelector(); selector.initialize(loader)
library = HypothesisLibrary('brain_alpha_ops/research/hypotheses').load_all()

gen = HypothesisDrivenGenerator(loader=loader, mapper=mapper, theme_engine=theme, selector=selector, library=library, ratio_str='70/20/10')
gen.update_context(
    [{'name': f.id, 'category': f.category} for f in loader.get_fields()],
    [{'name': op.name} for op in loader.get_operators()]
)

ds = 'analyst4'
gen.set_dataset(ds)
ds_fields = set(mapper.fields_for(ds))
ds_fields_lower = {f.lower() for f in ds_fields}
print(f"Dataset: {ds} ({len(ds_fields)} fields)")

targets = {'anl20', '1120', 'adxqfv'}

# Instrument _fill_placeholders in ThemeEngine
original_fill = theme._fill_placeholders
def instrumented_fill(skeleton, available_cats, cat_fields):
    result = original_fill(skeleton, available_cats, cat_fields)
    for target in targets:
        if target in result:
            # Find which field doesn't exist in dataset
            tokens = re.findall(r'\b([a-zA-Z_]\w+)\b', result)
            for t in tokens:
                if t.lower() not in ds_fields_lower and not t.isdigit():
                    # Check if this token exists in the full field list
                    in_full = any(f.id.lower() == t.lower() for f in loader.get_fields())
                    in_cat = any(t.lower() in [f.lower() for f in v] for v in cat_fields.values())
                    print(f"[ThemeEngine._fill_placeholders] PHANTOM: '{t}' in_full={in_full} in_cat={in_cat}")
                    print(f"  skeleton: {skeleton}")
                    print(f"  result: {result[:150]}")
                    break
            break
    return result
theme._fill_placeholders = instrumented_fill

# Instrument _sanitize_expression
original_sanitize = gen._sanitize_expression
def instrumented_sanitize(expr, fields):
    result = original_sanitize(expr, fields)
    for target in targets:
        if target in result:
            tokens = re.findall(r'\b([a-zA-Z_]\w+)\b', result)
            for t in tokens:
                if t.lower() not in ds_fields_lower and not t.isdigit():
                    print(f"[_sanitize_expression] PHANTOM: '{t}'")
                    print(f"  input: {expr[:150]}")
                    print(f"  output: {result[:150]}")
                    break
            break
    return result
gen._sanitize_expression = instrumented_sanitize

# Instrument _resolve_named_field
original_resolve = gen._resolve_named_field
def instrumented_resolve(name, field_categories, selected_fields):
    result = original_resolve(name, field_categories, selected_fields)
    if result and result.lower() not in ds_fields_lower:
        print(f"[_resolve_named_field] PHANTOM: name='{name}' → '{result}' NOT in dataset!")
    return result
gen._resolve_named_field = instrumented_resolve

# Generate and trace
print("\n--- Tracing generation ---")
for i in range(10):
    c = gen._generate_hypothesis_driven(ds)
    if c is None: continue
    for target in targets:
        if target in c.expression:
            tokens = re.findall(r'\b([a-zA-Z_]\w+)\b', c.expression)
            bad = [t for t in tokens if t.lower() not in ds_fields_lower and not t.isdigit()]
            print(f"\n[FOUND] Candidate #{i}: {c.expression[:150]}")
            print(f"  phantom tokens: {bad}")
            print(f"  family: {c.family}")
            break

print("\n--- Tracing ThemeEngine random exploration ---")
for i in range(10):
    c = gen._generate_random_exploration(ds)
    if c is None: continue
    for target in targets:
        if target in c.expression:
            tokens = re.findall(r'\b([a-zA-Z_]\w+)\b', c.expression)
            bad = [t for t in tokens if t.lower() not in ds_fields_lower and not t.isdigit()]
            print(f"\n[FOUND] Random#{i}: {c.expression[:150]}")
            print(f"  phantom tokens: {bad}")
            break
