import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timedelta
import pandas as pd
import altair as alt

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
        team_response = supabase.table("team_members").select("id, full_name, role").execute()
        tasks_response = supabase.table("tasks").select("*").execute()
        logs_response = supabase.table("team_logs").select("*").execute() # NEW: Fetch logs
        
        projects_data = projects_response.data
        team_data = team_response.data
        tasks_data = tasks_response.data
        logs_data = logs_response.data
        
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
                
                if "team_lead" in df_projects.columns:
                    df_projects["team_lead"] = df_projects["team_lead"].map(lambda x: id_to_name_map.get(x, "Unassigned") if pd.notna(x) else "Unassigned")
                
                proj_display_columns = ["project_code", "project_name", "location", "team_lead", "current_stage", "tracking_status"]
                proj_existing_columns = [col for col in proj_display_columns if col in df_projects.columns]
                
                st.dataframe(df_projects[proj_existing_columns], use_container_width=True, hide_index=True)
        else:
            st.info("No projects found in the database. Add some projects to see them here.")

        # --- NEW: Resource & Load Management Section ---
        st.divider()
        st.subheader("Resource & Load Management")
        
        if logs_data:
            df_logs = pd.DataFrame(logs_data)
            
            # Data Mapping for human readability
            df_logs["Person"] = df_logs["team_member_id"].map(lambda x: id_to_name_map.get(x, "Unknown"))
            df_logs["Project"] = df_logs["project_code"].apply(lambda x: "Internal/No Project" if x == "INTERNAL" else f"{x} - {project_map.get(x, 'Unknown')}")
            
            # Standardize column names for the raw log table
            df_logs = df_logs.rename(columns={
                "log_date": "Date",
                "activity_type": "Activity",
                "hours_spent": "Hours",
                "description": "Description"
            })
            
            # Filter for "This Week" (Monday to Current Day)
            df_logs['Date'] = pd.to_datetime(df_logs['Date']).dt.date
            today = datetime.today().date()
            start_of_week = today - timedelta(days=today.weekday())
            
            df_week = df_logs[df_logs['Date'] >= start_of_week]
            
            if not df_week.empty:
                chart_col1, chart_col2 = st.columns(2)
                
                with chart_col1:
                    st.markdown("**Total Hours Logged this Week by Team Member**")
                    # Group by person for the bar chart
                    member_hours = df_week.groupby("Person")["Hours"].sum().reset_index()
                    st.bar_chart(member_hours.set_index("Person"))
                    
                with chart_col2:
                    st.markdown("**Firm-wide Activity Breakdown (This Week)**")
                    # Group by activity for the pie chart
                    activity_hours = df_week.groupby("Activity")["Hours"].sum().reset_index()
                    
                    # Create Altair Pie Chart
                    pie_chart = alt.Chart(activity_hours).mark_arc().encode(
                        theta=alt.Theta(field="Hours", type="quantitative"),
                        color=alt.Color(field="Activity", type="nominal"),
                        tooltip=["Activity", "Hours"]
                    ).properties(height=300)
                    
                    st.altair_chart(pie_chart, use_container_width=True)
            else:
                st.info("No hours logged yet this week.")
                
            # Display Raw Logs Dataframe
            st.markdown("**Raw Timesheet Logs**")
            log_display_cols = ["Date", "Person", "Project", "Hours", "Activity", "Description"]
            existing_log_cols = [col for col in log_display_cols if col in df_logs.columns]
            
            # Sort by Date descending
            st.dataframe(df_logs[existing_log_cols].sort_values(by="Date", ascending=False), use_container_width=True, hide_index=True)
            
        else:
            st.info("No timesheet logs found in the database yet.")
            
    except Exception as e:
        st.error(f"Error fetching dashboard data: {e}")

    # --- Active Tasks Section ---
    st.divider()
    st.subheader("Active Tasks Dashboard")
    
    try:
        if tasks_data:
            df_tasks = pd.DataFrame(tasks_data)
            df_tasks["assigned_to"] = df_tasks["assigned_to"].map(lambda x: id_to_name_map.get(x, "Unknown"))
            df_tasks["project_name"] = df_tasks["project_code"].map(lambda x: project_map.get(x, "Unknown"))
            
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
        team_response = supabase.table("team_members").select("id, full_name, role").execute()
        projects_response = supabase.table("projects").select("*").execute() 
        
        tasks_data = tasks_response.data
        team_data = team_response.data
        projects_data = projects_response.data
        
        if not team_data:
            st.warning("No team members found in the database.")
        else:
            name_to_id_map = {member['full_name']: member['id'] for member in team_data}
            id_to_name_map = {member['id']: member['full_name'] for member in team_data}
            name_to_role_map = {member['full_name']: member.get('role', 'Team Member') for member in team_data}
            project_map = {p['project_code']: p.get('project_name', 'Unknown') for p in projects_data} if projects_data else {}
            
            # --- Top Level Filter ---
            selected_member_name = st.selectbox("Select Your Name", options=list(name_to_id_map.keys()))
            selected_member_id = name_to_id_map[selected_member_name]
            selected_member_role = name_to_role_map[selected_member_name] 
            
            st.divider()
            
            # Filter tasks to only show those assigned to the selected member
            my_tasks = [task for task in tasks_data if task.get('assigned_to') == selected_member_id]
            
            if my_tasks:
                st.subheader(f"Tasks for {selected_member_name}")
                df_my_tasks = pd.DataFrame(my_tasks)
                
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
                if selected_member_role in ["Principal Architect", "Manager"]:
                    allowed_projects = projects_data
                else:
                    allowed_projects = [p for p in projects_data if p.get('team_lead') == selected_member_id]
                
                if not allowed_projects:
                    st.info("You are not assigned as the Team Lead for any projects.")
                else:
                    proj_update_options = {f"{p['project_code']} ({p.get('project_name', 'Unknown')})": p['project_code'] for p in allowed_projects}
                    
                    selected_proj_to_update = st.selectbox("Select Project to Update", options=list(proj_update_options.keys()))
                    actual_proj_code = proj_update_options[selected_proj_to_update]
                    
                    selected_project_data = next((p for p in allowed_projects if p['project_code'] == actual_proj_code), {})
                    
                    current_stage_val = selected_project_data.get('current_stage')
                    current_tracking_val = selected_project_data.get('tracking_status')
                    current_status_val = selected_project_data.get('status')
                    
                    stage_options = ["Proposal", "Working", "Services", "Detailing", "Execution", "Plantation", "Design Revision", "Finishing"]
                    status_options = ["Critical", "Delay", "On Track", "Hold"]
                    main_status_options = ["Active", "On Hold", "Completed"]
                    
                    stage_idx = stage_options.index(current_stage_val) if current_stage_val in stage_options else 0
                    tracking_idx = status_options.index(current_tracking_val) if current_tracking_val in status_options else 0
                    main_idx = main_status_options.index(current_status_val) if current_status_val in main_status_options else 0
                    
                    with st.form("update_project_form"):
                        new_stage = st.selectbox("Current Stage", options=stage_options, index=stage_idx)
                        new_tracking = st.selectbox("Tracking Status", options=status_options, index=tracking_idx)
                        
                        new_main_status = None
                        if selected_member_role in ["Principal Architect", "Manager"]:
                            new_main_status = st.selectbox("Main Project Status", options=main_status_options, index=main_idx)
                        
                        if st.form_submit_button("Update Project Details", type="primary"):
                            update_payload = {
                                "current_stage": new_stage,
                                "tracking_status": new_tracking
                            }
                            if new_main_status:
                                update_payload["status"] = new_main_status
                            
                            try:
                                supabase.table("projects").update(update_payload).eq("project_code", actual_proj_code).execute()
                                st.success(f"Project {actual_proj_code} updated successfully!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to update project: {e}")

            # --- NEW: Submit Daily Log Section ---
            st.divider()
            st.subheader("Submit Daily Log")
            
            # Prepare options specifically for the log (all projects + Internal)
            log_project_options = {"Internal/No Project": "INTERNAL"}
            if projects_data:
                log_project_options.update({f"{p['project_code']} ({p.get('project_name', 'Unknown')})": p['project_code'] for p in projects_data})
            
            with st.form("daily_log_form", clear_on_submit=True):
                log_date = st.date_input("Date", value=datetime.today())
                log_proj_display = st.selectbox("Project", options=list(log_project_options.keys()))
                
                activity_choices = ["Drafting/3D", "Site Visit", "Client Meeting", "Vendor Coordination", "Internal Review", "Admin/General"]
                log_activity = st.selectbox("Activity Type", options=activity_choices)
                
                log_hours = st.number_input("Hours Spent", min_value=0.5, step=0.5, value=1.0)
                log_desc = st.text_area("Brief Description", placeholder="e.g., Modeled the ground floor structural layout...")
                
                if st.form_submit_button("Submit Log", type="primary"):
                    if not log_desc.strip():
                        st.error("Please provide a brief description of the work done.")
                    else:
                        log_payload = {
                            "team_member_id": selected_member_id,
                            "project_code": log_project_options[log_proj_display],
                            "log_date": log_date.isoformat(),
                            "activity_type": log_activity,
                            "hours_spent": log_hours,
                            "description": log_desc
                        }
                        
                        try:
                            supabase.table("team_logs").insert(log_payload).execute()
                            st.success(f"Log submitted successfully for {log_hours} hours!")
                        except Exception as e:
                            st.error(f"Failed to submit log: {e}")

    except Exception as e:
        st.error(f"Error loading Team Board data: {e}")