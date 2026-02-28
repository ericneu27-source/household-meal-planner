import streamlit as st
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
import json
import random

# --- SETUP ---
st.set_page_config(page_title="Household Meal Planner", page_icon="🍳", layout="centered")

if 'voila_pending' not in st.session_state:
    st.session_state.voila_pending = False
if 'voila_new_cart' not in st.session_state:
    st.session_state.voila_new_cart = []
if 'voila_item' not in st.session_state:
    st.session_state.voila_item = ""

api_key = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.5-flash')

# --- GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_google_sheet():
    creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_url(st.secrets["SHEET_URL"])

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_all_records(sheet_name):
    client = get_google_sheet()
    return client.worksheet(sheet_name).get_all_records()

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_col_values(sheet_name, col_num):
    client = get_google_sheet()
    return client.worksheet(sheet_name).col_values(col_num)

try:
    db = get_google_sheet()
    schedule_ws = db.worksheet("Schedule")
    pantry_ws = db.worksheet("Pantry")
    
    try:
        vault_ws = db.worksheet("Recipe Vault")
    except:
        vault_ws = db.add_worksheet(title="Recipe Vault", rows="100", cols="3")
        vault_ws.append_row(["Meal Title", "Recipe", "Rating"])
        
    try:
        voila_ws = db.worksheet("Voila")
    except:
        voila_ws = db.add_worksheet(title="Voila", rows="100", cols="1")
        voila_ws.append_row(["Item"])
        
    try:
        settings_ws = db.worksheet("Settings")
    except:
        settings_ws = db.add_worksheet(title="Settings", rows="10", cols="2")
        settings_ws.append_row(["Setting", "Value"])
        settings_ws.append_row(["Diet & Portions", "High-protein dinner recipes (using chicken, fish, ground turkey, or a high-protein vegetarian base). Scale all ingredient measurements to feed exactly 3 adults and 2 children for a single meal."])

    try:
        groceries_ws = db.worksheet("Groceries")
    except:
        groceries_ws = db.add_worksheet(title="Groceries", rows="200", cols="2")
        groceries_ws.append_row(["List Type", "Item"])

except Exception as e:
    st.error(f"Error connecting to Google Sheets. Check your secrets file! Details: {e}")
    st.stop()

# --- INITIALIZE OR READ DATA ---
schedule_data = fetch_all_records("Schedule")
if not schedule_data:
    schedule_ws.append_row(["Day", "Status", "Meal"])
    defaults = [
        ["Monday", "Cook at Home", ""],
        ["Tuesday", "Cook Day 1 (Makes Tues & Wed meals)", ""],
        ["Wednesday", "Prepped on Tuesday", ""],
        ["Thursday", "Cook Day 2 (Makes Thurs & Fri meals)", ""],
        ["Friday", "Prepped on Thursday", ""],
        ["Saturday", "Leftovers / Flexible", ""],
        ["Sunday", "Cook at Home", ""]
    ]
    schedule_ws.append_rows(defaults)
    fetch_all_records.clear("Schedule")
    schedule_data = fetch_all_records("Schedule")

schedule_dict = {row["Day"]: {"status": row["Status"], "meal": row["Meal"], "row_index": i + 2} for i, row in enumerate(schedule_data)}

pantry_data = fetch_col_values("Pantry", 1)
if not pantry_data:
    pantry_ws.append_row(["Item"])
    pantry_ws.append_rows([["Olive Oil"], ["Salt"], ["Black Pepper"], ["Garlic Powder"]])
    fetch_col_values.clear("Pantry", 1)
    pantry_data = fetch_col_values("Pantry", 1)

current_pantry = pantry_data[1:]

vault_data = fetch_all_records("Recipe Vault")
vault_dict = {
    str(row["Meal Title"]): {
        "recipe": str(row["Recipe"]), 
        "rating": str(row["Rating"]), 
        "row_index": i + 2
    } for i, row in enumerate(vault_data) if row.get("Meal Title")
}

loved_meals = [title for title, data in vault_dict.items() if data["rating"] in ["4", "5"]]
banned_meals = [title for title, data in vault_dict.items() if data["rating"] in ["1", "2"]]
loved_str = ", ".join(loved_meals) if loved_meals else "None yet"
banned_str = ", ".join(banned_meals) if banned_meals else "None yet"

