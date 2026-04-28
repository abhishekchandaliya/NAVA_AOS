import streamlit as st
from supabase import create_client, Client
from datetime import datetime
import pandas as pd

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
page = st.sidebar.radio("Go to", ["Principal Dashboard", "Assign Task", "Team Board"])

# --- Page 1: Principal Dashboard ---
if page == "Principal Dashboard":
    st.title("Principal Dashboard")
    
    # Fetch projects data
    try:
        projects_response = supabase.table("projects").select("*").execute()
        projects_data = projects_response.data
        
        if projects_data:
            # Calculate metrics
            total_projects = len(projects_data)
            active_projects = len([p for p in projects_data if p.get('status', 'Active').lower() == 'active'])
            
            # Display Metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(label="Total Active Projects", value=active_projects)
            with col2:
                st.metric(label="Total Projects (All-time)", value=total_projects)
                
            st.divider()
            
            # Make the Project Directory compact using an expander
            with st.expander("📂 View Project Directory"):
                st.dataframe(projects_data, use_container_width=True, hide_index=True)
        else:
            st.info("No projects found in the database. Add some projects to see them here.")
            
    except Exception as e:
        st.error(f"Error fetching project data: {e}")

    # --- Active Tasks Section with UI Upgrades ---
    st.divider()
    st.subheader("Active Tasks Dashboard")
    
    try:
        # Fetch both tasks and team members
        tasks_response = supabase.table("tasks").select("*").execute()
        team_response = supabase.table("team_members").select("id, full_name").execute()
        
        tasks_data = tasks_response.data
        team_data = team_response.data
        
        if tasks_data:
            # Create dictionary mapping: { UUID : Full Name }
            id_to_name_map = {member['id']: member['full_name'] for member in team_data} if team_data else {}
            
            # Load into a Pandas DataFrame for easy filtering and charting
            df_tasks = pd.DataFrame(tasks_data)
            
            # Map UUIDs to human names
            df_tasks["assigned_to"] = df_tasks["assigned_to"].map(lambda x: id_to_name_map.get(x, "Unknown"))
            
            # --- 1. Interactive Filters ---
            filter_col1, filter_col2 = st.columns(2)
            with filter_col1:
                all_statuses = df_tasks["status"].unique().tolist() if "status" in df_tasks.columns else []
                selected_status = st.multiselect("Filter by Status", options=all_statuses, default=all_statuses)
                
            with filter_col2:
                all_members = df_tasks["assigned_to"].unique().tolist()
                selected_members = st.multiselect("Filter by Team Member", options=all_members, default=all_members)
            
            # Apply filters to the DataFrame
            filtered_df = df_tasks[
                (df_tasks["status"].isin(selected_status)) & 
                (df_tasks["assigned_to"].isin(selected_members))
            ]
            
            # --- 2. Visual Data (Charts) ---
            st.write("---")
            chart_col1, chart_col2 = st.columns(2)
            
            with chart_col1:
                st.markdown("**Tasks by Status**")
                if not filtered_df.empty:
                    status_counts = filtered_df["status"].value_counts()
                    st.bar_chart(status_counts)
                else:
                    st.info("No data available for the selected filters.")
                    
            with chart_col2:
                st.markdown("**Tasks by Team Member**")
                if not filtered_df.empty:
                    member_counts = filtered_df["assigned_to"].value_counts()
                    st.bar_chart(member_counts)
                else:
                    st.info("No data available for the selected filters.")

            # --- 3. Clean Dataframe ---
            st.write("---")
            st.markdown("**Task Directory**")
            
            if not filtered_df.empty:
                display_columns = ["project_code", "assigned_to", "task_description", "deadline", "status"]
                clean_df = filtered_df[display_columns]
                st.dataframe(clean_df, use_container_width=True, hide_index=True)
            
        else:
            st.info("No active tasks found. Head over to 'Assign Task' to delegate some work.")
            
    except Exception as e:
        st.error(f"Error fetching active tasks: {e}")


