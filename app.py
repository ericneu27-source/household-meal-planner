import streamlit as st
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
import json
import random

# --- SETUP ---
st.set_page_config(page_title="Household Meal Planner", page_icon="🍳", layout="centered")

# Securely load the AI API key
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
        
    # NEW: Create the Settings tab
    try:
        settings_ws = db.worksheet("Settings")
    except:
        settings_ws = db.add_worksheet(title="Settings", rows="10", cols="2")
        settings_ws.append_row(["Setting", "Value"])
        settings_ws.append_row(["Diet & Portions", "High-protein dinner recipes (using chicken, fish, ground turkey, or a high-protein vegetarian base). Scale all ingredient measurements to feed exactly 3 adults and 2 children for a single meal."])

except Exception as e:
    st.error(f"Error connecting to Google Sheets. Check your secrets file! Details: {e}")
    st.stop()

# --- INITIALIZE OR READ DATA ---
schedule_data = schedule_ws.get_all_records()
if not schedule_data:
    schedule_ws.append_row(["Day", "Status", "Meal"])
    defaults = [
        ["Monday", "Cook at Home", ""],
        ["Tuesday", "Cook Day (Prep for Tues & Wed)", ""],
        ["Wednesday", "Warm-Up (Prepped on Tues)", ""],
        ["Thursday", "Cook Day (Prep for Thurs & Fri)", ""],
        ["Friday", "Warm-Up (Prepped on Thurs)", ""],
        ["Saturday", "Leftovers / Flexible", ""],
        ["Sunday", "Cook at Home", ""]
    ]
    schedule_ws.append_rows(defaults)
    schedule_data = schedule_ws.get_all_records()

schedule_dict = {row["Day"]: {"status": row["Status"], "meal": row["Meal"], "row_index": i + 2} for i, row in enumerate(schedule_data)}

pantry_data = pantry_ws.col_values(1)
if not pantry_data:
    pantry_ws.append_row(["Item"])
    pantry_ws.append_rows([["Olive Oil"], ["Salt"], ["Black Pepper"], ["Garlic Powder"]])
    pantry_data = pantry_ws.col_values(1)

current_pantry = pantry_data[1:]

vault_data = vault_ws.get_all_records()
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

voila_data = voila_ws.col_values(1)
if not voila_data:
    voila_ws.append_row(["Item"])
    voila_data = voila_ws.col_values(1)
current_voila = voila_data[1:]

# NEW: Read Settings Data
settings_data = settings_ws.get_all_records()
diet_prefs = "High-protein recipes."
for row in settings_data:
    if row.get("Setting") == "Diet & Portions":
        diet_prefs = str(row.get("Value"))

# --- HEADER ---
col_h1, col_h2 = st.columns([4, 1])
with col_h1:
    st.title("🍳 Household Meal Planner")
with col_h2:
    st.write("") 
    if st.button("🔄 Sync App", use_container_width=True):
        st.rerun()
        
st.divider()

# --- TABS ---
# NEW: Added tab6 for Settings
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📅 Schedule", "🛒 Groceries", "🥫 Pantry", "⭐ Vault", "🚚 Voila", "⚙️ Settings"])

