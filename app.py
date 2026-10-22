from flask import Flask, render_template, request, jsonify
import sqlite3
import json
import random
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
DB_PATH = BASE_DIR / "nutriplan.db"
with open(BASE_DIR / "meal_pools.json", encoding="utf-8") as file:
    MEAL_POOLS = json.load(file)

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
NON_VEG_SWAPS = [
    "Grilled Chicken with Steamed Greens", "Grilled Chicken with Brown Rice",
    "Grilled Chicken with Salad", "Grilled Chicken with Quinoa", "Baked Fish with Herbs",
    "Baked Salmon with Greens", "Grilled Fish with Broccoli", "Grilled Fish with Steamed Greens",
    "Grilled Fish with Steamed Vegetables", "Grilled Fish with Quinoa"
]
VEGAN_SWAPS = {
    "Greek Yogurt with Berries": "Coconut Yogurt with Berries",
    "Greek Yogurt with Seeds": "Coconut Yogurt with Seeds",
    "Paneer + Vegetables": "Tofu + Vegetables",
    "Paneer & Vegetable Bowl": "Tofu & Vegetable Bowl",
    "Grilled Paneer with Garlic Greens": "Grilled Tofu with Garlic Greens",
    "Egg White Scramble with Spinach": "Chickpea Scramble with Spinach",
    "Egg White Scramble": "Chickpea Scramble",
    "Egg & Vegetable Wrap": "Hummus & Vegetable Wrap",
    "Herbed Egg Muffins": "Herbed Chickpea Muffins",
    "Vegetable Egg White Omelette": "Vegetable Chickpea Omelette"
}

NON_VEG_PATTERN = re.compile(r"\b(chicken|fish|salmon|tuna|shrimp|prawn|seafood|pork|beef|mutton|lamb|turkey|bacon|ham|sausage|egg|eggs)\b", re.I)
DAIRY_PATTERN = re.compile(r"\b(paneer|yogurt|curd|cheese|milk|cream|butter|ghee|whey|dairy|honey)\b", re.I)


def init_db():
    """Create the SQLite table used to persist generated meal plans."""
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS saved_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL DEFAULT 'local-user',
                condition_name TEXT NOT NULL,
                diet_preference TEXT NOT NULL,
                cuisine TEXT NOT NULL,
                allergies TEXT NOT NULL DEFAULT '',
                plan_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.commit()


def meal_for_diet(name, diet):
    # Dictionary lookup is a simple data-structure operation for vegan substitutions.
    if diet == "vegan":
        name = VEGAN_SWAPS.get(name, name)
    if diet == "vegetarian" and NON_VEG_PATTERN.search(name):
        return None
    if diet == "vegan" and (NON_VEG_PATTERN.search(name) or (DAIRY_PATTERN.search(name) and not re.search(r"\bcoconut yogurt\b", name, re.I))):
        return None
    return name


def meals_for_diet(meals, diet):
    # List comprehension filters the list; a set is used later to avoid duplicate picks.
    return [candidate for meal in meals if (candidate := meal_for_diet(meal, diet))]