# --- Page 2: Assign Task ---
elif page == "Assign Task":
    st.title("Assign a Task")
    
    try:
        projects_response = supabase.table("projects").select("project_code").execute()
        team_response = supabase.table("team_members").select("id, full_name").execute()
        
        projects_data = projects_response.data
        team_data = team_response.data
        
        project_options = [p['project_code'] for p in projects_data] if projects_data else []
        team_options = {t['full_name']: t['id'] for t in team_data} if team_data else {}
        
    except Exception as e:
        st.error(f"Error loading form data: {e}")
        project_options, team_options = [], {}

    if not project_options or not team_options:
        st.warning("Ensure you have at least one project and one team member in your database before assigning tasks.")
    else:
        with st.form("task_assignment_form", clear_on_submit=True):
            st.subheader("Task Details")
            
            selected_project = st.selectbox("Select Project", options=project_options)
            selected_member = st.selectbox("Assign To", options=list(team_options.keys()))
            
            task_description_input = st.text_area("Task Description", placeholder="e.g., Issue GFC drawings for masonry work...")
            deadline = st.date_input("Deadline", min_value=datetime.today())
            
            submitted = st.form_submit_button("Assign Task", type="primary")
            
            if submitted:
                if not task_description_input.strip():
                    st.error("Please provide a task description.")
                else:
                    member_id = team_options[selected_member]
                    new_task = {
                        "project_code": selected_project, 
                        "assigned_to": member_id,                  
                        "task_description": task_description_input, 
                        "deadline": deadline.isoformat(),
                        "status": "Pending" 
                    }
                    
                    try:
                        supabase.table("tasks").insert(new_task).execute()
                        st.success(f"Task successfully assigned to {selected_member} for project {selected_project}!")
                    except Exception as e:
                        st.error(f"Failed to assign task: {e}")

# --- Page 3: Team Board ---
elif page == "Team Board":
    st.title("Team Board")
    
    try:
        # Fetch tasks and team members
        tasks_response = supabase.table("tasks").select("*").execute()
        team_response = supabase.table("team_members").select("id, full_name").execute()
        
        tasks_data = tasks_response.data
        team_data = team_response.data
        
        if not team_data:
            st.warning("No team members found in the database.")
        else:
            # Create two-way mapping for ease of use
            name_to_id_map = {member['full_name']: member['id'] for member in team_data}
            id_to_name_map = {member['id']: member['full_name'] for member in team_data}
            
            # --- 1. Top Level Filter ---
            selected_member_name = st.selectbox("Select Your Name", options=list(name_to_id_map.keys()))
            selected_member_id = name_to_id_map[selected_member_name]
            
            st.divider()
            
            # Filter tasks to only show those assigned to the selected member
            my_tasks = [task for task in tasks_data if task.get('assigned_to') == selected_member_id]
            
            if my_tasks:
                # --- 2. Clean Dataframe ---
                st.subheader(f"Tasks for {selected_member_name}")
                df_my_tasks = pd.DataFrame(my_tasks)
                
                # Swap UUID for Human Name
                df_my_tasks["assigned_to"] = df_my_tasks["assigned_to"].map(lambda x: id_to_name_map.get(x, "Unknown"))
                
                display_columns = ["project_code", "assigned_to", "task_description", "deadline", "status"]
                
                # Ensure we only try to display columns that exist to prevent errors
                existing_columns = [col for col in display_columns if col in df_my_tasks.columns]
                st.dataframe(df_my_tasks[existing_columns], use_container_width=True, hide_index=True)
                
                # --- 3. Update Task Status Section ---
                st.divider()
                st.subheader("Update Task Status")
                
                # Create a mapping dictionary for the selectbox: { "Project_Code: Description..." : Task_ID }
                # This lets the user read the task naturally, but we keep the ID for the database update.
                task_options = {f"{t['project_code']} - {t['task_description'][:40]}...": t['id'] for t in my_tasks}
                
                selected_task_display = st.selectbox("Select Task to Update", options=list(task_options.keys()))
                new_status = st.selectbox("Update Status To", options=["Pending", "In Review", "Completed"])
                
                if st.button("Update Status", type="primary"):
                    # Retrieve the underlying task ID
                    task_id_to_update = task_options[selected_task_display]
                    
                    try:
                        # Execute the update mutation in Supabase
                        supabase.table("tasks").update({"status": new_status}).eq("id", task_id_to_update).execute()
                        st.success("Status updated successfully!")
                        # Rerun the app instantly to refresh the dataframe and dashboard
                        st.rerun() 
                    except Exception as e:
                        st.error(f"Failed to update task: {e}")
            else:
                st.info(f"No active tasks assigned to {selected_member_name}.")
                
    except Exception as e:
        st.error(f"Error loading Team Board data: {e}")