with tab1:
    # NEW: The Magic Week Button
    if st.button("✨ Auto-Fill Magic Week", type="primary", use_container_width=True):
        with st.spinner("Chef Gemini is designing your perfect week (this takes about 10 seconds)..."):
            
            prep_days = ["Sunday", "Monday", "Tuesday", "Thursday"]
            new_meals = {}
            
            # Pick up to 2 random favorites from the vault
            chosen_favs = random.sample(loved_meals, min(2, len(loved_meals)))
            
            # Shuffle the days so the favorites don't always land on Sunday/Monday
            random.shuffle(prep_days)
            fav_days = prep_days[:len(chosen_favs)]
            ai_days = prep_days[len(chosen_favs):]
            
            # 1. Populate the Favorites
            for i, day in enumerate(fav_days):
                fav_title = chosen_favs[i]
                fav_data = vault_dict[fav_title]
                new_meals[day] = f"**{fav_title}**\n*(Vault Rating: {fav_data['rating']} Stars)*\n\n**Ingredients needed:**\n{fav_data['recipe']}"
            
            # 2. Generate AI meals for the remaining days using your Custom Settings
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
                
            # 3. Handle the Cook's leftovers for Wed and Fri
            tues_title = new_meals.get("Tuesday", "Tuesday's Meal").split("\n")[0].replace("**", "")
            thurs_title = new_meals.get("Thursday", "Thursday's Meal").split("\n")[0].replace("**", "")
            
            new_meals["Wednesday"] = f"**Warm-Up:**\nLeftovers from {tues_title}"
            new_meals["Friday"] = f"**Warm-Up:**\nLeftovers from {thurs_title}"
            new_meals["Saturday"] = "**Flexible / Clean out the fridge!**"
            
            # 4. Save everything to Google Sheets
            for day, meal_text in new_meals.items():
                if day in schedule_dict:
                    schedule_ws.update_cell(schedule_dict[day]["row_index"], 3, meal_text)
                    
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
            elif "Warm-Up" in details["status"]:
                st.warning(f"♨️ **{details['status']}**")
            elif "Flexible" in details["status"]:
                st.error(f"🥡 **{details['status']}**")
            else:
                st.success(f"🍽️ **{details['status']}**")
            
            if details["meal"]:
                st.write(details["meal"])
                
                with st.expander("✏️ Modify Recipe / Ingredients"):
                    edited_recipe = st.text_area("Make your changes here:", value=details["meal"], height=200, key=f"edit_recipe_{day}")
                    if st.button("Save Edits", key=f"save_edit_{day}", use_container_width=True):
                        if edited_recipe != details["meal"]:
                            schedule_ws.update_cell(details["row_index"], 3, edited_recipe)
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
                            vault_ws.append_row([meal_name, edited_recipe, numeric_rating])
                            st.success(f"Saved {meal_name} with {numeric_rating} stars!")
                            st.rerun()
            
            if "Flexible" not in details["status"]:
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button(f"✨ Single Generate", key=f"btn_{day}", use_container_width=True):
                        with st.spinner(f"Chef Gemini is planning {day}..."):
                            # The single generate prompt now also uses your Settings!
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
                            st.rerun()
                
                with col_btn2:
                    if vault_dict:
                        fav_options = ["-- Pick from Vault --"] + list(vault_dict.keys())
                        selected_fav = st.selectbox("Or choose from Vault:", fav_options, key=f"sel_{day}", label_visibility="collapsed")
                        
                        if selected_fav != "-- Pick from Vault --":
                            formatted_fav = f"**{selected_fav}**\n*(Vault Rating: {vault_dict[selected_fav]['rating']} Stars)*\n\n**Ingredients needed:**\n{vault_dict[selected_fav]['recipe']}"
                            schedule_ws.update_cell(details["row_index"], 3, formatted_fav)
                            st.rerun()
                    else:
                        st.write("*(Rate meals to build Vault)*")
        st.divider()

