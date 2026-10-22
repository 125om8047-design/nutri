NUTRIPLAN ALLERGY-FILTER PATCH

Files included:
- app.py: filters generated plans and meal swaps before selecting meals; supports comma, semicolon, newline, and simple 'and' separated restrictions.
- templates/index.html: filters the recipe library by recipe name and ingredient list; blocks opening a recipe if it matches a restriction.

How to apply:
1. Make a backup of your existing project folder.
2. Replace your existing app.py with this app.py.
3. Replace your existing templates/index.html with templates/index.html from this patch.
4. Keep your existing meal_pools.json, requirements.txt, database, and other project files unchanged.
5. Stop the Flask server (Ctrl+C) and start it again using your existing run method.
6. Refresh the website with Ctrl+F5.
7. Test with allergies: fish. Check the generated plan, Swap Meal, and recipe library. Also test: egg, dairy; or peanut and sesame.

Important limitation:
- The meal pool used for the generated weekly plan stores meal names rather than full ingredient lists, so the backend can reliably filter foods visible in the meal name and known synonyms, but cannot detect a hidden ingredient not represented in that name.
- The recipe library is checked against its stored ingredient lists.
- This is not a guarantee against cross-contact or unlisted ingredients. For serious allergies, verify full ingredient labels and preparation conditions.
