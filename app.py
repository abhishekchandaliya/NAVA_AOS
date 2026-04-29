import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timedelta
import pandas as pd
import altair as alt

# --- Page Configuration ---
st.set_page_config(page_title="AOS | Architect's Operating System", layout="wide")

# --- Session State Initialization ---
if 'selected_project_code' not in st.session_state:
    st.session_state.selected_project_code = None

def go_to_dashboard():
    st.session_state.selected_project_code = None

def open_cockpit(project_code):
    st.session_state.selected_project_code = project_code

# --- Database Connection ---
@st.cache_resource
def init_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# --- Global Context & Settings Fetch ---
try:
    team_response = supabase.table("team_members").select("id, full_name, role").execute()
    settings_response = supabase.table("aos_settings").select("*").execute()
    
    team_data = team_response.data
    settings_data = settings_response.data
    
    name_to_id_map = {member['full_name']: member['id'] for member in team_data} if team_data else {}
    id_to_name_map = {member['id']: member['full_name'] for member in team_data} if team_data else {}
    name_to_role_map = {member['full_name']: member.get('role', 'Team Member') for member in team_data} if team_data else {}
    
    settings_map = {row['category']: row.get('options', []) for row in settings_data} if settings_data else {}
    global_activity_types = settings_map.get("activity_types", [])
    global_tags = settings_map.get("tags", [])
    global_designations = settings_map.get("designations", ["Principal Architect", "Manager", "Team Member"])
    
except Exception as e:
    st.error(f"Error loading global configuration: {e}")
    team_data, global_activity_types, global_tags, global_designations = [], [], [], []

# --- Sidebar Navigation & Global Login ---
st.sidebar.title("AOS Navigation")

if not team_data:
    st.sidebar.warning("No team members found in the database. Please add users.")
    st.stop()

selected_member_name = st.sidebar.selectbox("👤 Current User", options=list(name_to_id_map.keys()))
selected_member_id = name_to_id_map[selected_member_name]
selected_member_role = name_to_role_map[selected_member_name] 

st.sidebar.divider()

nav_pages = ["Principal Dashboard", "Assign Task", "Team Board"]

if selected_member_role in ["Principal Architect", "Manager"]:
    nav_pages.append("Admin Settings")

page = st.sidebar.radio("Go to", nav_pages)

