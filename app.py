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
    
    try:
        # Fetch data globally for the dashboard
        projects_response = supabase.table("projects").select("*").execute()
        # UPDATED: Included 'role' in the select statement
        team_response = supabase.table("team_members").select("id, full_name, role").execute()
        tasks_response = supabase.table("tasks").select("*").execute()
        
        projects_data = projects_response.data
        team_data = team_response.data
        tasks_data = tasks_response.data
        
        # Create global mappings
        id_to_name_map = {member['id']: member['full_name'] for member in team_data} if team_data else {}
        project_map = {p['project_code']: p.get('project_name', 'Unknown') for p in projects_data} if projects_data else {}

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
            
            # --- Project Directory ---
            with st.expander("📂 View Project Directory"):
                df_projects = pd.DataFrame(projects_data)
                
                # Map the team_lead UUID to the actual name
                if "team_lead" in df_projects.columns:
                    df_projects["team_lead"] = df_projects["team_lead"].map(lambda x: id_to_name_map.get(x, "Unassigned") if pd.notna(x) else "Unassigned")
                
                # Define desired columns and filter out created_at/id
                proj_display_columns = ["project_code", "project_name", "location", "team_lead", "current_stage", "tracking_status"]
                proj_existing_columns = [col for col in proj_display_columns if col in df_projects.columns]
                
                st.dataframe(df_projects[proj_existing_columns], use_container_width=True, hide_index=True)
        else:
            st.info("No projects found in the database. Add some projects to see them here.")
            
    except Exception as e:
        st.error(f"Error fetching dashboard data: {e}")

    # --- Active Tasks Section ---
    st.divider()
    st.subheader("Active Tasks Dashboard")
    
    try:
        if tasks_data:
            df_tasks = pd.DataFrame(tasks_data)
            
            # Map UUIDs to human names AND map project_code to project_name
            df_tasks["assigned_to"] = df_tasks["assigned_to"].map(lambda x: id_to_name_map.get(x, "Unknown"))
            df_tasks["project_name"] = df_tasks["project_code"].map(lambda x: project_map.get(x, "Unknown"))
            
            # --- Interactive Filters ---
            filter_col1, filter_col2 = st.columns(2)
            with filter_col1:
                all_statuses = df_tasks["status"].unique().tolist() if "status" in df_tasks.columns else []
                selected_status = st.multiselect("Filter by Status", options=all_statuses, default=all_statuses)
                
            with filter_col2:
                all_members = df_tasks["assigned_to"].unique().tolist()
                selected_members = st.multiselect("Filter by Team Member", options=all_members, default=all_members)
            
            filtered_df = df_tasks[
                (df_tasks["status"].isin(selected_status)) & 
                (df_tasks["assigned_to"].isin(selected_members))
            ]
            
            # --- Visual Data (Charts) ---
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

            # --- Clean Dataframe ---
            st.write("---")
            st.markdown("**Task Directory**")
            
            if not filtered_df.empty:
                display_columns = ["project_code", "project_name", "assigned_to", "task_description", "deadline", "status"]
                clean_df = filtered_df[display_columns]
                st.dataframe(clean_df, use_container_width=True, hide_index=True)
            
        else:
            st.info("No active tasks found. Head over to 'Assign Task' to delegate some work.")
            
    except Exception as e:
        st.error(f"Error processing active tasks: {e}")


# --- Page 2: Assign Task ---
elif page == "Assign Task":
    st.title("Assign a Task")
    
    try:
        projects_response = supabase.table("projects").select("project_code, project_name").execute()
        # UPDATED: Included 'role'
        team_response = supabase.table("team_members").select("id, full_name, role").execute()
        
        projects_data = projects_response.data
        team_data = team_response.data
        
        project_options = {f"{p['project_code']} ({p.get('project_name', 'Unknown')})": p['project_code'] for p in projects_data} if projects_data else {}
        team_options = {t['full_name']: t['id'] for t in team_data} if team_data else {}
        
    except Exception as e:
        st.error(f"Error loading form data: {e}")
        project_options, team_options = {}, {}

    if not project_options or not team_options:
        st.warning("Ensure you have at least one project and one team member in your database before assigning tasks.")
    else:
        with st.form("task_assignment_form", clear_on_submit=True):
            st.subheader("Task Details")
            
            selected_project_display = st.selectbox("Select Project", options=list(project_options.keys()))
            selected_member = st.selectbox("Assign To", options=list(team_options.keys()))
            
            task_description_input = st.text_area("Task Description", placeholder="e.g., Issue GFC drawings for masonry work...")
            deadline = st.date_input("Deadline", min_value=datetime.today())
            
            submitted = st.form_submit_button("Assign Task", type="primary")
            
            if submitted:
                if not task_description_input.strip():
                    st.error("Please provide a task description.")
                else:
                    member_id = team_options[selected_member]
                    actual_project_code = project_options[selected_project_display]
                    
                    new_task = {
                        "project_code": actual_project_code, 
                        "assigned_to": member_id,                  
                        "task_description": task_description_input, 
                        "deadline": deadline.isoformat(),
                        "status": "Pending" 
                    }
                    
                    try:
                        supabase.table("tasks").insert(new_task).execute()
                        st.success(f"Task successfully assigned to {selected_member} for project {actual_project_code}!")
                    except Exception as e:
                        st.error(f"Failed to assign task: {e}")

