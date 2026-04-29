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

# --- Global Context & Settings Fetch ---
# Fetching this at the top level makes the entire app "Role-Aware" and fast.
try:
    team_response = supabase.table("team_members").select("id, full_name, role").execute()
    settings_response = supabase.table("aos_settings").select("*").execute()
    
    team_data = team_response.data
    settings_data = settings_response.data
    
    # Global User Mappings
    name_to_id_map = {member['full_name']: member['id'] for member in team_data} if team_data else {}
    id_to_name_map = {member['id']: member['full_name'] for member in team_data} if team_data else {}
    name_to_role_map = {member['full_name']: member.get('role', 'Team Member') for member in team_data} if team_data else {}
    
    # Global Settings Mappings
    settings_map = {row['category']: row.get('options', []) for row in settings_data} if settings_data else {}
    global_activity_types = settings_map.get("activity_types", [])
    global_tags = settings_map.get("tags", [])
    
except Exception as e:
    st.error(f"Error loading global configuration: {e}")
    team_data, global_activity_types, global_tags = [], [], []

# --- Sidebar Navigation & Global Login ---
st.sidebar.title("AOS Navigation")

if not team_data:
    st.sidebar.warning("No team members found in the database. Please add users.")
    st.stop()

# This acts as the global login context for the entire application
selected_member_name = st.sidebar.selectbox("👤 Current User", options=list(name_to_id_map.keys()))
selected_member_id = name_to_id_map[selected_member_name]
selected_member_role = name_to_role_map[selected_member_name] 

st.sidebar.divider()

# Role-Based Routing
nav_pages = ["Principal Dashboard", "Assign Task", "Team Board"]

# The Admin page is only injected into the navigation if the user has permission
if selected_member_role in ["Principal Architect", "Manager"]:
    nav_pages.append("Admin Settings")

page = st.sidebar.radio("Go to", nav_pages)

# ==========================================
# PAGE 1: PRINCIPAL DASHBOARD
# ==========================================
if page == "Principal Dashboard":
    st.title("Principal Dashboard")
    
    try:
        projects_response = supabase.table("projects").select("*").execute()
        tasks_response = supabase.table("tasks").select("*").execute()
        logs_response = supabase.table("team_logs").select("*").execute()
        
        projects_data = projects_response.data
        tasks_data = tasks_response.data
        logs_data = logs_response.data
        
        project_map = {p['project_code']: p.get('project_name', 'Unknown') for p in projects_data} if projects_data else {}

        if projects_data:
            total_projects = len(projects_data)
            active_projects = len([p for p in projects_data if p.get('status', 'Active').lower() == 'active'])
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(label="Total Active Projects", value=active_projects)
            with col2:
                st.metric(label="Total Projects (All-time)", value=total_projects)
                
            st.divider()
            
            with st.expander("📂 View Project Directory"):
                df_projects = pd.DataFrame(projects_data)
                
                if "team_lead" in df_projects.columns:
                    df_projects["team_lead"] = df_projects["team_lead"].map(lambda x: id_to_name_map.get(x, "Unassigned") if pd.notna(x) else "Unassigned")
                
                proj_display_columns = ["project_code", "project_name", "location", "team_lead", "current_stage", "tracking_status"]
                proj_existing_columns = [col for col in proj_display_columns if col in df_projects.columns]
                
                st.dataframe(df_projects[proj_existing_columns], use_container_width=True, hide_index=True)
        else:
            st.info("No projects found in the database. Add some projects to see them here.")

        # --- Resource & Load Management ---
        st.divider()
        st.subheader("Resource & Load Management")
        
        if logs_data:
            df_logs = pd.DataFrame(logs_data)
            
            df_logs["Person"] = df_logs["team_member_id"].map(lambda x: id_to_name_map.get(x, "Unknown"))
            df_logs["Project"] = df_logs["project_code"].apply(lambda x: "Internal/No Project" if x == "INTERNAL" else f"{x} - {project_map.get(x, 'Unknown')}")
            
            df_logs = df_logs.rename(columns={
                "log_date": "Date",
                "activity_type": "Activity",
                "hours_spent": "Hours",
                "description": "Description"
            })
            
            df_logs['Date'] = pd.to_datetime(df_logs['Date']).dt.date
            today = datetime.today().date()
            start_of_week = today - timedelta(days=today.weekday())
            
            df_week = df_logs[df_logs['Date'] >= start_of_week]
            
            if not df_week.empty:
                chart_col1, chart_col2 = st.columns(2)
                
                with chart_col1:
                    st.markdown("**Total Hours Logged this Week by Team Member**")
                    member_hours = df_week.groupby("Person")["Hours"].sum().reset_index()
                    st.bar_chart(member_hours.set_index("Person"))
                    
                with chart_col2:
                    st.markdown("**Firm-wide Activity Breakdown (This Week)**")
                    activity_hours = df_week.groupby("Activity")["Hours"].sum().reset_index()
                    
                    pie_chart = alt.Chart(activity_hours).mark_arc().encode(
                        theta=alt.Theta(field="Hours", type="quantitative"),
                        color=alt.Color(field="Activity", type="nominal"),
                        tooltip=["Activity", "Hours"]
                    ).properties(height=300)
                    
                    st.altair_chart(pie_chart, use_container_width=True)
            else:
                st.info("No hours logged yet this week.")
                
            st.markdown("**Raw Timesheet Logs**")
            log_display_cols = ["Date", "Person", "Project", "Hours", "Activity", "Description"]
            existing_log_cols = [col for col in log_display_cols if col in df_logs.columns]
            
            st.dataframe(df_logs[existing_log_cols].sort_values(by="Date", ascending=False), use_container_width=True, hide_index=True)
            
        else:
            st.info("No timesheet logs found in the database yet.")
            
    except Exception as e:
        st.error(f"Error fetching dashboard data: {e}")

    # --- Active Tasks Dashboard ---
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