voila_data = fetch_col_values("Voila", 1)
if not voila_data:
    voila_ws.append_row(["Item"])
    fetch_col_values.clear("Voila", 1)
    voila_data = fetch_col_values("Voila", 1)
current_voila = voila_data[1:]

settings_data = fetch_all_records("Settings")
diet_prefs = "High-protein recipes."
for row in settings_data:
    if row.get("Setting") == "Diet & Portions":
        diet_prefs = str(row.get("Value"))

groceries_data = fetch_all_records("Groceries")

# --- HEADER ---
col_h1, col_h2 = st.columns([4, 1])
with col_h1:
    st.title("🍳 Household Meal Planner")
with col_h2:
    st.write("") 
    if st.button("🔄 Sync App", use_container_width=True):
        fetch_all_records.clear()
        fetch_col_values.clear()
        st.rerun()
        
st.divider()

# --- TABS ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📅 Schedule", "🛒 Groceries", "🥫 Pantry", "⭐ Vault", "🚚 Voila", "⚙️ Settings"])

with tab1:
    if st.button("✨ Auto-Fill Magic Week", type="primary", use_container_width=True):
        with st.spinner("Chef Gemini is designing your perfect week (this takes about 10 seconds)..."):
            
            prep_days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            new_meals = {}
            
            chosen_favs = random.sample(loved_meals, min(2, len(loved_meals)))
            
            random.shuffle(prep_days)
            fav_days = prep_days[:len(chosen_favs)]
            ai_days = prep_days[len(chosen_favs):]
            
            for i, day in enumerate(fav_days):
                fav_title = chosen_favs[i]
                fav_data = vault_dict[fav_title]
                new_meals[day] = f"**{fav_title}**\n*(Vault Rating: {fav_data['rating']} Stars)*\n\n**Ingredients needed:**\n{fav_data['recipe']}"
            
            for day in ai_days:
                prompt = f"""
                Suggest a dinner recipe based EXACTLY on these family preferences: {diet_prefs}.
                
                CRITICAL INSTRUCTIONS:
                - Do NOT suggest these 1 and 2-star banned meals: {banned_str}
                - Provide a fresh, creative idea.
                
                Format your response exactly like this:
                **[Recipe Title]**
                *Brief 1-sentence description.*
                
                **Ingredients needed:**
                (Provide a simple bulleted list with quantities)
                """
                response = model.generate_content(prompt)
                new_meals[day] = response.text
                
            new_meals["Saturday"] = "**Flexible / Clean out the fridge!**"
            
            for day, meal_text in new_meals.items():
                if day in schedule_dict:
                    schedule_ws.update_cell(schedule_dict[day]["row_index"], 3, meal_text)
            
            fetch_all_records.clear("Schedule")
            st.rerun()

    st.write("---")
    
    st.header("This Week's Schedule")
    for day, details in schedule_dict.items():
        col1, col2 = st.columns([1, 3])
        with col1:
            st.subheader(day)
        with col2:
            if "Cook Day" in details["status"]:
                st.info(f"🧑‍🍳 **{details['status']}**")
            elif "Warm-Up" in details["status"] or "Prepped" in details["status"]:
                st.warning(f"♨️ **{details['status']}**")
            elif "Flexible" in details["status"]:
                st.error(f"🥡 **{details['status']}**")
            else:
                st.success(f"🍽️ **{details['status']}**")
            
            if details["meal"]:
                st.write(details["meal"])
                
                # FIXED: Line-by-line parsing logic
                with st.expander("✏️ Line-by-Line Edit & AI Substitute"):
                    lines = details["meal"].split("\n")
                    new_lines = []
                    
                    for idx, line in enumerate(lines):
                        stripped = line.strip()
                        
                        # Identify exactly what kind of line this is
                        is_bold_header = stripped.startswith("**")
                        # It is an italic description ONLY if it starts with an asterisk but NO space follows it
                        is_italic_desc = stripped.startswith("*") and not stripped.startswith("**") and not stripped.startswith("* ")
                        
                        if stripped == "" or is_bold_header or is_italic_desc:
                            st.markdown(line)
                            new_lines.append(line)
                        else:
                            col_e1, col_e2 = st.columns([4, 1])
                            with col_e1:
                                edited_line = st.text_input(f"Edit {idx}", value=line, key=f"edit_line_{day}_{idx}", label_visibility="collapsed")
                                new_lines.append(edited_line)
                            with col_e2:
                                if st.button("🪄 AI Sub", key=f"sub_btn_{day}_{idx}"):
                                    with st.spinner("Swapping..."):
                                        title = next((l for l in lines if "**" in l), "the recipe").replace("**", "")
                                        prompt = f"""
                                        I am cooking {title}. I need a direct ingredient substitution for '{line}'. 
                                        Please provide JUST the replacement ingredient and its measurement, formatted exactly like the original line. 
                                        Do not use introductory text.
                                        """
                                        new_ingredient = model.generate_content(prompt).text.strip().lstrip("- ").lstrip("* ")
                                        
                                        # Keep the bullet format consistent with the original line
                                        if line.startswith("* "):
                                            new_ingredient = f"* {new_ingredient}"
                                        elif line.startswith("- "):
                                            new_ingredient = f"- {new_ingredient}"
                                            
                                        lines[idx] = new_ingredient
                                        updated_meal = "\n".join(lines)
                                        schedule_ws.update_cell(details["row_index"], 3, updated_meal)
                                        fetch_all_records.clear("Schedule")
                                        st.rerun()
                                        
                    st.write("")
                    if st.button("💾 Save Manual Edits", key=f"save_manual_{day}", use_container_width=True):
                        updated_meal = "\n".join(new_lines)
                        if updated_meal != details["meal"]:
                            schedule_ws.update_cell(details["row_index"], 3, updated_meal)
                            fetch_all_records.clear("Schedule")
                            st.rerun()
                
                with st.expander("⭐ Rate & Save this Meal"):
                    col_r1, col_r2 = st.columns([2, 1])
                    with col_r1:
                        meal_name = st.text_input("Name this meal:", key=f"name_{day}")
                    with col_r2:
                        rating = st.selectbox("Rating:", ["5 (Love)", "4 (Like)", "3 (Okay)", "2 (Dislike)", "1 (Never Again)"], key=f"rate_{day}")
                    
                    if st.button("Save to Vault", key=f"save_{day}", use_container_width=True):
                        if meal_name:
                            numeric_rating = rating[0] 
                            vault_ws.append_row([meal_name, details["meal"], numeric_rating])
                            fetch_all_records.clear("Recipe Vault")
                            st.success(f"Saved {meal_name} with {numeric_rating} stars!")
                            st.rerun()
            
            if "Flexible" not in details["status"]:
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button(f"✨ Single Generate", key=f"btn_{day}", use_container_width=True):
                        with st.spinner(f"Chef Gemini is planning {day}..."):
                            prompt = f"""
                            Suggest a dinner recipe based EXACTLY on these family preferences: {diet_prefs}.
                            
                            CRITICAL INSTRUCTIONS:
                            - Here are the family's 4 and 5-star meals. You are highly encouraged to suggest one of these, or a very close variation: {loved_str}
                            - Do NOT suggest these 1 and 2-star banned meals: {banned_str}
                            
                            Format your response exactly like this:
                            **[Recipe Title]**
                            *Brief 1-sentence description.*
                            
                            **Ingredients needed:**
                            (Provide a simple bulleted list with quantities)
                            """
                            response = model.generate_content(prompt)
                            schedule_ws.update_cell(details["row_index"], 3, response.text)
                            fetch_all_records.clear("Schedule")
                            st.rerun()
                
                with col_btn2:
                    if vault_dict:
                        fav_options = ["-- Pick from Vault --"] + list(vault_dict.keys())
                        selected_fav = st.selectbox("Or choose from Vault:", fav_options, key=f"sel_{day}", label_visibility="collapsed")
                        
                        if selected_fav != "-- Pick from Vault --":
                            formatted_fav = f"**{selected_fav}**\n*(Vault Rating: {vault_dict[selected_fav]['rating']} Stars)*\n\n**Ingredients needed:**\n{vault_dict[selected_fav]['recipe']}"
                            schedule_ws.update_cell(details["row_index"], 3, formatted_fav)
                            fetch_all_records.clear("Schedule")
                            st.rerun()
                    else:
                        st.write("*(Rate meals to build Vault)*")
        st.divider()