# --- Page 3: Team Board ---
elif page == "Team Board":
    st.title("Team Board")
    
    try:
        tasks_response = supabase.table("tasks").select("*").execute()
        # UPDATED: Fetch 'role' to enable permissions logic
        team_response = supabase.table("team_members").select("id, full_name, role").execute()
        projects_response = supabase.table("projects").select("*").execute() # Need all columns for filtering team_lead
        
        tasks_data = tasks_response.data
        team_data = team_response.data
        projects_data = projects_response.data
        
        if not team_data:
            st.warning("No team members found in the database.")
        else:
            # Create mappings
            name_to_id_map = {member['full_name']: member['id'] for member in team_data}
            id_to_name_map = {member['id']: member['full_name'] for member in team_data}
            # NEW: Mapping to easily retrieve the role of the selected user
            name_to_role_map = {member['full_name']: member.get('role', 'Team Member') for member in team_data}
            project_map = {p['project_code']: p.get('project_name', 'Unknown') for p in projects_data} if projects_data else {}
            
            # --- Top Level Filter ---
            selected_member_name = st.selectbox("Select Your Name", options=list(name_to_id_map.keys()))
            selected_member_id = name_to_id_map[selected_member_name]
            selected_member_role = name_to_role_map[selected_member_name] # Fetch role
            
            st.divider()
            
            # Filter tasks to only show those assigned to the selected member
            my_tasks = [task for task in tasks_data if task.get('assigned_to') == selected_member_id]
            
            if my_tasks:
                st.subheader(f"Tasks for {selected_member_name}")
                df_my_tasks = pd.DataFrame(my_tasks)
                
                # Swap UUID for Human Name AND Map Project Code to Project Name
                df_my_tasks["assigned_to"] = df_my_tasks["assigned_to"].map(lambda x: id_to_name_map.get(x, "Unknown"))
                df_my_tasks["project_name"] = df_my_tasks["project_code"].map(lambda x: project_map.get(x, "Unknown"))
                
                display_columns = ["project_code", "project_name", "assigned_to", "task_description", "deadline", "status"]
                existing_columns = [col for col in display_columns if col in df_my_tasks.columns]
                st.dataframe(df_my_tasks[existing_columns], use_container_width=True, hide_index=True)
                
                # --- Update Task Status Section ---
                st.divider()
                st.subheader("Update Task Status")
                
                task_options = {f"{t['project_code']} - {t['task_description'][:40]}...": t['id'] for t in my_tasks}
                
                selected_task_display = st.selectbox("Select Task to Update", options=list(task_options.keys()))
                new_status = st.selectbox("Update Status To", options=["Pending", "In Review", "Completed"])
                
                if st.button("Update Status", type="primary"):
                    task_id_to_update = task_options[selected_task_display]
                    try:
                        supabase.table("tasks").update({"status": new_status}).eq("id", task_id_to_update).execute()
                        st.success("Task status updated successfully!")
                        st.rerun() 
                    except Exception as e:
                        st.error(f"Failed to update task: {e}")
            else:
                st.info(f"No active tasks assigned to {selected_member_name}.")
                
            # --- Update Project Status Section ---
            st.divider()
            st.subheader("Update Project Status")
            
            if projects_data:
                # ROLE CHECK: Filter allowed projects based on the user's role
                if selected_member_role in ["Principal Architect", "Manager"]:
                    allowed_projects = projects_data # Sees everything
                else:
                    # Standard team members only see projects where they are explicitly assigned as the team_lead
                    allowed_projects = [p for p in projects_data if p.get('team_lead') == selected_member_id]
                
                if not allowed_projects:
                    st.info("You are not assigned as the Team Lead for any projects.")
                else:
                    proj_update_options = {f"{p['project_code']} ({p.get('project_name', 'Unknown')})": p['project_code'] for p in allowed_projects}
                    
                    with st.form("update_project_form"):
                        selected_proj_to_update = st.selectbox("Select Project", options=list(proj_update_options.keys()))
                        
                        stage_options = ["Proposal", "Working", "Services", "Detailing", "Execution", "Plantation", "Design Revision", "Finishing"]
                        status_options = ["Critical", "Delay", "On Track", "Hold"]
                        
                        new_stage = st.selectbox("Current Stage", options=stage_options)
                        new_tracking = st.selectbox("Tracking Status", options=status_options)
                        
                        # SUPERPOWER CHECK: Only render the main status selectbox for leadership
                        new_main_status = None
                        if selected_member_role in ["Principal Architect", "Manager"]:
                            new_main_status = st.selectbox("Main Project Status", options=["Active", "On Hold", "Completed"])
                        
                        if st.form_submit_button("Update Project", type="primary"):
                            actual_proj_code = proj_update_options[selected_proj_to_update]
                            
                            # Prepare payload
                            update_payload = {
                                "current_stage": new_stage,
                                "tracking_status": new_tracking
                            }
                            # Only inject the main status update if the user had permission to select it
                            if new_main_status:
                                update_payload["status"] = new_main_status
                            
                            try:
                                supabase.table("projects").update(update_payload).eq("project_code", actual_proj_code).execute()
                                st.success(f"Project {actual_proj_code} updated successfully!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to update project: {e}")

    except Exception as e:
        st.error(f"Error loading Team Board data: {e}")