# ==========================================
# PAGE 1: PRINCIPAL DASHBOARD & COCKPIT
# ==========================================
if page == "Principal Dashboard":
    
    try:
        projects_response = supabase.table("projects").select("*").execute()
        tasks_response = supabase.table("tasks").select("*").execute()
        logs_response = supabase.table("team_logs").select("*").execute()
        ledger_response = supabase.table("project_ledger").select("*").execute() 
        
        projects_data = projects_response.data
        tasks_data = tasks_response.data
        logs_data = logs_response.data
        ledger_data = ledger_response.data
        
        project_map = {p['project_code']: p.get('project_name', 'Unknown') for p in projects_data} if projects_data else {}

        # ---------------------------------------------------------
        # STATE 1: PROJECT COCKPIT (DRILL-DOWN VIEW)
        # ---------------------------------------------------------
        if st.session_state.selected_project_code:
            st.button("⬅️ Back to Main Dashboard", on_click=go_to_dashboard)
            
            target_code = st.session_state.selected_project_code
            proj_details = next((p for p in projects_data if p['project_code'] == target_code), None)
            
            if proj_details:
                lead_name = id_to_name_map.get(proj_details.get('team_lead'), "Unassigned")
                st.title(f"🚀 Project Cockpit: {target_code}")
                st.markdown(f"**{proj_details.get('project_name', 'Unnamed')}** | Lead: *{lead_name}* | Stage: *{proj_details.get('current_stage', 'N/A')}*")
                st.divider()
                
                # --- Proactive Summary (Critical Path) ---
                st.subheader("Critical Path Summary")
                df_ledger = pd.DataFrame(ledger_data) if ledger_data else pd.DataFrame()
                
                if not df_ledger.empty and 'project_code' in df_ledger.columns:
                    proj_ledger = df_ledger[df_ledger['project_code'] == target_code].copy()
                    
                    if not proj_ledger.empty:
                        proj_ledger['created_at'] = pd.to_datetime(proj_ledger['created_at'])
                        idx_max = proj_ledger.groupby('category')['created_at'].idxmax()
                        summary_df = proj_ledger.loc[idx_max].sort_values('created_at', ascending=False)
                        
                        cols = st.columns(len(summary_df))
                        for i, (_, row) in enumerate(summary_df.iterrows()):
                            with cols[i]:
                                st.info(f"**{row['category']}**\n\n{row.get('content', '')}\n\n*(Updated: {row['created_at'].strftime('%Y-%m-%d')})*")
                    else:
                        st.write("No updates logged for this project yet.")
                else:
                    st.write("No updates logged for this project yet.")
                    
                st.divider()
                
                # --- Full Width Ledger ---
                st.subheader("Activity Ledger")
                if not df_ledger.empty and not proj_ledger.empty:
                    display_ledger = proj_ledger.copy()
                    display_ledger['Team Member'] = display_ledger['author_id'].map(lambda x: id_to_name_map.get(x, "Unknown"))
                    
                    display_ledger = display_ledger.rename(columns={"created_at": "Date", "category": "Category", "content": "Details", "action_type": "Action Required"})
                    
                    view_cols = ["Date", "Category", "Team Member", "Details", "Action Required"]
                    view_cols = [c for c in view_cols if c in display_ledger.columns]
                    st.dataframe(display_ledger[view_cols].sort_values("Date", ascending=False), use_container_width=True, hide_index=True)
                else:
                    st.write("Ledger is empty.")
                    
            else:
                st.error("Project details not found.")

        # ---------------------------------------------------------
        # STATE 2: PRINCIPAL DASHBOARD (MAIN VIEW)
        # ---------------------------------------------------------
        else:
            st.title("Principal Dashboard")
            
            # --- Principal Action Center (One-Click Resolution) ---
            df_ledger = pd.DataFrame(ledger_data) if ledger_data else pd.DataFrame()
            if not df_ledger.empty and 'is_principal_action_required' in df_ledger.columns:
                action_req_df = df_ledger[df_ledger['is_principal_action_required'] == True].copy()
                
                if not action_req_df.empty:
                    st.error("### 🔴 Principal Intervention Required")
                    
                    for idx, row in action_req_df.sort_values('created_at', ascending=False).iterrows():
                        proj_code = row['project_code']
                        proj_name = project_map.get(proj_code, 'Unknown')
                        req_by = id_to_name_map.get(row.get('author_id'), 'Unknown')
                        action = row.get('action_type', 'Action Required')
                        date_str = pd.to_datetime(row['created_at']).strftime('%b %d, %Y')
                        details = row.get('content', '') 
                        
                        with st.container():
                            c1, c2, c3 = st.columns([4, 2, 1])
                            with c1:
                                st.markdown(f"**{proj_code} - {proj_name}** | *{date_str}*")
                                st.markdown(f"**Reason:** {action} | **Details:** {details}")
                            with c2:
                                st.markdown(f"**Requested by:** {req_by}")
                            with c3:
                                st.button("View Cockpit", key=f"flag_{row.get('id', idx)}", on_click=open_cockpit, args=(proj_code,), type="primary")
                            st.write("---")
            
            if projects_data:
                dash_tab1, dash_tab2, dash_tab3 = st.tabs(["⚠️ Portfolio Health", "📊 Resource Allocation", "🗂️ Master Directory"])
                
                df_projects = pd.DataFrame(projects_data)
                if "team_lead" in df_projects.columns:
                    df_projects["team_lead_name"] = df_projects["team_lead"].map(lambda x: id_to_name_map.get(x, "Unassigned") if pd.notna(x) else "Unassigned")

                # --- TAB 1: PORTFOLIO HEALTH ---
                with dash_tab1:
                    total_projects = len(projects_data)
                    active_projects = len([p for p in projects_data if p.get('status', '').lower() == 'active'])
                    hold_projects = len([p for p in projects_data if p.get('status', '').lower() == 'on hold'])
                    critical_projects = len([p for p in projects_data if p.get('tracking_status', '').lower() == 'critical'])
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric(label="Total Active Projects", value=active_projects)
                    with col2:
                        st.metric(label="Projects On Hold", value=hold_projects)
                    with col3:
                        st.metric(label="Critical Status", value=critical_projects)
                    with col4:
                        st.metric(label="Total Portfolio", value=total_projects)
                        
                    st.divider()
                    st.subheader("⚠️ Action Required")
                    
                    action_required_df = df_projects[df_projects['tracking_status'].isin(["Critical", "Delay"])]
                    
                    if not action_required_df.empty:
                        display_cols = ["project_code", "project_name", "team_lead_name", "current_stage", "tracking_status", "status"]
                        exist_cols = [c for c in display_cols if c in action_required_df.columns]
                        st.dataframe(action_required_df[exist_cols], use_container_width=True, hide_index=True)
                    else:
                        st.success("All projects are currently on track! No critical actions required.")

                # --- TAB 2: RESOURCE ALLOCATION ---
                with dash_tab2:
                    if logs_data:
                        df_logs = pd.DataFrame(logs_data)
                        df_logs["Person"] = df_logs["team_member_id"].map(lambda x: id_to_name_map.get(x, "Unknown"))
                        df_logs["Project"] = df_logs["project_code"].apply(lambda x: "Internal/No Project" if pd.isna(x) else f"{x} - {project_map.get(x, 'Unknown')}")
                        
                        df_logs = df_logs.rename(columns={
                            "log_date": "Date", "activity_type": "Activity", "hours_spent": "Hours", "description": "Description"
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
                            
                        st.divider()
                        st.markdown("**Raw Timesheet Audit Logs**")
                        log_display_cols = ["Date", "Person", "Project", "Hours", "Activity", "Description"]
                        existing_log_cols = [col for col in log_display_cols if col in df_logs.columns]
                        st.dataframe(df_logs[existing_log_cols].sort_values(by="Date", ascending=False), use_container_width=True, hide_index=True)
                    else:
                        st.info("No timesheet logs found in the database yet.")

                # --- TAB 3: MASTER DIRECTORY ---
                with dash_tab3:
                    st.subheader("Project Master Directory")
                    
                    st.markdown("##### 🚀 Access Project Cockpit")
                    cockpit_col1, cockpit_col2 = st.columns([3, 1])
                    with cockpit_col1:
                        proj_list = [f"{row['project_code']} - {row['project_name']}" for _, row in df_projects.iterrows()]
                        selected_for_cockpit = st.selectbox("Select Project to View Cockpit", options=proj_list, label_visibility="collapsed")
                    with cockpit_col2:
                        if st.button("View Cockpit", type="primary", use_container_width=True):
                            code_only = selected_for_cockpit.split(" - ")[0]
                            st.session_state.selected_project_code = code_only
                            st.rerun()

                    st.divider()
                    
                    lead_options = ["All"] + sorted([str(x) for x in df_projects['team_lead_name'].unique() if pd.notna(x)])
                    stage_options = ["All"] + sorted([str(x) for x in df_projects['current_stage'].unique() if pd.notna(x)])
                    
                    filter_col1, filter_col2 = st.columns(2)
                    with filter_col1:
                        selected_lead = st.selectbox("Filter by Lead Architect", options=lead_options)
                    with filter_col2:
                        selected_stage = st.selectbox("Filter by Current Stage", options=stage_options)
                    
                    filtered_dir = df_projects.copy()
                    if selected_lead != "All":
                        filtered_dir = filtered_dir[filtered_dir['team_lead_name'] == selected_lead]
                    if selected_stage != "All":
                        filtered_dir = filtered_dir[filtered_dir['current_stage'] == selected_stage]
                    
                    proj_display_columns = ["project_code", "project_name", "location", "team_lead_name", "current_stage", "tracking_status", "status"]
                    proj_existing_columns = [col for col in proj_display_columns if col in filtered_dir.columns]
                    st.dataframe(filtered_dir[proj_existing_columns], use_container_width=True, hide_index=True)

            else:
                st.info("No projects found in the database. Add some projects to see them here.")
            
    except Exception as e:
        st.error(f"Error fetching dashboard data: {e}")

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
                    st.subheader("Frictionless Project Update")
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
                        st.markdown("##### 1. Master Status Adjustments")
                        col_s1, col_s2 = st.columns(2)
                        with col_s1:
                            new_stage = st.selectbox("Current Stage", options=stage_options, index=stage_idx)
                        with col_s2:
                            new_tracking = st.selectbox("Tracking Status", options=status_options, index=tracking_idx)
                        
                        new_main_status = None
                        if selected_member_role in ["Principal Architect", "Manager"]:
                            new_main_status = st.selectbox("Main Project Status", options=main_status_options, index=main_idx)
                        
                        st.divider()
                        
                        st.markdown("##### 2. Log Activity Ledger & Escalations")
                        update_category = st.selectbox("Category", ["Design", "Client", "Site", "Vendor", "Statutory"])
                        update_text = st.text_area("Update Details (Optional but recommended)")
                        
                        st.markdown("**Principal Escalation**")
                        flag_principal = st.checkbox("🔴 Flag for Principal Intervention")
                        action_type = st.selectbox("Action Type (If Flagged)", ["None", "Site Visit Required", "Client Call Required", "Design Approval", "Financial Review"])
                        
                        if st.form_submit_button("Submit Combined Update", type="primary"):
                            error = False
                            if flag_principal and action_type == "None":
                                st.error("Please select an Action Type when flagging for the Principal.")
                                error = True
                            
                            if not error:
                                update_payload = {
                                    "current_stage": new_stage,
                                    "tracking_status": new_tracking
                                }
                                if new_main_status:
                                    update_payload["status"] = new_main_status
                                
                                try:
                                    supabase.table("projects").update(update_payload).eq("project_code", actual_proj_code).execute()
                                    
                                    if update_text.strip() or flag_principal:
                                        # UPDATED: Changed key to 'author_id' and 'content' based on schema mapping
                                        new_entry = {
                                            "project_code": actual_proj_code,
                                            "author_id": selected_member_id, 
                                            "category": update_category,
                                            "content": update_text.strip() if update_text.strip() else "Flagged for intervention.",
                                            "is_principal_action_required": flag_principal,
                                            "action_type": action_type if flag_principal else None
                                        }
                                        supabase.table("project_ledger").insert(new_entry).execute()
                                    
                                    st.success(f"Project {actual_proj_code} updated and ledger entry recorded successfully!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed to update project data: {e}")

        # === TAB 3: TIME TRACKER & ANALYTICS ===
        with tab3:
            st.subheader("Submit Daily Log")
            
            log_project_options = {"Internal/No Project": "INTERNAL"}
            if projects_data:
                log_project_options.update({f"{p['project_code']} ({p.get('project_name', 'Unknown')})": p['project_code'] for p in projects_data})
            
            with st.form("daily_log_form", clear_on_submit=True):
                log_date = st.date_input("Date", value=datetime.today())
                log_proj_display = st.selectbox("Project", options=list(log_project_options.keys()))
                
                if not global_activity_types:
                    global_activity_types = ['Drawing', 'Admin']
                log_activity = st.selectbox("Activity Type", options=global_activity_types)
                
                col_h, col_m = st.columns(2)
                with col_h:
                    hours_input = st.selectbox("Hours", options=list(range(13)), index=1)
                with col_m:
                    minutes_input = st.selectbox("Minutes", options=[0, 15, 30, 45], index=0)
                
                if not global_tags:
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
                        # UPDATED: Enforce Foreign Key Constraint (Convert INTERNAL to None/NULL)
                        actual_log_code = log_project_options[log_proj_display]
                        final_log_code = None if actual_log_code == "INTERNAL" else actual_log_code

                        log_payload = {
                            "team_member_id": selected_member_id,
                            "project_code": final_log_code,
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
                            
                            df_filtered_logs["project_name"] = df_filtered_logs["project_code"].apply(lambda x: "Internal/No Project" if pd.isna(x) else f"{x} - {project_map.get(x, 'Unknown')}")
                            df_filtered_logs = df_filtered_logs.rename(columns={
                                "log_date": "Date", "project_name": "Project", "activity_type": "Activity",
                                "hours_spent": "Hours", "tags": "Tags", "description": "Description"
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
    if selected_member_role not in ["Principal Architect", "Manager"]:
        st.error("Access Denied: You must be a Principal Architect or Manager to view this page.")
    else:
        st.title("Admin Settings")
        st.markdown("Manage global application configurations and your team directory.")
        
        st.subheader("Global Configurations")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            with st.form("activity_settings_form"):
                st.markdown("**Activity Types**")
                active_activities = st.multiselect("Current Types", options=global_activity_types, default=global_activity_types)
                new_activity = st.text_input("Add New Type")
                
                if st.form_submit_button("Save Activities", type="primary"):
                    final_activities = active_activities.copy()
                    if new_activity.strip() and new_activity.strip() not in final_activities:
                        final_activities.append(new_activity.strip())
                    try:
                        supabase.table("aos_settings").update({"options": final_activities}).eq("category", "activity_types").execute()
                        st.success("Updated!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                        
        with col2:
            with st.form("tags_settings_form"):
                st.markdown("**Timesheet Tags**")
                active_tags = st.multiselect("Current Tags", options=global_tags, default=global_tags)
                new_tag = st.text_input("Add New Tag")
                
                if st.form_submit_button("Save Tags", type="primary"):
                    final_tags = active_tags.copy()
                    if new_tag.strip() and new_tag.strip() not in final_tags:
                        final_tags.append(new_tag.strip())
                    try:
                        supabase.table("aos_settings").update({"options": final_tags}).eq("category", "tags").execute()
                        st.success("Updated!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                        
        with col3:
            with st.form("designation_settings_form"):
                st.markdown("**Company Designations**")
                active_designations = st.multiselect("Current Designations", options=global_designations, default=global_designations)
                new_designation = st.text_input("Add New Designation")
                
                if st.form_submit_button("Save Designations", type="primary"):
                    final_designations = active_designations.copy()
                    if new_designation.strip() and new_designation.strip() not in final_designations:
                        final_designations.append(new_designation.strip())
                    try:
                        supabase.table("aos_settings").upsert({"category": "designations", "options": final_designations}).execute()
                        st.success("Updated!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

        st.divider()
        st.subheader("Manage Team Directory")
        dir_col1, dir_col2 = st.columns(2)
        
        with dir_col1:
            with st.form("add_employee_form", clear_on_submit=True):
                st.markdown("**Add New Employee**")
                new_emp_name = st.text_input("Full Name")
                new_emp_role = st.selectbox("Designation", options=global_designations)
                
                if st.form_submit_button("Add Employee", type="primary"):
                    if not new_emp_name.strip():
                        st.error("Please provide a valid name.")
                    else:
                        try:
                            supabase.table("team_members").insert({
                                "full_name": new_emp_name.strip(),
                                "role": new_emp_role
                            }).execute()
                            st.success(f"{new_emp_name} added successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to add employee: {e}")

        with dir_col2:
            st.markdown("**Edit or Remove Employee**")
            if team_data:
                emp_to_edit_name = st.selectbox("Select Employee", options=list(name_to_id_map.keys()), key="edit_emp_select")
                emp_to_edit_id = name_to_id_map.get(emp_to_edit_name)
                current_role = name_to_role_map.get(emp_to_edit_name, "Team Member")
                
                role_idx = global_designations.index(current_role) if current_role in global_designations else 0
                updated_role = st.selectbox("Update Designation", options=global_designations, index=role_idx)
                
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Update Role", use_container_width=True):
                        try:
                            supabase.table("team_members").update({"role": updated_role}).eq("id", emp_to_edit_id).execute()
                            st.success("Role updated successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Update failed: {e}")
                with c2:
                    if st.button("Remove User", type="primary", use_container_width=True):
                        try:
                            supabase.table("team_members").delete().eq("id", emp_to_edit_id).execute()
                            st.success(f"{emp_to_edit_name} removed from the system.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Removal failed: {e}")
            else:
                st.info("No employees available to edit.")