import streamlit as st
import google.generativeai as genai

# Set up the main page layout
st.set_page_config(page_title="Household Meal Planner", page_icon="🍳", layout="centered")

# Securely load the API key
api_key = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.5-flash')

# --- INITIALIZE THE APP'S MEMORY ---
if 'schedule' not in st.session_state:
    st.session_state.schedule = {
        "Monday": {"status": "Cook at Home", "meal": None},
        "Tuesday": {"status": "Cook Day (Prep for Tues & Wed)", "meal": None},
        "Wednesday": {"status": "Warm-Up (Prepped on Tues)", "meal": None},
        "Thursday": {"status": "Cook Day (Prep for Thurs & Fri)", "meal": None},
        "Friday": {"status": "Warm-Up (Prepped on Thurs)", "meal": None},
        "Saturday": {"status": "Leftovers / Flexible", "meal": None},
        "Sunday": {"status": "Cook at Home", "meal": None}
    }

# Initialize the Virtual Pantry memory
if 'pantry' not in st.session_state:
    # We will start you off with a few standard kitchen basics
    st.session_state.pantry = ["Olive Oil", "Salt", "Black Pepper", "Garlic Powder"]

# --- HEADER ---
st.title("🍳 Household Meal & Grocery Planner")
st.markdown("*Configured for: 3 Adults, 2 Children | Cook Days: Tues & Thurs*")
st.divider()

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["📅 Weekly Schedule", "🛒 Grocery Lists", "🥫 Virtual Pantry"])

with tab1:
    st.header("This Week's Schedule")
    
    for day, details in st.session_state.schedule.items():
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
                        st.session_state.schedule[day]["meal"] = response.text
                        st.rerun()
        st.divider()

with tab2:
    st.header("🛒 Smart Shopping Lists")
    
    if st.button("Compile Grocery Lists"):
        with st.spinner("Chef Gemini is organizing the aisles..."):
            
            household_text = ""
            for day in ["Sunday", "Monday"]:
                if st.session_state.schedule[day]["meal"]:
                    household_text += f"\n--- {day} ---\n{st.session_state.schedule[day]['meal']}"
            
            cook_text = ""
            for day in ["Tuesday", "Wednesday", "Thursday", "Friday"]:
                if st.session_state.schedule[day]["meal"]:
                    cook_text += f"\n--- {day} ---\n{st.session_state.schedule[day]['meal']}"
            
            if household_text:
                prompt_house = f"""
                Extract all ingredients from these recipes and combine them into a single grocery list. 
                Group the items by standard grocery store aisles. Combine quantities where possible.
                
                CRITICAL INSTRUCTION: Here is the user's current pantry inventory: {', '.join(st.session_state.pantry)}.
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
                
                CRITICAL INSTRUCTION: Here is the user's current pantry inventory: {', '.join(st.session_state.pantry)}.
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
    
    # 1. The input area to add a new item
    col_add1, col_add2 = st.columns([3, 1])
    with col_add1:
        new_item = st.text_input("Add a staple to your pantry:", placeholder="e.g., Soy Sauce, Rice...")
    with col_add2:
        st.write("") # Spacing to align the button
        st.write("")
        if st.button("Add Item", use_container_width=True):
            if new_item and new_item not in st.session_state.pantry:
                st.session_state.pantry.append(new_item.title())
                st.rerun()
                
    st.divider()
    
    # 2. Displaying the current inventory
    st.subheader("Current Stock")
    if not st.session_state.pantry:
        st.info("Your pantry is currently empty.")
    else:
   # Loop through the memory and create a row for each item
        for item in st.session_state.pantry:
            col_item1, col_item2 = st.columns([4, 1])
            
            with col_item1:
                st.write(f"✅ **{item}**")
                
            with col_item2:
                if st.button("Use Up", key=f"del_{item}"):
                    st.session_state.pantry.remove(item)
                    st.rerun()