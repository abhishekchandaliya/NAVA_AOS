import streamlit as st
from supabase import create_client, Client
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(page_title="AOS | Architect's Operating System", layout="wide")

# --- Database Connection ---
@st.cache_resource
def init_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# --- Sidebar Navigation ---
st.sidebar.title("AOS Navigation")
page = st.sidebar.radio("Go to", ["Principal Dashboard", "Assign Task"])

# --- Page: Principal Dashboard ---
if page == "Principal Dashboard":
    st.title("Principal Dashboard")
    
    # Fetch projects data
    try:
        projects_response = supabase.table("projects").select("*").execute()
        projects_data = projects_response.data
        
        if projects_data:
            # Calculate metrics (Assuming there's a 'status' column, otherwise just counts total)
            total_projects = len(projects_data)
            active_projects = len([p for p in projects_data if p.get('status', 'Active').lower() == 'active'])
            
            # Display Metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(label="Total Active Projects", value=active_projects)
            with col2:
                st.metric(label="Total Projects (All-time)", value=total_projects)
                
            st.divider()
            st.subheader("Project Directory")
            # Display as a clean dataframe
            st.dataframe(projects_data, use_container_width=True, hide_index=True)
        else:
            st.info("No projects found in the database. Add some projects to see them here.")
            
    except Exception as e:
        st.error(f"Error fetching project data: {e}")

# --- Page: Assign Task ---
elif page == "Assign Task":
    st.title("Assign a Task")
    
    # Fetch necessary data for dropdowns
    try:
        projects_response = supabase.table("projects").select("id, project_code").execute()
        team_response = supabase.table("team_members").select("id, full_name").execute()
        
        projects_data = projects_response.data
        team_data = team_response.data
        
        # Create mapping dictionaries (Display Name -> Database ID)
        project_options = {p['project_code']: p['id'] for p in projects_data} if projects_data else {}
        team_options = {t['full_name']: t['id'] for t in team_data} if team_data else {}
        
    except Exception as e:
        st.error(f"Error loading form data: {e}")
        project_options, team_options = {}, {}

    if not project_options or not team_options:
        st.warning("Ensure you have at least one project and one team member in your database before assigning tasks.")
    else:
        # Create the form
        with st.form("task_assignment_form", clear_on_submit=True):
            st.subheader("Task Details")
            
            # Dropdowns using the keys of our mapping dictionaries
            selected_project = st.selectbox("Select Project", options=list(project_options.keys()))
            selected_member = st.selectbox("Assign To", options=list(team_options.keys()))
            
            task_description = st.text_area("Task Description", placeholder="e.g., Issue GFC drawings for masonry work...")
            deadline = st.date_input("Deadline", min_value=datetime.today())
            
            submitted = st.form_submit_button("Assign Task", type="primary")
            
            if submitted:
                if not task_description.strip():
                    st.error("Please provide a task description.")
                else:
                    # Retrieve the actual IDs using the mapping dictionaries
                    project_id = project_options[selected_project]
                    member_id = team_options[selected_member]
                    
                    # Prepare data payload
                    new_task = {
                        "project_id": project_id,
                        "team_member_id": member_id,
                        "description": task_description,
                        "deadline": deadline.isoformat(),
                        "status": "Pending" # Default status
                    }
                    
                    # Insert into Supabase
                    try:
                        supabase.table("tasks").insert(new_task).execute()
                        st.success(f"Task successfully assigned to {selected_member} for project {selected_project}!")
                    except Exception as e:
                        st.error(f"Failed to assign task: {e}")