# ==========================================
# PAGE 2: ASSIGN TASK
# ==========================================
elif page == "Assign Task":
    st.title("Assign a Task")
    
    try:
        projects_response = supabase.table("projects").select("project_code, project_name, team_lead").execute()
        projects_data = projects_response.data
        
        project_options = {}
        if projects_data:
            for p in projects_data:
                code = p['project_code']
                name = p.get('project_name', 'Unknown')
                lead_id = p.get('team_lead')
                lead_name = id_to_name_map.get(lead_id, "Unassigned")
                
                display_string = f"{code} ({name}) - Lead: {lead_name}"
                project_options[display_string] = code
                
    except Exception as e:
        st.error(f"Error loading form data: {e}")
        project_options = {}

    if not project_options or not team_data:
        st.warning("Ensure you have at least one project and one team member in your database before assigning tasks.")
    else:
        TASK_DICTIONARY = {
            "Concept Design": ["Site Analysis", "Moodboard & References", "Conceptual Layouts", "Volume Massing", "Initial Presentation", "Client Revisions"],
            "Working Drawings": ["Floor Plans", "Elevations", "Sections", "Door/Window Schedule", "Flooring Layout", "Masonry Details", "Staircase Details"],
            "MEP Services": ["Electrical Layout", "Plumbing Layout", "HVAC Layout", "Fire Safety Plan", "Reflected Ceiling Plan (RCP)"],
            "3D Visualization": ["Exterior 3D Views", "Interior 3D Views", "Walkthrough Animation", "Material & Lighting Setup", "Post-Production"],
            "Site Execution": ["Site Marking / Layout", "Steel / Reinforcement Checking", "Pouring Supervision", "Vendor Coordination", "Quality Check / Snag List"],
            "Admin / General": ["Permit Drawings", "BOQ & Estimation", "Client Handover Package", "Team Meeting"]
        }

        with st.form("task_assignment_form", clear_on_submit=True):
            st.subheader("Task Details")
            
            selected_project_display = st.selectbox("Select Project", options=list(project_options.keys()))
            # Assign To dropdown maps directly to the global team_data
            selected_assignee_name = st.selectbox("Assign To", options=list(name_to_id_map.keys()))
            
            st.divider()
            st.markdown("##### Task Specifications")
            
            col1, col2 = st.columns(2)
            with col1:
                task_category = st.selectbox("Task Category", options=list(TASK_DICTIONARY.keys()))
            with col2:
                task_deliverable = st.selectbox("Standard Deliverable", options=TASK_DICTIONARY[task_category])
                
            additional_notes = st.text_input("Additional Notes (Optional)", placeholder="e.g., Check column grid dimensions on ground floor.")
            
            deadline = st.date_input("Deadline", min_value=datetime.today())
            
            submitted = st.form_submit_button("Assign Task", type="primary")
            
            if submitted:
                final_description = f"{task_category} - {task_deliverable}"
                if additional_notes.strip():
                    final_description += f". Notes: {additional_notes.strip()}"
                
                member_id = name_to_id_map[selected_assignee_name]
                actual_project_code = project_options[selected_project_display]
                
                new_task = {
                    "project_code": actual_project_code, 
                    "assigned_to": member_id,                  
                    "task_description": final_description, 
                    "deadline": deadline.isoformat(),
                    "status": "Pending" 
                }
                
                try:
                    supabase.table("tasks").insert(new_task).execute()
                    st.success(f"Task successfully assigned to {selected_assignee_name} for project {actual_project_code}!")
                except Exception as e:
                    st.error(f"Failed to assign task: {e}")

