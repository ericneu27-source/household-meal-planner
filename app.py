import streamlit as st
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
import json

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

# NEW: We are now tracking the exact "row_index" for the vault meals too!
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

# --- HEADER ---
col_h1, col_h2 = st.columns([4, 1])
with col_h1:
    st.title("🍳 Household Meal & Grocery Planner")
    st.markdown("*Configured for: 3 Adults, 2 Children | Cook Days: Tues & Thurs*")
with col_h2:
    st.write("") 
    if st.button("🔄 Sync App", use_container_width=True):
        st.rerun()
        
st.divider()

# --- TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["📅 Weekly Schedule", "🛒 Grocery Lists", "🥫 Virtual Pantry", "⭐ Recipe Vault"])

with tab1:
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
                            st.success(f"Saved {meal_name} with {numeric_rating} stars!")
                            st.rerun()
            
            if "Flexible" not in details["status"]:
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button(f"✨ AI Generate", key=f"btn_{day}", use_container_width=True):
                        with st.spinner(f"Chef Gemini is planning {day}..."):
                            prompt = f"""
                            Suggest one high-protein dinner recipe (using chicken, fish, ground turkey, or a high-protein vegetarian base). 
                            Scale the ingredient measurements exactly to feed 3 adults and 2 children for a single meal.
                            
                            CRITICAL PREFERENCES:
                            - Your goal is to suggest highly rated meals frequently. 
                            - Here are the family's 4 and 5-star meals. You are highly encouraged to suggest one of these, or a very close variation: {loved_str}
                            - Here are the family's 1 and 2-star meals. DO NOT suggest these or anything similar: {banned_str}
                            
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
            
            cook_text = ""
            for day in ["Tuesday", "Wednesday", "Thursday", "Friday"]:
                if schedule_dict[day]["meal"]:
                    cook_text += f"\n--- {day} ---\n{schedule_dict[day]['meal']}"
            
            pantry_string = ", ".join(current_pantry)

            if household_text:
                prompt_house = f"""
                Extract all ingredients from these recipes and combine them into a single grocery list. 
                Group the items by standard grocery store aisles. Combine quantities where possible.
                
                CRITICAL INSTRUCTION: Here is the user's current pantry inventory: {pantry_string}.
                Do NOT include these pantry items in the final shopping list.
                
                Format it as a clean checklist.
                Recipes:\n{household_text}
                """
                st.subheader("Your Master Household List (Sun & Mon)")
                st.write(model.generate_content(prompt_house).text)
            else:
                st.info("No meals scheduled for Sunday or Monday yet.")
                
            st.divider()
            
            if cook_text:
                prompt_cook = f"""
                Extract all ingredients from these recipes and combine them into a single grocery list. 
                Group the items by standard grocery store aisles. Combine quantities where possible.
                
                CRITICAL INSTRUCTION: Here is the user's current pantry inventory: {pantry_string}.
                Do NOT include these pantry items in the final shopping list.
                
                Format it as a clean checklist.
                Recipes:\n{cook_text}
                """
                st.subheader("The Cook's Prep List (Tues - Fri)")
                st.write(model.generate_content(prompt_cook).text)
            else:
                st.info("No meals scheduled for Tuesday through Friday yet.")

with tab3:
    st.header("🥫 Virtual Pantry")
    col_add1, col_add2 = st.columns([3, 1])
    with col_add1:
        new_item = st.text_input("Add a staple to your pantry:", placeholder="e.g., Soy Sauce, Rice...")
    with col_add2:
        st.write("") 
        st.write("")
        if st.button("Add Item", use_container_width=True):
            if new_item and new_item.title() not in current_pantry:
                pantry_ws.append_row([new_item.title()])
                st.rerun()
                
    st.divider()
    
    st.subheader("Current Stock")
    if not current_pantry:
        st.info("Your pantry is currently empty.")
    else:
        for i, item in enumerate(current_pantry):
            col_item1, col_item2 = st.columns([4, 1])
            with col_item1:
                st.write(f"✅ **{item}**")
            with col_item2:
                if st.button("Use Up", key=f"del_{item}"):
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
                st.write("**Ingredients:**")
                st.write(data["recipe"])
                
                st.divider()
                
                # NEW: The Rating Update Interface
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    rating_options = ["5 (Love)", "4 (Like)", "3 (Okay)", "2 (Dislike)", "1 (Never Again)"]
                    current_val = str(data["rating"])
                    # Find which text option matches their current numerical rating to display it as default
                    default_idx = next((i for i, opt in enumerate(rating_options) if opt.startswith(current_val)), 0)
                    new_rating = st.selectbox("Change Rating:", rating_options, index=default_idx, key=f"edit_rate_{title}")
                
                with col_u2:
                    st.write("")
                    st.write("")
                    if st.button("Update Rating", key=f"upd_vault_{title}", use_container_width=True):
                        if new_rating[0] != current_val:
                            # Column 3 is the Rating column in Google Sheets
                            vault_ws.update_cell(data["row_index"], 3, new_rating[0])
                            st.rerun()
                
                # Notice we updated the row deletion logic here to be perfectly precise using the exact row_index
                if st.button("Delete from Vault", key=f"del_vault_{title}"):
                    vault_ws.delete_rows(data["row_index"])
                    st.rerun()