# Name-based screening only: the project currently stores meal names, not full ingredients.
# These groups deliberately include common synonyms and closely related food names.
ALLERGEN_PATTERNS = {
    "egg": r"\b(egg|eggs|eggwhite|omelette|omelet|mayonnaise|mayo)\b",
    "fish": r"\b(fish|salmon|tuna|cod|sardine|anchovy|trout|mackerel|haddock|tilapia)\b",
    "shellfish": r"\b(shellfish|shrimp|prawn|crab|lobster|crayfish|clam|mussel|oyster|scallop)\b",
    "peanut": r"\b(peanut|peanuts|groundnut|groundnuts)\b",
    "tree nut": r"\b(almond|almonds|cashew|cashews|walnut|walnuts|pistachio|pistachios|pecan|pecans|hazelnut|hazelnuts|macadamia|brazil nut|brazil nuts)\b",
    "nut": r"\b(nut|nuts|peanut|peanuts|almond|almonds|cashew|cashews|walnut|walnuts|pistachio|pistachios|pecan|pecans|hazelnut|hazelnuts|macadamia)\b",
    "dairy": r"\b(dairy|milk|butter|ghee|cream|cheese|paneer|yogurt|curd|whey|casein)\b",
    "milk": r"\b(milk|butter|ghee|cream|cheese|paneer|yogurt|curd|whey|casein|dairy)\b",
    "soy": r"\b(soy|soya|tofu|edamame|tempeh|miso|soybean|soybeans)\b",
    "gluten": r"\b(gluten|wheat|barley|rye|semolina|suji|sooji|maida|bread|roti|chapati|pasta|couscous|noodles)\b",
    "wheat": r"\b(wheat|bread|roti|chapati|pasta|couscous|semolina|suji|sooji|maida)\b",
    "sesame": r"\b(sesame|tahini|til)\b",
    "mustard": r"\b(mustard)\b",
    "corn": r"\b(corn|maize|cornmeal)\b",
}


def parse_allergies(allergies):
    """Accept comma/semicolon-separated foods and simple 'and' lists."""
    raw_terms = re.split(r"[,;\n]+|\s+and\s+", str(allergies or ""), flags=re.I)
    terms = []
    for raw in raw_terms:
        term = re.sub(r"\b(allerg(?:y|ies)|allergic|to|avoid|avoiding)\b", " ", raw.lower())
        term = re.sub(r"\s+", " ", term).strip(" .:-")
        if term and term not in terms:
            terms.append(term)
    return terms


def meal_matches_allergy(meal_name, allergy_terms):
    """Reject a meal when its name contains a restricted food or known synonym."""
    text = str(meal_name or "")
    for term in allergy_terms:
        # Match the canonical allergen group even when the user enters a synonym.
        canonical = term.rstrip("s") if term.endswith("s") else term
        pattern = ALLERGEN_PATTERNS.get(term) or ALLERGEN_PATTERNS.get(canonical)
        if pattern and re.search(pattern, text, re.I):
            return True
        # If a known synonym is entered (e.g. salmon), also catch that exact food.
        if re.search(r"\b" + re.escape(term) + r"s?\b", text, re.I):
            return True
        for group, group_pattern in ALLERGEN_PATTERNS.items():
            if re.search(group_pattern, term, re.I) and re.search(group_pattern, text, re.I):
                return True
    return False


def meals_without_allergens(meals, allergy_terms):
    return [meal for meal in meals if not meal_matches_allergy(meal, allergy_terms)]


def pick_meals(options, count=7):
    # Preserve order while removing duplicates, using a set for fast membership checks.
    unique_options = []
    seen = set()
    for option in options:
        if option not in seen:
            unique_options.append(option)
            seen.add(option)
    if not unique_options:
        raise ValueError("No matching meals found for this meal category and your food restrictions. Please change your preferences or allergy entries.")
    if len(unique_options) >= count:
        return random.sample(unique_options, count)
    # Repeat only meals that have already passed diet and allergy filters.
    result = unique_options.copy()
    while len(result) < count:
        result.append(random.choice(unique_options))
    random.shuffle(result)
    return result


