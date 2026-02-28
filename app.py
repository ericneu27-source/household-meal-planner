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
# We use @st.cache_resource so it doesn't log in from scratch every time you click a button
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
except Exception as e:
    st.error(f"Error connecting to Google Sheets. Check your secrets file! Details: {e}")
    st.stop()

# --- INITIALIZE OR READ DATA ---
# 1. Schedule Data
schedule_data = schedule_ws.get_all_records()
if not schedule_data:
    # If the sheet is completely blank, build the headers and default days
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

# Organize the data so the app can read it easily
schedule_dict = {row["Day"]: {"status": row["Status"], "meal": row["Meal"], "row_index": i + 2} for i, row in enumerate(schedule_data)}

# 2. Pantry Data
pantry_data = pantry_ws.col_values(1)
if not pantry_data:
    # If the pantry tab is blank, add the header and some basics
    pantry_ws.append_row(["Item"])
    pantry_ws.append_rows([["Olive Oil"], ["Salt"], ["Black Pepper"], ["Garlic Powder"]])
    pantry_data = pantry_ws.col_values(1)

current_pantry = pantry_data[1:] # Grab everything except the "Item" header row

# --- HEADER ---
st.title("🍳 Household Meal & Grocery Planner")
st.markdown("*Configured for: 3 Adults, 2 Children | Cook Days: Tues & Thurs*")
st.divider()

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["📅 Weekly Schedule", "🛒 Grocery Lists", "🥫 Virtual Pantry"])

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
            
            if "Flexible" not in details["status"]:
                if st.button(f"Generate Recipe for {day}", key=f"btn_{day}"):
                    with st.spinner(f"Chef Gemini is planning {day}..."):
                        prompt = f"""
                        Suggest one high-protein dinner recipe (using chicken, fish, ground turkey, or a high-protein vegetarian base). 
                        It must be easy to cook. 
                        Scale the ingredient measurements exactly to feed 3 adults and 2 children for a single meal.
                        
                        Format your response exactly like this:
                        **[Recipe Title]**
                        *Brief 1-sentence description.*
                        
                        **Ingredients needed:**
                        (Provide a simple bulleted list with quantities)
                        """
                        response = model.generate_content(prompt)
                        # Type the recipe directly into the correct row and column in Google Sheets
                        schedule_ws.update_cell(details["row_index"], 3, response.text)
                        st.rerun()
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
                Do NOT include these pantry items in the final shopping list, as they already have them at home.
                
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
                Do NOT include these pantry items in the final shopping list, as they already have them at home.
                
                Format it as a clean checklist.
                Recipes:\n{cook_text}
                """
                st.subheader("The Cook's Prep List (Tues - Fri)")
                st.write(model.generate_content(prompt_cook).text)
            else:
                st.info("No meals scheduled for Tuesday through Friday yet.")

with tab3:
    st.header("🥫 Virtual Pantry")
    st.write("Slowly build your inventory. Add staples you already have so you don't over-buy.")
    
    col_add1, col_add2 = st.columns([3, 1])
    with col_add1:
        new_item = st.text_input("Add a staple to your pantry:", placeholder="e.g., Soy Sauce, Rice...")
    with col_add2:
        st.write("") 
        st.write("")
        if st.button("Add Item", use_container_width=True):
            if new_item and new_item.title() not in current_pantry:
                # Add the new item to the bottom of the Google Sheet
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
                    # Delete the row right out of the Google Sheet
                    row_to_delete = i + 2 
                    pantry_ws.delete_rows(row_to_delete)
                    st.rerun()