# ==========================================
# PAGE 3: TEAM BOARD
# ==========================================
elif page == "Team Board":
    st.title("Team Board")
    st.markdown(f"**Welcome, {selected_member_name}** | Role: *{selected_member_role}*")
    
    try:
        tasks_response = supabase.table("tasks").select("*").execute()
        projects_response = supabase.table("projects").select("*").execute() 
        logs_response = supabase.table("team_logs").select("*").execute() 
        
        tasks_data = tasks_response.data
        projects_data = projects_response.data
        logs_data = logs_response.data
        
        project_map = {p['project_code']: p.get('project_name', 'Unknown') for p in projects_data} if projects_data else {}
        
        st.divider()
        
        tab1, tab2, tab3 = st.tabs(["📋 My Tasks", "🏗️ Update Projects", "⏱️ Time Tracker & Analytics"])
        
        # === TAB 1: MY TASKS ===
        with tab1:
            my_tasks = [task for task in tasks_data if task.get('assigned_to') == selected_member_id]
            
            if my_tasks:
                st.subheader("Assigned Workload")
                df_my_tasks = pd.DataFrame(my_tasks)
                
                df_my_tasks["assigned_to"] = df_my_tasks["assigned_to"].map(lambda x: id_to_name_map.get(x, "Unknown"))
                df_my_tasks["project_name"] = df_my_tasks["project_code"].map(lambda x: project_map.get(x, "Unknown"))
                
                display_columns = ["project_code", "project_name", "assigned_to", "task_description", "deadline", "status"]
                existing_columns = [col for col in display_columns if col in df_my_tasks.columns]
                st.dataframe(df_my_tasks[existing_columns], use_container_width=True, hide_index=True)
                
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
                st.info("You currently have no active tasks assigned.")
                
        # === TAB 2: UPDATE PROJECTS ===
        with tab2:
            if projects_data:
                if selected_member_role in ["Principal Architect", "Manager"]:
                    allowed_projects = projects_data
                else:
                    allowed_projects = [p for p in projects_data if p.get('team_lead') == selected_member_id]
                
                if not allowed_projects:
                    st.info("You are not assigned as the Team Lead for any projects.")
                else:
                    st.subheader("Update Project Parameters")
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

        # === TAB 3: TIME TRACKER & ANALYTICS ===
        with tab3:
            st.subheader("Submit Daily Log")
            
            log_project_options = {"Internal/No Project": "INTERNAL"}
            if projects_data:
                log_project_options.update({f"{p['project_code']} ({p.get('project_name', 'Unknown')})": p['project_code'] for p in projects_data})
            
            with st.form("daily_log_form", clear_on_submit=True):
                log_date = st.date_input("Date", value=datetime.today())
                log_proj_display = st.selectbox("Project", options=list(log_project_options.keys()))
                
                # DYNAMIC: Fetching Activity Types from global aos_settings
                if not global_activity_types:
                    st.warning("No Activity Types found in settings. Using fallback data.")
                    global_activity_types = ['Drawing', 'Admin']
                
                log_activity = st.selectbox("Activity Type", options=global_activity_types)
                
                # Formatted Time Selection
                col_h, col_m = st.columns(2)
                with col_h:
                    hours_input = st.selectbox("Hours", options=list(range(13)), index=1)
                with col_m:
                    minutes_input = st.selectbox("Minutes", options=[0, 15, 30, 45], index=0)
                
                # DYNAMIC: Fetching Tags from global aos_settings
                if not global_tags:
                    st.warning("No Tags found in settings. Using fallback data.")
                    global_tags = ['Concept', 'Other']
                
                log_tags = st.multiselect("Tags", options=global_tags)
                
                log_desc = st.text_area("Brief Description", placeholder="e.g., Modeled the ground floor structural layout...")
                
                if st.form_submit_button("Submit Log", type="primary"):
                    total_time = hours_input + (minutes_input / 60.0)
                    
                    if total_time == 0:
                        st.error("Please log a valid time greater than 0.")
                    elif not log_desc.strip():
                        st.error("Please provide a brief description of the work done.")
                    else:
                        log_payload = {
                            "team_member_id": selected_member_id,
                            "project_code": log_project_options[log_proj_display],
                            "log_date": log_date.isoformat(),
                            "activity_type": log_activity,
                            "hours_spent": total_time,
                            "description": log_desc,
                            "tags": log_tags
                        }
                        
                        try:
                            supabase.table("team_logs").insert(log_payload).execute()
                            st.success(f"Log submitted successfully for {total_time:.2f} hours!")
                            st.rerun() 
                        except Exception as e:
                            st.error(f"Failed to submit log: {e}")

            # --- My Timesheet History ---
            st.divider()
            st.subheader("My Timesheet History")
            
            today = datetime.today().date()
            default_start = today - timedelta(days=7)
            
            date_range = st.date_input("Select Date Range", value=(default_start, today))
            
            if isinstance(date_range, tuple) and len(date_range) == 2:
                start_date, end_date = date_range
                
                if logs_data:
                    my_logs = [log for log in logs_data if log.get('team_member_id') == selected_member_id]
                    
                    if my_logs:
                        df_my_logs = pd.DataFrame(my_logs)
                        df_my_logs['log_date'] = pd.to_datetime(df_my_logs['log_date']).dt.date
                        
                        mask = (df_my_logs['log_date'] >= start_date) & (df_my_logs['log_date'] <= end_date)
                        df_filtered_logs = df_my_logs.loc[mask].copy()
                        
                        if not df_filtered_logs.empty:
                            total_logged_hours = df_filtered_logs['hours_spent'].sum()
                            st.metric(label="Total Hours Logged (Selected Period)", value=f"{total_logged_hours:.2f} hrs")
                            
                            df_filtered_logs["project_name"] = df_filtered_logs["project_code"].apply(lambda x: "Internal/No Project" if x == "INTERNAL" else f"{x} - {project_map.get(x, 'Unknown')}")
                            
                            df_filtered_logs = df_filtered_logs.rename(columns={
                                "log_date": "Date",
                                "project_name": "Project",
                                "activity_type": "Activity",
                                "hours_spent": "Hours",
                                "tags": "Tags",
                                "description": "Description"
                            })
                            
                            display_log_cols = ["Date", "Project", "Activity", "Hours", "Tags", "Description"]
                            existing_log_cols = [c for c in display_log_cols if c in df_filtered_logs.columns]
                            
                            st.dataframe(df_filtered_logs[existing_log_cols].sort_values(by="Date", ascending=False), use_container_width=True, hide_index=True)
                        else:
                            st.info("No logs found for the selected date range.")
                    else:
                        st.info("You haven't submitted any timesheet logs yet.")
            else:
                st.warning("Please select a valid start and end date to view history.")

    except Exception as e:
        st.error(f"Error loading Team Board data: {e}")