def generate_plan(condition, diet, cuisine, allergies):
    if condition not in MEAL_POOLS:
        raise ValueError("Please select a valid health condition.")
    if diet not in {"vegetarian", "vegan", "nonveg"}:
        raise ValueError("Please select a valid dietary preference.")

    condition_pool = MEAL_POOLS[condition]
    allergy_terms = parse_allergies(allergies)
    selected = {}
    for meal_type in ("breakfast", "lunch", "dinner"):
        choices = meals_for_diet(condition_pool[meal_type], diet)
        if diet == "nonveg" and meal_type != "breakfast":
            choices = choices + NON_VEG_SWAPS
        # Apply allergy screening after all additions/substitutions, before selection.
        choices = meals_without_allergens(choices, allergy_terms)
        if not choices:
            # Try the general pool, but never bypass the user's allergy filter.
            choices = meals_without_allergens(
                meals_for_diet(MEAL_POOLS["diabetes"][meal_type], diet), allergy_terms
            )
        selected[meal_type] = pick_meals(choices)

    days = []
    for index, day in enumerate(DAYS):
        entry = {"day": day}
        for meal_type in ("breakfast", "lunch", "dinner"):
            entry[meal_type] = selected[meal_type][index]
        days.append(entry)
    return {"condition": condition, "dietPref": diet, "cuisine": cuisine, "allergies": allergies or "", "days": days}


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "message": "NutriPlan backend is running"})


@app.post("/api/generate")
def api_generate():
    data = request.get_json(silent=True) or {}
    try:
        plan = generate_plan(
            str(data.get("condition", "diabetes")),
            str(data.get("dietPref", "vegetarian")),
            str(data.get("cuisine", "indian")),
            str(data.get("allergies", ""))
        )
        return jsonify(plan)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


@app.post("/api/swap")
def api_swap():
    data = request.get_json(silent=True) or {}
    condition, diet, meal_type = data.get("condition"), data.get("dietPref"), data.get("meal")
    if condition not in MEAL_POOLS or diet not in {"vegetarian", "vegan", "nonveg"} or meal_type not in {"breakfast", "lunch", "dinner"}:
        return jsonify({"error": "Invalid meal swap request."}), 400
    allergies = str(data.get("allergies", ""))
    allergy_terms = parse_allergies(allergies)
    choices = meals_for_diet(MEAL_POOLS[condition][meal_type], diet)
    if diet == "nonveg" and meal_type != "breakfast":
        choices += NON_VEG_SWAPS
    choices = meals_without_allergens(choices, allergy_terms)
    if not choices:
        choices = meals_without_allergens(
            meals_for_diet(MEAL_POOLS["diabetes"][meal_type], diet), allergy_terms
        )
    if not choices:
        return jsonify({"error": "No matching replacement meal found for your food restrictions. Keep the current meal and change your preferences or allergy entries."}), 400
    return jsonify({"meal": random.choice(choices)})


@app.post("/api/save")
def api_save():
    data = request.get_json(silent=True) or {}
    plan = data.get("plan")
    if not isinstance(plan, dict) or not isinstance(plan.get("days"), list):
        return jsonify({"error": "Generate a meal plan before saving."}), 400
    user_email = str(data.get("email") or "local-user")[:200]
    condition = str(plan.get("condition", "unknown"))[:80]
    diet = str(plan.get("dietPref", "unknown"))[:40]
    cuisine = str(plan.get("cuisine", "unknown"))[:40]
    allergies = str(plan.get("allergies", ""))[:500]
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.execute(
            "INSERT INTO saved_plans (user_email, condition_name, diet_preference, cuisine, allergies, plan_json) VALUES (?, ?, ?, ?, ?, ?)",
            (user_email, condition, diet, cuisine, allergies, json.dumps(plan, ensure_ascii=False))
        )
        plan_id = cursor.lastrowid
        connection.commit()
    return jsonify({"saved": True, "id": plan_id, "message": "Meal plan saved to the local SQLite database."})


@app.get("/api/plans")
def api_plans():
    email = request.args.get("email", "local-user")[:200]
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT id, condition_name, diet_preference, cuisine, allergies, created_at, plan_json FROM saved_plans WHERE user_email = ? ORDER BY id DESC",
            (email,)
        ).fetchall()
    return jsonify([{
        "id": row["id"], "condition": row["condition_name"], "dietPref": row["diet_preference"],
        "cuisine": row["cuisine"], "allergies": row["allergies"], "createdAt": row["created_at"],
        "plan": json.loads(row["plan_json"])
    } for row in rows])


init_db()

if __name__ == "__main__":
    app.run(debug=True)