with tab2:
    st.header("🛒 Smart Shopping Lists")
    
    if st.button("✨ Compile AI Grocery Lists", type="primary", use_container_width=True):
        with st.spinner("Chef Gemini is clearing the old lists and organizing the aisles..."):
            
            household_text = "".join([f"\n{schedule_dict[day]['meal']}" for day in ["Sunday", "Monday"] if schedule_dict[day]["meal"]])
            cook_text_1 = "".join([f"\n{schedule_dict[day]['meal']}" for day in ["Tuesday", "Wednesday"] if schedule_dict[day]["meal"]])
            cook_text_2 = "".join([f"\n{schedule_dict[day]['meal']}" for day in ["Thursday", "Friday"] if schedule_dict[day]["meal"]])
            
            pantry_string = ", ".join(current_pantry)
            
            groceries_ws.clear()
            groceries_ws.append_row(["List Type", "Item"])
            rows_to_add = []

            system_prompt = f"""
            Extract all ingredients from the following recipes. Combine quantities where possible.
            CRITICAL INSTRUCTION: The user already has these pantry items: {pantry_string}. DO NOT include them.
            
            FORMATTING RULES:
            1. Output a NEWLINE-SEPARATED list. 
            2. Put each completely separate ingredient on its own line.
            3. NEVER split a single ingredient across multiple lines. "2 lbs Boneless, Skinless Salmon" MUST be on one single line.
            4. You MAY use commas within an ingredient line.
            5. Do not use bullet points, asterisks, or introductory text.
            
            Example output: 
            2 lbs Ground Turkey
            1 head Garlic, Minced
            3 Bell Peppers
            """

            if household_text:
                resp = model.generate_content(system_prompt + "\nRecipes:\n" + household_text)
                items = [x.strip().title().lstrip("- ").lstrip("* ") for x in resp.text.split("\n") if x.strip()]
                rows_to_add.extend([["🏡 Household (Sun/Mon)", item] for item in items])
                
            if cook_text_1:
                resp = model.generate_content(system_prompt + "\nRecipes:\n" + cook_text_1)
                items = [x.strip().title().lstrip("- ").lstrip("* ") for x in resp.text.split("\n") if x.strip()]
                rows_to_add.extend([["🧑‍🍳 Cook List 1 (Tues/Wed)", item] for item in items])
                
            if cook_text_2:
                resp = model.generate_content(system_prompt + "\nRecipes:\n" + cook_text_2)
                items = [x.strip().title().lstrip("- ").lstrip("* ") for x in resp.text.split("\n") if x.strip()]
                rows_to_add.extend([["🧑‍🍳 Cook List 2 (Thurs/Fri)", item] for item in items])
                
            if rows_to_add:
                groceries_ws.append_rows(rows_to_add)
            
            fetch_all_records.clear("Groceries")
            st.success("Lists successfully generated and synced to all devices!")
            st.rerun()
            
    st.divider()

    if not groceries_data:
        st.info("Your grocery lists are empty. Hit the big compile button to generate them!")
    else:
        list_categories = ["🏡 Household (Sun/Mon)", "🧑‍🍳 Cook List 1 (Tues/Wed)", "🧑‍🍳 Cook List 2 (Thurs/Fri)"]
        
        for category in list_categories:
            items_in_category = [(i, row) for i, row in enumerate(groceries_data) if row["List Type"] == category]
            
            if items_in_category:
                st.subheader(category)
                for original_index, row in items_in_category:
                    col_g1, col_g2 = st.columns([4, 1])
                    with col_g1:
                        st.write(f"🛒 {row['Item']}")
                    with col_g2:
                        if st.button("To Pantry", key=f"buy_{original_index}"):
                            clean_item = row['Item'].replace("*", "").strip().title()
                            if clean_item and clean_item not in current_pantry:
                                pantry_ws.append_row([clean_item])
                                fetch_col_values.clear("Pantry", 1)
                            groceries_ws.delete_rows(original_index + 2)
                            fetch_all_records.clear("Groceries")
                            st.rerun()
                st.write("---")

    st.subheader("➕ Add an Extra Item")
    st.write("*(Note: Compiling the AI lists will reset this tab, so add your manual items after you compile!)*")
    
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        manual_item = st.text_input("Item name:", placeholder="e.g., 1 Bag of Apples")
    with col_m2:
        list_options = ["🏡 Household (Sun/Mon)", "🧑‍🍳 Cook List 1 (Tues/Wed)", "🧑‍🍳 Cook List 2 (Thurs/Fri)"]
        target_list = st.selectbox("Which list?", list_options)
        
    if st.button("Add Item to List", use_container_width=True):
        if manual_item:
            clean_manual = manual_item.replace("*", "").strip().title()
            groceries_ws.append_row([target_list, clean_manual])
            fetch_all_records.clear("Groceries")
            st.rerun()