# ==========================================
# PAGE 4: ADMIN SETTINGS (Restricted)
# ==========================================
elif page == "Admin Settings":
    # Security check: If a user somehow manipulates the URL/state to reach this, explicitly block them
    if selected_member_role not in ["Principal Architect", "Manager"]:
        st.error("Access Denied: You must be a Principal Architect or Manager to view this page.")
    else:
        st.title("Admin Settings")
        st.markdown("Manage global application configurations and dropdown options.")
        
        col1, col2 = st.columns(2)
        
        # --- Section: Manage Activity Types ---
        with col1:
            st.subheader("Manage Activity Types")
            with st.form("activity_settings_form"):
                
                # Multiselect serves as both a viewer and a rapid removal tool
                active_activities = st.multiselect(
                    "Current Activity Types (Click 'X' to remove)", 
                    options=global_activity_types, 
                    default=global_activity_types
                )
                
                new_activity = st.text_input("Add New Activity Type", placeholder="e.g., Client Presentation")
                
                if st.form_submit_button("Save Activity Types", type="primary"):
                    final_activities = active_activities.copy()
                    
                    # Append new item if it is filled out and doesn't already exist
                    if new_activity.strip() and new_activity.strip() not in final_activities:
                        final_activities.append(new_activity.strip())
                    
                    try:
                        # Mutation to update array in Supabase
                        supabase.table("aos_settings").update({"options": final_activities}).eq("category", "activity_types").execute()
                        st.success("Activity types updated successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error updating database: {e}")
                        
        # --- Section: Manage Tags ---
        with col2:
            st.subheader("Manage Tags")
            with st.form("tags_settings_form"):
                
                active_tags = st.multiselect(
                    "Current Tags (Click 'X' to remove)", 
                    options=global_tags, 
                    default=global_tags
                )
                
                new_tag = st.text_input("Add New Tag", placeholder="e.g., Urgent")
                
                if st.form_submit_button("Save Tags", type="primary"):
                    final_tags = active_tags.copy()
                    
                    if new_tag.strip() and new_tag.strip() not in final_tags:
                        final_tags.append(new_tag.strip())
                    
                    try:
                        supabase.table("aos_settings").update({"options": final_tags}).eq("category", "tags").execute()
                        st.success("Tags updated successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error updating database: {e}")