with tab2:
    st.header("🛒 Smart Shopping Lists")
    if st.button("Compile Grocery Lists"):
        with st.spinner("Chef Gemini is organizing the aisles..."):
            
            household_text = ""
            for day in ["Sunday", "Monday"]:
                if schedule_dict[day]["meal"]:
                    household_text += f"\n--- {day} ---\n{schedule_dict[day]['meal']}"
            
            cook_text_tues_wed = ""
            for day in ["Tuesday", "Wednesday"]:
                if schedule_dict[day]["meal"]:
                    cook_text_tues_wed += f"\n--- {day} ---\n{schedule_dict[day]['meal']}"
                    
            cook_text_thurs_fri = ""
            for day in ["Thursday", "Friday"]:
                if schedule_dict[day]["meal"]:
                    cook_text_thurs_fri += f"\n--- {day} ---\n{schedule_dict[day]['meal']}"
            
            pantry_string = ", ".join(current_pantry)

            if household_text:
                prompt_house = f"""
                Extract all ingredients from these recipes and combine them into a single grocery list. Group items by standard grocery store aisles. Combine quantities where possible.
                CRITICAL INSTRUCTION: Here is the user's current pantry inventory: {pantry_string}. Do NOT include these pantry items in the final shopping list.
                Format it as a clean checklist.
                Recipes:\n{household_text}
                """
                st.subheader("🏡 Your Master Household List (Sun & Mon)")
                st.write(model.generate_content(prompt_house).text)
            else:
                st.info("No meals scheduled for Sunday or Monday yet.")
                
            st.divider()
            
            if cook_text_tues_wed:
                prompt_cook_1 = f"""
                Extract all ingredients from these recipes and combine them into a single grocery list. Group items by standard grocery store aisles. Combine quantities where possible.
                CRITICAL INSTRUCTION: Here is the user's current pantry inventory: {pantry_string}. Do NOT include these pantry items in the final shopping list.
                Format it as a clean checklist.
                Recipes:\n{cook_text_tues_wed}
                """
                st.subheader("🧑‍🍳 The Cook's List 1: Tuesday Shopping (Preps Tues & Wed)")
                st.write(model.generate_content(prompt_cook_1).text)
            else:
                st.info("No meals scheduled for Tuesday or Wednesday yet.")
                
            st.divider()
            
            if cook_text_thurs_fri:
                prompt_cook_2 = f"""
                Extract all ingredients from these recipes and combine them into a single grocery list. Group items by standard grocery store aisles. Combine quantities where possible.
                CRITICAL INSTRUCTION: Here is the user's current pantry inventory: {pantry_string}. Do NOT include these pantry items in the final shopping list.
                Format it as a clean checklist.
                Recipes:\n{cook_text_thurs_fri}
                """
                st.subheader("🧑‍🍳 The Cook's List 2: Thursday Shopping (Preps Thurs & Fri)")
                st.write(model.generate_content(prompt_cook_2).text)
            else:
                st.info("No meals scheduled for Thursday or Friday yet.")

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
                            st.rerun()
                
                if st.button("Delete from Vault", key=f"del_vault_{title}"):
                    vault_ws.delete_rows(data["row_index"])
                    st.rerun()

with tab5:
    st.header("🚚 Voila Delivery List")
    st.write("Manage your weekly Sobeys order for snacks, cereal, and non-perishables here.")
    
    col_vadd1, col_vadd2 = st.columns([3, 1])
    with col_vadd1:
        new_voila = st.text_input("Add an item to your Voila list:", placeholder="e.g., Cheerios, Paper Towels...")
    with col_vadd2:
        st.write("") 
        st.write("")
        if st.button("Add to Voila", use_container_width=True):
            if new_voila:
                clean_voila = new_voila.replace("*", "").strip().title()
                if clean_voila and clean_voila not in current_voila:
                    voila_ws.append_row([clean_voila])
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
                    st.rerun()

# NEW: Tab 6 for Global Settings
with tab6:
    st.header("⚙️ App Settings")
    st.write("Tell Chef Gemini exactly how to cook for your family. Update this anytime your diet or portion sizes change!")
    
    new_diet_prefs = st.text_area("Dietary Preferences & Portion Rules:", value=diet_prefs, height=150)
    
    if st.button("Save Settings", type="primary"):
        if new_diet_prefs != diet_prefs:
            # Row 2, Column 2 is where the value lives in the Settings tab
            settings_ws.update_cell(2, 2, new_diet_prefs)
            st.success("Settings saved! Chef Gemini will use these rules for all future meals.")
            st.rerun()