with tab3:
    st.header("🥫 Virtual Pantry")
    col_add1, col_add2 = st.columns([3, 1])
    with col_add1:
        new_item = st.text_input("Add a staple to your pantry:", placeholder="e.g., Soy Sauce, Rice...")
    with col_add2:
        st.write("") 
        st.write("")
        if st.button("Add Item", use_container_width=True):
            if new_item:
                clean_item = new_item.replace("*", "").strip().title()
                if clean_item and clean_item not in current_pantry:
                    pantry_ws.append_row([clean_item])
                    fetch_col_values.clear("Pantry", 1)
                    st.rerun()
                
    st.divider()
    
    st.subheader("Current Stock")
    if not current_pantry:
        st.info("Your pantry is currently empty.")
    else:
        for i, item in enumerate(current_pantry):
            col_item1, col_item2 = st.columns([4, 1])
            with col_item1:
                st.write(f"✅ {item}")
            with col_item2:
                if st.button("Use Up", key=f"del_pantry_{item}_{i}"):
                    row_to_delete = i + 2 
                    pantry_ws.delete_rows(row_to_delete)
                    fetch_col_values.clear("Pantry", 1)
                    st.rerun()

with tab4:
    st.header("⭐ Recipe Vault")
    st.write("Your historical ratings inform the AI. 4 and 5-star meals will be suggested often. 1 and 2-star meals are banned.")
    
    with st.expander("➕ Manually Add a Known Favorite"):
        new_title = st.text_input("Meal Name", placeholder="e.g., Turkey Chili")
        new_recipe = st.text_area("Ingredients (List quantities for the Grocery Compiler!)", placeholder="- 1 lb Ground Turkey\n- 1 can Kidney Beans\n...")
        if st.button("Save 5-Star Favorite", use_container_width=True):
            if new_title and new_recipe:
                vault_ws.append_row([new_title, new_recipe, "5"])
                fetch_all_records.clear("Recipe Vault")
                st.rerun()
                
    st.divider()
    
    if not vault_dict:
        st.info("Your vault is empty. Rate meals on the Schedule tab to build your database!")
    else:
        for title, data in vault_dict.items():
            stars = "⭐" * int(data["rating"])
            with st.expander(f"{stars} {title}"):
                st.write("**Ingredients / Portions:**")
                edited_vault_recipe = st.text_area("Adjust portions here so future uses are perfectly scaled:", value=data["recipe"], height=150, key=f"edit_vault_{title}")
                
                if st.button("Save Portion Edits", key=f"save_portion_{title}"):
                    if edited_vault_recipe != data["recipe"]:
                        vault_ws.update_cell(data["row_index"], 2, edited_vault_recipe)
                        fetch_all_records.clear("Recipe Vault")
                        st.rerun()
                
                st.divider()
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    rating_options = ["5 (Love)", "4 (Like)", "3 (Okay)", "2 (Dislike)", "1 (Never Again)"]
                    current_val = str(data["rating"])
                    default_idx = next((i for i, opt in enumerate(rating_options) if opt.startswith(current_val)), 0)
                    new_rating = st.selectbox("Change Rating:", rating_options, index=default_idx, key=f"edit_rate_{title}")
                with col_u2:
                    st.write("")
                    st.write("")
                    if st.button("Update Rating", key=f"upd_vault_{title}", use_container_width=True):
                        if new_rating[0] != current_val:
                            vault_ws.update_cell(data["row_index"], 3, new_rating[0])
                            fetch_all_records.clear("Recipe Vault")
                            st.rerun()
                
                if st.button("Delete from Vault", key=f"del_vault_{title}"):
                    vault_ws.delete_rows(data["row_index"])
                    fetch_all_records.clear("Recipe Vault")
                    st.rerun()

with tab5:
    st.header("🚚 Voila Delivery List")
    st.write("Manage your weekly Sobeys order. Add an item, and Chef Gemini will automatically combine matching quantities!")
    
    if st.session_state.voila_pending:
        st.warning(f"⚠️ **Duplicate Detected!** It looks like you already have something similar to **'{st.session_state.voila_item}'** in your cart.")
        
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            if st.button("✅ Combine Them", use_container_width=True):
                voila_ws.clear()
                voila_ws.append_row(["Item"])
                rows_to_add = [[item] for item in st.session_state.voila_new_cart]
                if rows_to_add:
                    voila_ws.append_rows(rows_to_add)
                fetch_col_values.clear("Voila", 1)
                st.session_state.voila_pending = False
                st.rerun()
        with col_c2:
            if st.button("➕ Add Separately", use_container_width=True):
                voila_ws.append_row([st.session_state.voila_item])
                fetch_col_values.clear("Voila", 1)
                st.session_state.voila_pending = False
                st.rerun()
        with col_c3:
            if st.button("❌ Cancel", use_container_width=True):
                st.session_state.voila_pending = False
                st.rerun()
        st.divider()
        
    else:
        col_vadd1, col_vadd2 = st.columns([3, 1])
        with col_vadd1:
            new_voila = st.text_input("Add an item to your Voila list:", placeholder="e.g., 2 boxes of Cheerios, 3 Apples...")
        with col_vadd2:
            st.write("") 
            st.write("")
            if st.button("Smart Add", use_container_width=True):
                if new_voila:
                    with st.spinner("Checking cart for duplicates..."):
                        clean_voila = new_voila.replace("*", "").strip().title()
                        
                        if not current_voila:
                            voila_ws.append_row([clean_voila])
                            fetch_col_values.clear("Voila", 1)
                            st.rerun()
                        else:
                            cart_string = "\n".join(current_voila)
                            prompt = f"""
                            Here is my current grocery cart:
                            {cart_string}
                            
                            I want to add this new item: "{clean_voila}"
                            
                            INSTRUCTIONS:
                            1. Does the new item match (or is it essentially the same as) an item already in the cart? Answer exactly "DUPLICATE: YES" or "DUPLICATE: NO" on the first line.
                            2. If YES, combine their quantities mathematically. If NO, simply add the new item to the bottom of the list.
                            3. From the second line onwards, provide the final updated cart as a newline-separated list with NO bullet points, asterisks, or extra text. Capitalize each item.
                            """
                            response = model.generate_content(prompt)
                            lines = response.text.strip().split("\n")
                            
                            is_duplicate = "YES" in lines[0].upper()
                            updated_cart = [x.strip().title().lstrip("- ").lstrip("* ") for x in lines[1:] if x.strip()]
                            
                            if is_duplicate:
                                st.session_state.voila_pending = True
                                st.session_state.voila_item = clean_voila
                                st.session_state.voila_new_cart = updated_cart
                                st.rerun()
                            else:
                                voila_ws.append_row([clean_voila])
                                fetch_col_values.clear("Voila", 1)
                                st.rerun()
                
    st.divider()
    
    st.subheader("Current Cart")
    if not current_voila:
        st.info("Your Voila list is empty.")
    else:
        for i, item in enumerate(current_voila):
            col_vitem1, col_vitem2 = st.columns([4, 1])
            with col_vitem1:
                st.write(f"📦 {item}")
            with col_vitem2:
                if st.button("Remove", key=f"del_voila_{item}_{i}"):
                    row_to_delete = i + 2 
                    voila_ws.delete_rows(row_to_delete)
                    fetch_col_values.clear("Voila", 1)
                    st.rerun()

with tab6:
    st.header("⚙️ App Settings")
    st.write("Tell Chef Gemini exactly how to cook for your family. Update this anytime your diet or portion sizes change!")
    
    new_diet_prefs = st.text_area("Dietary Preferences & Portion Rules:", value=diet_prefs, height=150)
    
    if st.button("Save Settings", type="primary"):
        if new_diet_prefs != diet_prefs:
            settings_ws.update_cell(2, 2, new_diet_prefs)
            fetch_all_records.clear("Settings")
            st.success("Settings saved! Chef Gemini will use these rules for all future meals.")
            st.rerun()