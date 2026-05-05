import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timedelta
import pandas as pd
import altair as alt
import time
import math

# --- Page Configuration ---
st.set_page_config(page_title="AOS | Architect's Operating System", layout="wide")

# --- Session State Initialization ---
if 'current_user' not in st.session_state:
    st.session_state.current_user = None

if 'selected_project_code' not in st.session_state:
    st.session_state.selected_project_code = None

if 'daily_log_cart' not in st.session_state:
    st.session_state.daily_log_cart = []

if 'grid_key' not in st.session_state: 
    st.session_state.grid_key = 0

if 'roster_key' not in st.session_state:
    st.session_state.roster_key = 0

if 'admin_emp_id' not in st.session_state:
    st.session_state.admin_emp_id = None

def go_to_dashboard():
    st.session_state.selected_project_code = None

def open_hub(project_code):
    st.session_state.selected_project_code = project_code

def go_to_roster():
    st.session_state.admin_emp_id = None

# --- Algorithmic Code Name Engine ---
def generate_code_name(first, father, last, existing_codes):
    f_val = (first or "").strip()
    m_val = (father or "").strip()
    l_val = (last or "").strip()
    
    f_init = f_val[0].upper() if f_val else ""
    m_init = m_val[0].upper() if m_val else ""
    l_init = l_val[0].upper() if l_val else ""
    
    base_code = f"{f_init}{m_init}{l_init}"
    if not base_code:
        base_code = "EMP" 
        
    final_code = base_code
    counter = 1
    while final_code in existing_codes:
        final_code = f"{base_code}-{counter}"
        counter += 1
        
    return final_code

# --- Pre-Save Sanitization & Calculation Engine ---
def sanitize_and_calculate_profile(raw_profile_data):
    processed = raw_profile_data.copy()

    if 'Past Employment' in processed:
        pe_records = processed['Past Employment']
        if isinstance(pe_records, list):
            df_pe = pd.DataFrame(pe_records)
            if not df_pe.empty and 'Company Name' in df_pe.columns:
                df_pe['Company Name'] = df_pe['Company Name'].fillna('').astype(str).str.strip()
                df_pe = df_pe[df_pe['Company Name'] != '']

                if not df_pe.empty:
                    df_pe['From Date'] = pd.to_datetime(df_pe['From Date'], errors='coerce')
                    df_pe['To Date'] = pd.to_datetime(df_pe['To Date'], errors='coerce')

                    total_days = 0
                    for _, row in df_pe.iterrows():
                        if pd.notna(row['From Date']) and pd.notna(row['To Date']):
                            diff = (row['To Date'] - row['From Date']).days
                            if diff > 0:
                                total_days += diff

                    processed['Total Experience'] = str(round(total_days / 365.0, 1))

                    df_pe = df_pe.sort_values(by='To Date', ascending=False)
                    df_pe['From Date'] = df_pe['From Date'].dt.strftime('%Y-%m-%d').fillna("")
                    df_pe['To Date'] = df_pe['To Date'].dt.strftime('%Y-%m-%d').fillna("")
                    processed['Past Employment'] = df_pe.fillna("").to_dict('records')
                else:
                    processed['Past Employment'] = []
                    processed['Total Experience'] = "0.0"

    if 'Educational Background' in processed:
        ed_records = processed['Educational Background']
        if isinstance(ed_records, list):
            df_ed = pd.DataFrame(ed_records)
            if not df_ed.empty and 'Degree' in df_ed.columns:
                df_ed['Degree'] = df_ed['Degree'].fillna('').astype(str).str.strip()
                df_ed = df_ed[df_ed['Degree'] != '']

                if not df_ed.empty:
                    df_ed['Passing Year'] = pd.to_numeric(df_ed['Passing Year'], errors='coerce')
                    df_ed = df_ed.sort_values(by='Passing Year', ascending=False)
                    df_ed['Passing Year'] = df_ed['Passing Year'].astype('Int64').astype(str).replace('<NA>', '')
                    processed['Educational Background'] = df_ed.fillna("").to_dict('records')
                else:
                    processed['Educational Background'] = []

    return processed

# --- Database Connection ---
@st.cache_resource
def init_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# --- Global Context & Settings Fetch ---
try:
    team_response = supabase.table("team_members").select("*").execute()
    settings_response = supabase.table("aos_settings").select("*").execute()
    taxonomy_response = supabase.table("task_taxonomy").select("*").execute()
    projects_response_global = supabase.table("projects").select("*").execute()
    
    team_data = team_response.data
    settings_data = settings_response.data
    taxonomy_data = taxonomy_response.data
    projects_data_global = projects_response_global.data
    
    name_to_id_map = {member['full_name']: member['id'] for member in team_data} if team_data else {}
    id_to_name_map = {member['id']: member['full_name'] for member in team_data} if team_data else {}
    name_to_role_map = {member['full_name']: member.get('role', 'Team Member') for member in team_data} if team_data else {}
    
    settings_map = {row['category']: row.get('options', []) for row in settings_data} if settings_data else {}
    global_activity_types = settings_map.get("activity_types", [])
    global_tags = settings_map.get("tags", [])
    global_designations = settings_map.get("designations", ["Principal Architect", "Manager", "Team Member"])
    global_custom_fields = settings_map.get("custom_profile_fields", [])
    global_project_categories = settings_map.get("project_categories", [])
    global_project_sub_categories = settings_map.get("project_sub_categories", [])
    
    taxonomy_map = {row['category']: row.get('deliverables', []) for row in taxonomy_data} if taxonomy_data else {}
    
except Exception as e:
    st.error(f"Error loading global configuration: {e}")
    team_data, global_activity_types, global_tags, global_designations, global_custom_fields, taxonomy_map, projects_data_global = [], [], [], [], [], {}, []
    global_project_categories, global_project_sub_categories = [], []

if not team_data:
    st.warning("No team members found in the database. Please configure the database.")
    st.stop()

# ==========================================
# LOGIN GATE
# ==========================================
if st.session_state.current_user is None:
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center;'>AOS Authentication</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("login_form"):
            user_options = ["-- Select Your Name --"] + list(name_to_id_map.keys())
            selected_user = st.selectbox("System User", options=user_options, label_visibility="collapsed")
            
            submit_login = st.form_submit_button("Enter Workspace", use_container_width=True)
            
            if submit_login:
                if selected_user == "-- Select Your Name --":
                    st.error("Please select a valid user to log in.")
                else:
                    st.session_state.current_user = {
                        "name": selected_user,
                        "id": name_to_id_map[selected_user],
                        "role": name_to_role_map[selected_user]
                    }
                    st.rerun()
    st.stop()

# --- Active Session Details ---
selected_member_name = st.session_state.current_user["name"]
selected_member_id = st.session_state.current_user["id"]
selected_member_role = st.session_state.current_user["role"]

# --- Sidebar Navigation & RBAC ---
st.sidebar.title("AOS Navigation")
st.sidebar.markdown(f"**User:** {selected_member_name}<br>**Role:** {selected_member_role}", unsafe_allow_html=True)
st.sidebar.divider()

nav_pages = []
if selected_member_role in ["Principal Architect", "Manager"]:
    nav_pages.extend(["Principal Dashboard", "Assign Task", "Team Board", "Admin Settings"])
else:
    nav_pages.extend(["Assign Task", "Team Board"])

page = st.sidebar.radio("Go to", nav_pages)

st.sidebar.divider()
if st.sidebar.button("Log Out", use_container_width=True):
    st.session_state.current_user = None
    st.session_state.selected_project_code = None
    st.session_state.admin_emp_id = None
    st.rerun()

# ==========================================
# GLOBAL PROJECT HUB OVERLAY
# ==========================================
if st.session_state.selected_project_code:
    if st.button("Close Project Hub", use_container_width=False):
        go_to_dashboard()
        st.rerun()
        
    target_code = st.session_state.selected_project_code
    proj_details = next((p for p in projects_data_global if p['project_code'] == target_code), None)
    
    if proj_details:
        lead_name = id_to_name_map.get(proj_details.get('team_lead'), "Unassigned")
        
        st.title(f"{proj_details.get('project_name', 'Unnamed Project')}")
        
        h_col1, h_col2, h_col3, h_col4, h_col5 = st.columns(5)
        h_col1.metric("Project Code", target_code)
        h_col2.metric("Client Name", proj_details.get('client_name', 'Not Set'))
        h_col3.metric("Team Lead", lead_name)
        h_col4.metric("Current Stage", proj_details.get('current_stage', 'Not Set'))
        h_col5.metric("Tracking Status", proj_details.get('tracking_status', 'Not Set'))
        
        st.divider()
        
        tab_overview, tab_deliverables, tab_field, tab_comms, tab_vault = st.tabs([
            "Overview & Timeline", 
            "Design & Deliverables", 
            "Field & Execution", 
            "Comms & Approvals", 
            "Document Vault"
        ])
        
        try:
            ledger_response_hub = supabase.table("project_ledger").select("*").execute()
            ledger_data_hub = ledger_response_hub.data
        except:
            ledger_data_hub = []
            
        df_ledger = pd.DataFrame(ledger_data_hub) if ledger_data_hub else pd.DataFrame()
        if not df_ledger.empty and 'project_code' in df_ledger.columns:
            proj_ledger = df_ledger[df_ledger['project_code'] == target_code].copy()
            if not proj_ledger.empty:
                proj_ledger['created_at'] = pd.to_datetime(proj_ledger['created_at'])
                proj_ledger = proj_ledger.sort_values('created_at', ascending=False)
        else:
            proj_ledger = pd.DataFrame()

        with tab_overview:
            col_vitals, col_timeline = st.columns([1, 2])
            with col_vitals:
                st.subheader("Project Vitals")
                st.markdown(f"**Main Status:** {proj_details.get('status', 'Not Set')}")
                st.markdown(f"**Category:** {proj_details.get('category', 'Not Set')} - {proj_details.get('sub_category', 'Not Set')}")
                st.markdown(f"**Scale:** {proj_details.get('scale', 'Not Set')}")
                st.markdown(f"**City:** {proj_details.get('city', 'Not Set')}")
                st.markdown(f"**Address:** {proj_details.get('address', 'Not Set')}")
                st.markdown(f"**Architect:** {proj_details.get('architect', 'Not Set')}")
                
                s_date = proj_details.get('start_date')
                c_date = proj_details.get('completion_date')
                st.markdown(f"**Start Date:** {s_date if s_date else 'Not Set'}")
                st.markdown(f"**Target Completion:** {c_date if c_date else 'Not Set'}")
            
            with col_timeline:
                st.subheader("Activity Timeline")
                if not proj_ledger.empty:
                    top_10 = proj_ledger.head(10)
                    for _, row in top_10.iterrows():
                        date_str = row['created_at'].strftime('%b %d, %Y')
                        author = id_to_name_map.get(row.get('author_id'), 'Unknown')
                        cat = row.get('category', 'Uncategorized')
                        content = row.get('content', '')
                        st.markdown(f"**{date_str} | {cat}** (by {author})")
                        st.write(content)
                        st.divider()
                else:
                    st.write("No activity logged yet.")

        with tab_deliverables:
            st.info("Module under construction in Phase 2.")

        with tab_field:
            st.info("Module under construction in Phase 2.")

        with tab_comms:
            st.subheader("Communications & Approvals")
            if not proj_ledger.empty:
                cat_mask = proj_ledger.get('category', pd.Series()).isin(['Client', 'Approvals', 'Client Meeting'])
                esc_mask = proj_ledger.get('escalation_status', pd.Series()).notna() & (proj_ledger.get('escalation_status') != '')
                comms_df = proj_ledger[cat_mask | esc_mask].copy()
                
                if not comms_df.empty:
                    comms_df['Author'] = comms_df['author_id'].map(lambda x: id_to_name_map.get(x, "Unknown"))
                    comms_df['Date'] = comms_df['created_at'].dt.strftime('%Y-%m-%d')
                    
                    display_cols = {
                        "Date": "Date", 
                        "category": "Category", 
                        "Author": "Author", 
                        "content": "Details", 
                        "action_type": "Action Required", 
                        "escalation_status": "Status"
                    }
                    comms_ui = comms_df.rename(columns=display_cols)
                    comms_ui = comms_ui[[v for v in display_cols.values() if v in comms_ui.columns]]
                    st.dataframe(comms_ui, use_container_width=True, hide_index=True)
                else:
                    st.write("No communications or approvals logged yet.")
            else:
                st.write("No activity logged yet.")

        with tab_vault:
            st.info("Module under construction in Phase 2.")
            
    else:
        st.error("Project details not found.")

# ==========================================
# MAIN ROUTING (Only executed if Hub is closed)
# ==========================================
else:
    # ==========================================
    # PAGE 1: PRINCIPAL DASHBOARD
    # ==========================================
    if page == "Principal Dashboard":
        st.title("Principal Dashboard")
        
        try:
            projects_data = projects_data_global
            tasks_response = supabase.table("tasks").select("*").execute()
            logs_response = supabase.table("team_logs").select("*").execute()
            ledger_response = supabase.table("project_ledger").select("*").execute() 
            
            tasks_data = tasks_response.data
            logs_data = logs_response.data
            ledger_data = ledger_response.data
            
            project_map = {p['project_code']: p.get('project_name', 'Unknown') for p in projects_data} if projects_data else {}
        except Exception as e:
            st.error(f"Error loading dashboard data: {e}")
            projects_data, tasks_data, logs_data, ledger_data, project_map = [], [], [], [], {}

        df_ledger = pd.DataFrame(ledger_data) if ledger_data else pd.DataFrame()
        if not df_ledger.empty and 'is_principal_action_required' in df_ledger.columns:
            action_req_df = df_ledger[df_ledger['is_principal_action_required'] == True].copy()
            
            if not action_req_df.empty:
                st.subheader("Principal Intervention Required")
                
                action_req_df['action_type'] = action_req_df['action_type'].fillna('Uncategorized')
                grouped_escalations = action_req_df.groupby('action_type')
                
                for action_type, group in grouped_escalations:
                    with st.expander(f"{action_type} ({len(group)} Pending Actions)", expanded=True):
                        for idx, row in group.sort_values('created_at', ascending=False).iterrows():
                            proj_code = row['project_code']
                            proj_name = project_map.get(proj_code, 'Unknown')
                            req_by = id_to_name_map.get(row.get('author_id'), 'Unknown')
                            date_str = pd.to_datetime(row['created_at']).strftime('%b %d, %Y')
                            
                            c1, c2, c3 = st.columns([5, 3, 2])
                            with c1:
                                st.write(f"**{proj_code} - {proj_name}** | {date_str}")
                            with c2:
                                st.write(f"Lead: {req_by}")
                            with c3:
                                st.button("View Hub", key=f"flag_hub_{row.get('id', idx)}", on_click=open_hub, args=(proj_code,), use_container_width=True)
                            st.divider()
        
        if projects_data:
            dash_tab1, dash_tab2, dash_tab3 = st.tabs(["Portfolio Health", "Resource Allocation", "Master Directory"])
            
            df_projects = pd.DataFrame(projects_data)
            if "team_lead" in df_projects.columns:
                df_projects["team_lead_name"] = df_projects["team_lead"].map(lambda x: id_to_name_map.get(x, "Unassigned") if pd.notna(x) else "Unassigned")

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
                st.subheader("Action Required")
                
                action_required_df = df_projects[df_projects['tracking_status'].isin(["Critical", "Delay"])]
                
                if not action_required_df.empty:
                    display_cols = ["project_code", "project_name", "team_lead_name", "current_stage", "tracking_status", "status"]
                    exist_cols = [c for c in display_cols if c in action_required_df.columns]
                    st.dataframe(action_required_df[exist_cols], use_container_width=True, hide_index=True)
                else:
                    st.write("All projects are currently on track.")

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
                            st.write("Total Hours Logged this Week by Team Member")
                            member_hours = df_week.groupby("Person")["Hours"].sum().reset_index()
                            st.bar_chart(member_hours.set_index("Person"))
                            
                        with chart_col2:
                            st.write("Firm-wide Activity Breakdown (This Week)")
                            activity_hours = df_week.groupby("Activity")["Hours"].sum().reset_index()
                            pie_chart = alt.Chart(activity_hours).mark_arc().encode(
                                theta=alt.Theta(field="Hours", type="quantitative"),
                                color=alt.Color(field="Activity", type="nominal"),
                                tooltip=["Activity", "Hours"]
                            ).properties(height=300)
                            st.altair_chart(pie_chart, use_container_width=True)
                    else:
                        st.write("No hours logged yet this week.")
                        
                    st.divider()
                    st.write("Raw Timesheet Audit Logs")
                    log_display_cols = ["Date", "Person", "Project", "Hours", "Activity", "Description"]
                    existing_log_cols = [col for col in log_display_cols if col in df_logs.columns]
                    st.dataframe(df_logs[existing_log_cols].sort_values(by="Date", ascending=False), use_container_width=True, hide_index=True)
                else:
                    st.write("No timesheet logs found in the database yet.")

            with dash_tab3:
                st.subheader("Project Master Directory")
                
                st.write("Access Project Hub")
                hub_col1, hub_col2 = st.columns([3, 1])
                with hub_col1:
                    proj_list = [f"{row['project_code']} - {row['project_name']}" for _, row in df_projects.iterrows()]
                    selected_for_hub = st.selectbox("Select Project to View Hub", options=proj_list, label_visibility="collapsed")
                with hub_col2:
                    if st.button("View Hub", type="primary", use_container_width=True):
                        code_only = selected_for_hub.split(" - ")[0]
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
            st.write("No projects found in the database. Add some projects to see them here.")

    # ==========================================
    # PAGE 2: ASSIGN TASK
    # ==========================================
    elif page == "Assign Task":
        st.title("Assign Task")
        
        try:
            projects_data = projects_data_global
            
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
        elif not taxonomy_map:
            st.warning("No task taxonomy found in database. Please ask an Admin to configure Task SOPs.")
        else:
            st.subheader("Task Details")
            
            selected_project_display = st.selectbox("Select Project", options=list(project_options.keys()))
            selected_assignee_name = st.selectbox("Assign To", options=list(name_to_id_map.keys()))
            
            st.divider()
            st.write("Task Specifications")
            
            col1, col2 = st.columns(2)
            with col1:
                task_category = st.selectbox("Task Category", options=list(taxonomy_map.keys()))
            with col2:
                task_deliverables_list = taxonomy_map.get(task_category, [])
                task_deliverable = st.selectbox("Standard Deliverable", options=task_deliverables_list)
                
            additional_notes = st.text_input("Additional Notes (Optional)", placeholder="e.g., Check column grid dimensions on ground floor.")
            deadline = st.date_input("Deadline", min_value=datetime.today())
            
            if st.button("Assign Task", type="primary"):
                if not task_deliverable:
                    st.error("Please select a standard deliverable.")
                else:
                    final_description = f"{task_category} - {task_deliverable}"
                    if (additional_notes or "").strip():
                        final_description += f". Notes: {(additional_notes or '').strip()}"
                    
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
                        st.success(f"Task assigned to {selected_assignee_name} for project {actual_project_code}.")
                    except Exception as e:
                        st.error(f"Failed to assign task: {e}")

    # ==========================================
    # PAGE 3: TEAM BOARD
    # ==========================================
    elif page == "Team Board":
        st.title("Team Board")
        
        try:
            tasks_response = supabase.table("tasks").select("*").execute()
            logs_response = supabase.table("team_logs").select("*").execute() 
            ledger_response = supabase.table("project_ledger").select("*").execute()
            
            tasks_data = tasks_response.data
            projects_data = projects_data_global
            logs_data = logs_response.data
            ledger_data = ledger_response.data
            
            project_map = {p['project_code']: p.get('project_name', 'Unknown') for p in projects_data} if projects_data else {}
            
            tab1, tab2, tab3, tab4 = st.tabs(["My Tasks", "Update Projects", "Time Tracker", "My Profile"])
            
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
                            st.success("Task status updated.")
                            st.rerun() 
                        except Exception as e:
                            st.error(f"Failed to update task: {e}")
                else:
                    st.write("You currently have no active tasks assigned.")
                    
            # === TAB 2: UPDATE PROJECTS ===
            with tab2:
                if projects_data:
                    if selected_member_role in ["Principal Architect", "Manager"]:
                        allowed_projects = projects_data
                    else:
                        allowed_projects = [p for p in projects_data if p.get('team_lead') == selected_member_id]
                    
                    if not allowed_projects:
                        st.write("You are not assigned as the Team Lead for any projects.")
                    else:
                        my_active = len([p for p in allowed_projects if p.get('status', '').lower() == 'active'])
                        my_critical = len([p for p in allowed_projects if p.get('tracking_status', '').lower() == 'critical'])
                        
                        st.subheader("Team Lead Command Center")
                        m_col1, m_col2 = st.columns(2)
                        m_col1.metric("My Active Projects", my_active)
                        m_col2.metric("My Critical Projects", my_critical)
                        st.divider()
                        
                        allowed_proj_codes = [p['project_code'] for p in allowed_projects]
                        if ledger_data:
                            pending_feedback = [l for l in ledger_data if l.get('escalation_status') == 'Pending Lead Action' and l.get('project_code') in allowed_proj_codes]
                            
                            if pending_feedback:
                                with st.expander("Principal Feedback", expanded=True):
                                    for idx, fb in enumerate(pending_feedback):
                                        fb_date = pd.to_datetime(fb['created_at']).strftime('%b %d, %Y')
                                        fb_proj = fb['project_code']
                                        fb_text = fb.get('principal_feedback', 'No feedback provided.')
                                        
                                        st.write(f"{fb_proj} | {fb_date}")
                                        st.write(f"Principal Feedback: {fb_text}")
                                        
                                        if st.button("Acknowledge and Clear", key=f"ack_fb_{fb['id']}"):
                                            try:
                                                supabase.table("project_ledger").update({"escalation_status": "Resolved"}).eq("id", fb['id']).execute()
                                                st.toast("Feedback Acknowledged")
                                                time.sleep(0.5)
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"Failed to clear feedback: {e}")
                                    st.divider()
                        
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
                            col_left, col_right = st.columns(2)
                            
                            with col_left:
                                st.write("Project Status")
                                new_stage = st.selectbox("Current Stage", options=stage_options, index=stage_idx)
                                new_tracking = st.selectbox("Tracking Status", options=status_options, index=tracking_idx)
                                
                                new_main_status = None
                                if selected_member_role in ["Principal Architect", "Manager"]:
                                    new_main_status = st.selectbox("Main Project Status", options=main_status_options, index=main_idx)
                                    
                            with col_right:
                                st.write("Log Activity Ledger")
                                update_category = st.selectbox("Category", ["Design", "Client", "Site", "Vendor", "Statutory"])
                                update_text = st.text_area("Update Details", placeholder="Optional but recommended")
                                
                                st.write("Principal Escalation")
                                flag_principal = st.checkbox("Flag for Principal Intervention")
                                action_type = st.selectbox("Action Type (If Flagged)", ["None", "Site Visit Required", "Client Call Required", "Design Approval", "Financial Review"])
                            
                            submit_update = st.form_submit_button("Submit Combined Update", type="primary", use_container_width=True)
                            
                            if submit_update:
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
                                        
                                        if (update_text or "").strip() or flag_principal:
                                            new_entry = {
                                                "project_code": actual_proj_code,
                                                "author_id": selected_member_id, 
                                                "category": update_category,
                                                "content": (update_text or "").strip() if (update_text or "").strip() else "Flagged for intervention.",
                                                "is_principal_action_required": flag_principal,
                                                "action_type": action_type if flag_principal else None,
                                                "escalation_status": "Pending" if flag_principal else None
                                            }
                                            supabase.table("project_ledger").insert(new_entry).execute()
                                        
                                        st.success("Project Updated and Logged Successfully")
                                        time.sleep(0.5)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Failed to update project data: {e}")

            # === TAB 3: TIME TRACKER & ANALYTICS ===
            with tab3:
                col_form, col_history = st.columns([1, 1.5])
                
                with col_form:
                    st.subheader("Queue Activity")
                    log_project_options = {"Internal/No Project": "INTERNAL"}
                    if projects_data:
                        log_project_options.update({f"{p['project_code']} ({p.get('project_name', 'Unknown')})": p['project_code'] for p in projects_data})
                    
                    log_date = st.date_input("Date", value=datetime.today())
                    log_proj_display = st.selectbox("Project", options=list(log_project_options.keys()))
                    
                    if not global_activity_types:
                        global_activity_types = ['Drawing', 'Admin']
                    log_activity = st.selectbox("Activity Type", options=global_activity_types)
                    
                    col_start, col_end = st.columns(2)
                    with col_start:
                        start_time = st.time_input("Start Time", value=datetime.now().replace(hour=9, minute=0, second=0))
                    with col_end:
                        end_time = st.time_input("End Time", value=datetime.now().replace(hour=17, minute=0, second=0))
                    
                    col_tags, col_new_tag = st.columns([3, 1])
                    with col_tags:
                        if not global_tags:
                            global_tags = ['Concept', 'Other']
                        log_tags = st.multiselect("Tags", options=global_tags)
                        
                    with col_new_tag:
                        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                        new_inline_tag = st.text_input("New Tag", placeholder="Tag Name", label_visibility="collapsed")
                        if st.button("Add", use_container_width=True):
                            if (new_inline_tag or "").strip() and (new_inline_tag or "").strip() not in global_tags:
                                updated_tags = global_tags + [(new_inline_tag or "").strip()]
                                try:
                                    supabase.table("aos_settings").update({"options": updated_tags}).eq("category", "tags").execute()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed to add tag: {e}")
                    
                    log_desc = st.text_area("Brief Description", placeholder="e.g., Modeled the ground floor structural layout...")
                    
                    if st.button("Add to Today's Timesheet", type="primary", use_container_width=True):
                        s_dt = datetime.combine(log_date, start_time)
                        e_dt = datetime.combine(log_date, end_time)
                        if e_dt < s_dt:
                            e_dt += timedelta(days=1)
                        total_time = (e_dt - s_dt).total_seconds() / 3600.0
                        
                        if total_time <= 0:
                            st.error("Please ensure the End Time is after the Start Time.")
                        elif not (log_desc or "").strip():
                            st.error("Please provide a brief description of the work done.")
                        else:
                            actual_log_code = log_project_options[log_proj_display]
                            final_log_code = None if actual_log_code == "INTERNAL" else actual_log_code

                            st.session_state.daily_log_cart.append({
                                "team_member_id": selected_member_id,
                                "project_code": final_log_code,
                                "log_date": log_date.isoformat(),
                                "activity_type": log_activity,
                                "start_time": start_time.strftime("%H:%M:%S"),
                                "end_time": end_time.strftime("%H:%M:%S"),
                                "hours_spent": total_time,
                                "description": (log_desc or "").strip(),
                                "tags": log_tags,
                                "_display_proj": log_proj_display 
                            })
                            st.rerun()

                    st.divider()
                    st.write("Timesheet Cart")
                    if st.session_state.daily_log_cart:
                        cart_df = pd.DataFrame(st.session_state.daily_log_cart)
                        st.dataframe(cart_df[["log_date", "_display_proj", "activity_type", "hours_spent", "description"]], use_container_width=True)
                        
                        if st.button("Submit Entire Day to Database", type="primary", use_container_width=True):
                            payloads = []
                            for item in st.session_state.daily_log_cart:
                                payload = item.copy()
                                del payload["_display_proj"] 
                                payloads.append(payload)
                                
                            try:
                                supabase.table("team_logs").insert(payloads).execute()
                                st.session_state.daily_log_cart = []
                                st.success("All logs submitted successfully.")
                                time.sleep(0.5)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to submit batch: {e}")
                    else:
                        st.write("Your timesheet cart is empty.")

                with col_history:
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
                                    
                                    df_display = df_filtered_logs.sort_values(by="log_date", ascending=False).reset_index(drop=True)
                                    
                                    display_cols_map = {
                                        "log_date": "Date", "project_name": "Project", "activity_type": "Activity",
                                        "hours_spent": "Hours", "tags": "Tags", "description": "Description"
                                    }
                                    df_ui = df_display.rename(columns=display_cols_map)
                                    display_log_cols = list(display_cols_map.values())
                                    
                                    current_grid_key = f"history_grid_{st.session_state.grid_key}"
                                    
                                    st.dataframe(
                                        df_ui[display_log_cols], 
                                        use_container_width=True, 
                                        hide_index=True,
                                        selection_mode="single-row",
                                        on_select="rerun",
                                        key=current_grid_key
                                    )
                                    
                                    if current_grid_key in st.session_state and len(st.session_state[current_grid_key]['selection']['rows']) > 0:
                                        selected_idx = st.session_state[current_grid_key]['selection']['rows'][0]
                                        selected_log = df_display.iloc[selected_idx]
                                        
                                        st.divider()
                                        st.subheader("Edit Selected Log")
                                        
                                        with st.form("edit_log_form"):
                                            st.write(f"Project: {selected_log['project_name']} | Date: {selected_log['log_date']}")
                                            
                                            edit_activity = st.selectbox("Activity Type", options=global_activity_types, index=global_activity_types.index(selected_log['activity_type']) if selected_log['activity_type'] in global_activity_types else 0)
                                            
                                            try:
                                                st_time_obj = datetime.strptime(selected_log.get('start_time', "09:00:00"), "%H:%M:%S").time()
                                                en_time_obj = datetime.strptime(selected_log.get('end_time', "17:00:00"), "%H:%M:%S").time()
                                            except:
                                                st_time_obj = datetime.now().replace(hour=9, minute=0, second=0).time()
                                                en_time_obj = datetime.now().replace(hour=17, minute=0, second=0).time()
                                                
                                            ecol_s, ecol_e = st.columns(2)
                                            with ecol_s:
                                                edit_start = st.time_input("Start Time", value=st_time_obj, key="edit_st")
                                            with ecol_e:
                                                edit_end = st.time_input("End Time", value=en_time_obj, key="edit_en")
                                                
                                            edit_desc = st.text_area("Description", value=selected_log['description'])
                                            
                                            if st.form_submit_button("Save Changes", type="primary"):
                                                s_dt = datetime.combine(selected_log['log_date'], edit_start)
                                                e_dt = datetime.combine(selected_log['log_date'], edit_end)
                                                if e_dt < s_dt:
                                                    e_dt += timedelta(days=1)
                                                total_edit_time = (e_dt - s_dt).total_seconds() / 3600.0
                                                
                                                if total_edit_time <= 0:
                                                    st.error("Please ensure the End Time is after the Start Time.")
                                                else:
                                                    update_payload = {
                                                        "activity_type": edit_activity,
                                                        "start_time": edit_start.strftime("%H:%M:%S"),
                                                        "end_time": edit_end.strftime("%H:%M:%S"),
                                                        "hours_spent": total_edit_time,
                                                        "description": (edit_desc or "").strip()
                                                    }
                                                    try:
                                                        supabase.table("team_logs").update(update_payload).eq("id", selected_log['id']).execute()
                                                        st.success("Log updated.")
                                                        st.session_state.grid_key += 1
                                                        time.sleep(0.5)
                                                        st.rerun()
                                                    except Exception as e:
                                                        st.error(f"Failed to update log: {e}")

                                else:
                                    st.write("No logs found for the selected date range.")
                            else:
                                st.write("You haven't submitted any timesheet logs yet.")
                    else:
                        st.write("Please select a valid start and end date to view history.")

            # === TAB 4: MY PROFILE (SELF-SERVICE WITH APPROVAL GATE) ===
            with tab4:
                st.subheader("My Profile")
                
                my_data = next((m for m in team_data if m['id'] == selected_member_id), {})
                prof_data = my_data.get('profile_data') or {}
                
                col_core, col_dyn = st.columns(2)
                
                with col_core:
                    st.write("Core Identifiers (Read-Only)")
                    st.info(f"Full Name: {my_data.get('full_name', 'Not Set')}")
                    st.info(f"Code Name: {my_data.get('code_name', 'Not Set')}")
                    st.info(f"Designation: {my_data.get('role', 'Not Set')}")
                    join_d = my_data.get('join_date')
                    st.info(f"Join Date: {join_d if join_d else 'Not Set'}")
                
                with col_dyn:
                    st.write("Update Dynamic Details")
                    if not global_custom_fields:
                        st.write("No dynamic profile fields have been configured by the Administrator.")
                    else:
                        if my_data.get('pending_profile_data'):
                            st.warning("You have a profile update currently pending Admin approval.")
                            
                        with st.form("my_profile_form"):
                            new_prof_data = {}
                            for field in global_custom_fields:
                                if field == 'Total Experience':
                                    continue 
                                    
                                if field == 'Emergency Contact':
                                    st.write(f"**{field}**")
                                    ec_data = prof_data.get(field, {})
                                    if not isinstance(ec_data, dict): ec_data = {}
                                    ec1, ec2, ec3 = st.columns(3)
                                    ec_name = ec1.text_input("Name", value=ec_data.get('Name', ''), key=f"my_ec_n_{selected_member_id}")
                                    ec_rel = ec2.text_input("Relationship", value=ec_data.get('Relationship', ''), key=f"my_ec_r_{selected_member_id}")
                                    ec_num = ec3.text_input("Contact Number", value=ec_data.get('Contact Number', ''), key=f"my_ec_c_{selected_member_id}")
                                    new_prof_data[field] = {"Name": (ec_name or "").strip(), "Relationship": (ec_rel or "").strip(), "Contact Number": (ec_num or "").strip()}
                                    
                                elif field == 'Educational Background':
                                    st.write(f"**{field}**")
                                    ed_data = prof_data.get(field, [])
                                    if not isinstance(ed_data, list): ed_data = []
                                    df_ed = pd.DataFrame(ed_data, columns=['Degree', 'College/University', 'Passing Year'])
                                    df_ed['Passing Year'] = pd.to_numeric(df_ed['Passing Year'], errors='coerce')
                                    
                                    edited_ed = st.data_editor(
                                        df_ed, 
                                        num_rows="dynamic", 
                                        column_config={"Passing Year": st.column_config.NumberColumn(format="%d")},
                                        key=f"my_ed_{selected_member_id}", 
                                        use_container_width=True
                                    )
                                    new_prof_data[field] = edited_ed.to_dict('records')
                                    
                                elif field == 'Past Employment':
                                    st.write(f"**{field}**")
                                    pe_data = prof_data.get(field, [])
                                    if not isinstance(pe_data, list): pe_data = []
                                    df_pe = pd.DataFrame(pe_data, columns=['Company Name', 'City', 'From Date', 'To Date'])
                                    df_pe['From Date'] = pd.to_datetime(df_pe['From Date'], errors='coerce').dt.date
                                    df_pe['To Date'] = pd.to_datetime(df_pe['To Date'], errors='coerce').dt.date
                                    
                                    edited_pe = st.data_editor(
                                        df_pe, 
                                        num_rows="dynamic", 
                                        column_config={
                                            "Company Name": st.column_config.TextColumn(),
                                            "City": st.column_config.TextColumn(),
                                            "From Date": st.column_config.DateColumn(),
                                            "To Date": st.column_config.DateColumn()
                                        },
                                        key=f"my_pe_{selected_member_id}", 
                                        use_container_width=True
                                    )
                                    new_prof_data[field] = edited_pe.to_dict('records')
                                    
                                else:
                                    current_val = prof_data.get(field, "")
                                    temp_val = st.text_input(field, value=current_val, key=f"my_cf_{field}_{selected_member_id}")
                                    new_prof_data[field] = (temp_val or "").strip()
                                
                            if st.form_submit_button("Submit Update Request", type="primary"):
                                final_prof_data = sanitize_and_calculate_profile(new_prof_data)
                                
                                try:
                                    supabase.table("team_members").update({"pending_profile_data": final_prof_data}).eq("id", selected_member_id).execute()
                                    st.success("Profile update submitted. Pending Admin approval.")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed to submit profile update: {e}")

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
            st.write("Manage global application configurations and your team directory.")
            
            adm_tab1, adm_tab2, adm_tab3, adm_tab4 = st.tabs(["Global Configurations", "Team Directory", "Master Project Control", "Task SOPs"])
            
            # --- TAB 1: GLOBAL CONFIGURATIONS ---
            with adm_tab1:
                col1, col2, col3 = st.columns(3)
                with col1:
                    with st.form("activity_settings_form"):
                        st.write("Activity Types")
                        active_activities = st.multiselect("Current Types", options=global_activity_types, default=global_activity_types)
                        new_activity = st.text_input("Add New Type")
                        
                        if st.form_submit_button("Save Activities", type="primary"):
                            final_activities = active_activities.copy()
                            if (new_activity or "").strip() and (new_activity or "").strip() not in final_activities:
                                final_activities.append((new_activity or "").strip())
                            try:
                                supabase.table("aos_settings").update({"options": final_activities}).eq("category", "activity_types").execute()
                                st.success("Updated")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                                
                with col2:
                    with st.form("tags_settings_form"):
                        st.write("Timesheet Tags")
                        active_tags = st.multiselect("Current Tags", options=global_tags, default=global_tags)
                        new_tag = st.text_input("Add New Tag")
                        
                        if st.form_submit_button("Save Tags", type="primary"):
                            final_tags = active_tags.copy()
                            if (new_tag or "").strip() and (new_tag or "").strip() not in final_tags:
                                final_tags.append((new_tag or "").strip())
                            try:
                                supabase.table("aos_settings").update({"options": final_tags}).eq("category", "tags").execute()
                                st.success("Updated")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                                
                with col3:
                    with st.form("designation_settings_form"):
                        st.write("Company Designations")
                        active_designations = st.multiselect("Current Designations", options=global_designations, default=global_designations)
                        new_designation = st.text_input("Add New Designation")
                        
                        if st.form_submit_button("Save Designations", type="primary"):
                            final_designations = active_designations.copy()
                            if (new_designation or "").strip() and (new_designation or "").strip() not in final_designations:
                                final_designations.append((new_designation or "").strip())
                            try:
                                supabase.table("aos_settings").upsert({"category": "designations", "options": final_designations}).execute()
                                st.success("Updated")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                                
                col4, col5, col6 = st.columns(3)
                with col4:
                    with st.form("custom_fields_settings_form"):
                        st.write("Custom Profile Fields")
                        active_fields = st.multiselect("Current Fields", options=global_custom_fields, default=global_custom_fields)
                        new_field = st.text_input("Add New Field")
                        
                        if st.form_submit_button("Save Fields", type="primary"):
                            final_fields = active_fields.copy()
                            if (new_field or "").strip() and (new_field or "").strip() not in final_fields:
                                final_fields.append((new_field or "").strip())
                            try:
                                supabase.table("aos_settings").upsert({"category": "custom_profile_fields", "options": final_fields}).execute()
                                st.success("Updated")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                
                with col5:
                    with st.form("project_category_settings_form"):
                        st.write("Project Categories")
                        active_p_cats = st.multiselect("Current Categories", options=global_project_categories, default=global_project_categories)
                        new_p_cat = st.text_input("Add New Category")
                        
                        if st.form_submit_button("Save Categories", type="primary"):
                            final_p_cats = active_p_cats.copy()
                            if (new_p_cat or "").strip() and (new_p_cat or "").strip() not in final_p_cats:
                                final_p_cats.append((new_p_cat or "").strip())
                            try:
                                supabase.table("aos_settings").upsert({"category": "project_categories", "options": final_p_cats}).execute()
                                st.success("Updated")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")

                with col6:
                    with st.form("project_sub_category_settings_form"):
                        st.write("Project Sub-Categories")
                        active_p_subcats = st.multiselect("Current Sub-Categories", options=global_project_sub_categories, default=global_project_sub_categories)
                        new_p_subcat = st.text_input("Add New Sub-Category")
                        
                        if st.form_submit_button("Save Sub-Categories", type="primary"):
                            final_p_subcats = active_p_subcats.copy()
                            if (new_p_subcat or "").strip() and (new_p_subcat or "").strip() not in final_p_subcats:
                                final_p_subcats.append((new_p_subcat or "").strip())
                            try:
                                supabase.table("aos_settings").upsert({"category": "project_sub_categories", "options": final_p_subcats}).execute()
                                st.success("Updated")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")

            # --- TAB 2: TEAM DIRECTORY (HCM) ---
            with adm_tab2:
                if st.session_state.admin_emp_id:
                    # STATE 2: EMPLOYEE HUB DRILL-DOWN WITH TOTAL EDIT CONTROL
                    if st.button("Back to Roster"):
                        st.session_state.admin_emp_id = None
                        st.session_state.roster_key += 1
                        st.rerun()
                    
                    emp_target_id = st.session_state.admin_emp_id
                    emp_record = next((e for e in team_data if e['id'] == emp_target_id), None)
                    
                    if emp_record:
                        st.title(f"Employee Hub: {emp_record['full_name']}")
                        st.divider()
                        
                        active_proj_count = 0
                        if projects_data_global:
                            active_proj_count = len([p for p in projects_data_global if p.get('team_lead') == emp_target_id and p.get('status') == 'Active'])
                            
                        metric_col1, metric_col2, metric_col3 = st.columns(3)
                        metric_col1.metric("Designation", emp_record.get('role', 'N/A'))
                        metric_col2.metric("Code Name", emp_record.get('code_name', 'N/A'))
                        metric_col3.metric("Active Projects Assigned", active_proj_count)
                        
                        st.divider()
                        st.subheader("Manage Employee Data")
                        
                        prof_data = emp_record.get('profile_data') or {}
                        
                        with st.form("admin_total_edit_form"):
                            st.write("Core Identification")
                            c_core1, c_core2, c_core3 = st.columns(3)
                            upd_first = c_core1.text_input("First Name", value=emp_record.get('first_name', ''))
                            upd_father = c_core2.text_input("Father's Name", value=emp_record.get('father_name', ''))
                            upd_last = c_core3.text_input("Last Name", value=emp_record.get('last_name', ''))
                            
                            c_core4, c_core5, c_core6 = st.columns(3)
                            upd_email = c_core4.text_input("Email", value=emp_record.get('email', ''))
                            upd_phone = c_core5.text_input("Phone", value=emp_record.get('phone', ''))
                            
                            try:
                                j_date_val = datetime.strptime(emp_record.get('join_date', ''), "%Y-%m-%d").date()
                            except:
                                j_date_val = datetime.today().date()
                            upd_join = c_core6.date_input("Join Date", value=j_date_val)
                            
                            c_core7, c_core8 = st.columns(2)
                            current_r = emp_record.get('role')
                            upd_role = c_core7.selectbox("Designation", options=global_designations, index=global_designations.index(current_r) if current_r in global_designations else 0)
                            
                            current_s = emp_record.get('status', 'Active')
                            status_opts = ['Active', 'Inactive', 'On Leave']
                            upd_status = c_core8.selectbox("Status", options=status_opts, index=status_opts.index(current_s) if current_s in status_opts else 0)
                            
                            st.divider()
                            st.write("Dynamic Profile Data")
                            new_prof_data = {}
                            if global_custom_fields:
                                for field in global_custom_fields:
                                    if field == 'Total Experience':
                                        continue
                                        
                                    if field == 'Emergency Contact':
                                        st.write(f"**{field}**")
                                        ec_data = prof_data.get(field, {})
                                        if not isinstance(ec_data, dict): ec_data = {}
                                        ec1, ec2, ec3 = st.columns(3)
                                        ec_name = ec1.text_input("Name", value=ec_data.get('Name', ''), key=f"adm_ec_n_{emp_target_id}")
                                        ec_rel = ec2.text_input("Relationship", value=ec_data.get('Relationship', ''), key=f"adm_ec_r_{emp_target_id}")
                                        ec_num = ec3.text_input("Contact Number", value=ec_data.get('Contact Number', ''), key=f"adm_ec_c_{emp_target_id}")
                                        new_prof_data[field] = {"Name": (ec_name or "").strip(), "Relationship": (ec_rel or "").strip(), "Contact Number": (ec_num or "").strip()}
                                        
                                    elif field == 'Educational Background':
                                        st.write(f"**{field}**")
                                        ed_data = prof_data.get(field, [])
                                        if not isinstance(ed_data, list): ed_data = []
                                        df_ed = pd.DataFrame(ed_data, columns=['Degree', 'College/University', 'Passing Year'])
                                        df_ed['Passing Year'] = pd.to_numeric(df_ed['Passing Year'], errors='coerce')
                                        
                                        edited_ed = st.data_editor(
                                            df_ed, 
                                            num_rows="dynamic", 
                                            column_config={"Passing Year": st.column_config.NumberColumn(format="%d")},
                                            key=f"adm_ed_{emp_target_id}", 
                                            use_container_width=True
                                        )
                                        new_prof_data[field] = edited_ed.to_dict('records')
                                        
                                    elif field == 'Past Employment':
                                        st.write(f"**{field}**")
                                        pe_data = prof_data.get(field, [])
                                        if not isinstance(pe_data, list): pe_data = []
                                        df_pe = pd.DataFrame(pe_data, columns=['Company Name', 'City', 'From Date', 'To Date'])
                                        df_pe['From Date'] = pd.to_datetime(df_pe['From Date'], errors='coerce').dt.date
                                        df_pe['To Date'] = pd.to_datetime(df_pe['To Date'], errors='coerce').dt.date
                                        
                                        edited_pe = st.data_editor(
                                            df_pe, 
                                            num_rows="dynamic", 
                                            column_config={
                                                "Company Name": st.column_config.TextColumn(),
                                                "City": st.column_config.TextColumn(),
                                                "From Date": st.column_config.DateColumn(),
                                                "To Date": st.column_config.DateColumn()
                                            },
                                            key=f"adm_pe_{emp_target_id}", 
                                            use_container_width=True
                                        )
                                        new_prof_data[field] = edited_pe.to_dict('records')
                                        
                                    else:
                                        current_val = prof_data.get(field, "")
                                        temp_val = st.text_input(field, value=current_val, key=f"adm_cf_{field}_{emp_target_id}")
                                        new_prof_data[field] = (temp_val or "").strip()
                            else:
                                st.write("No custom fields configured.")
                                
                            st.divider()
                            col_btn1, col_btn2 = st.columns(2)
                            with col_btn1:
                                submit_hub = st.form_submit_button("Force Save All Changes", type="primary", use_container_width=True)
                            with col_btn2:
                                submit_del = st.form_submit_button("Delete Employee Record", use_container_width=True)
                                
                            if submit_hub:
                                final_prof_data = sanitize_and_calculate_profile(new_prof_data)
                                
                                upd_full_name = f"{(upd_first or '').strip()} {(upd_last or '').strip()}".strip()
                                existing_codes = [m.get('code_name') for m in team_data if m.get('code_name') and m.get('id') != emp_target_id]
                                upd_code = generate_code_name((upd_first or "").strip(), (upd_father or "").strip(), (upd_last or "").strip(), existing_codes)
                                
                                payload = {
                                    "first_name": (upd_first or "").strip(),
                                    "father_name": (upd_father or "").strip(),
                                    "last_name": (upd_last or "").strip(),
                                    "full_name": upd_full_name,
                                    "code_name": upd_code,
                                    "email": (upd_email or "").strip(),
                                    "phone": (upd_phone or "").strip(),
                                    "join_date": upd_join.isoformat() if upd_join else None,
                                    "role": upd_role,
                                    "status": upd_status,
                                    "profile_data": final_prof_data
                                }
                                try:
                                    supabase.table("team_members").update(payload).eq("id", emp_target_id).execute()
                                    st.success("Employee record completely updated.")
                                    st.session_state.admin_emp_id = None
                                    st.session_state.roster_key += 1
                                    time.sleep(0.5)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed to update employee: {e}")
                                    
                            if submit_del:
                                try:
                                    supabase.table("team_members").delete().eq("id", emp_target_id).execute()
                                    st.success("Employee record deleted.")
                                    st.session_state.admin_emp_id = None
                                    st.session_state.roster_key += 1
                                    time.sleep(0.5)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed to delete employee: {e}")
                    else:
                        st.error("Employee record not found.")

                else:
                    # STATE 1: MASTER ROSTER & HR INBOX
                    
                    # --- HR APPROVALS INBOX ---
                    pending_approvals = [m for m in team_data if m.get('pending_profile_data')]
                    if pending_approvals:
                        st.subheader("HR Approvals Inbox")
                        for emp in pending_approvals:
                            with st.expander(f"Pending Profile Update: {emp['full_name']}", expanded=True):
                                st.write("Requested Changes")
                                current_data = emp.get('profile_data', {})
                                pending_data = emp.get('pending_profile_data', {})
                                
                                for field in global_custom_fields:
                                    c_val = current_data.get(field, 'Empty')
                                    p_val = pending_data.get(field, 'Empty')
                                    if str(c_val) != str(p_val):
                                        st.markdown(f"- **{field}**: `{c_val}` -> `{p_val}`")
                                
                                c1, c2 = st.columns(2)
                                with c1:
                                    if st.button("Approve Changes", key=f"appr_{emp['id']}", type="primary"):
                                        try:
                                            supabase.table("team_members").update({
                                                "profile_data": pending_data,
                                                "pending_profile_data": None
                                            }).eq("id", emp['id']).execute()
                                            st.success("Changes approved.")
                                            time.sleep(0.5)
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Error: {e}")
                                with c2:
                                    if st.button("Reject", key=f"rej_{emp['id']}"):
                                        try:
                                            supabase.table("team_members").update({
                                                "pending_profile_data": None
                                            }).eq("id", emp['id']).execute()
                                            st.success("Request rejected.")
                                            time.sleep(0.5)
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Error: {e}")
                        st.divider()

                    st.subheader("Executive Headcount Dashboard")
                    df_team = pd.DataFrame(team_data)
                    
                    for col in ['status', 'email', 'phone', 'join_date']:
                        if col not in df_team.columns:
                            df_team[col] = None
                    df_team['status'] = df_team['status'].fillna('Active')
                    
                    total_headcount = len(df_team)
                    active_employees = len(df_team[df_team['status'] == 'Active'])
                    on_leave_inactive = len(df_team[df_team['status'].isin(['Inactive', 'On Leave'])])
                    total_designations = df_team['role'].nunique()
                    
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Total Headcount", total_headcount)
                    m2.metric("Active Employees", active_employees)
                    m3.metric("Total Designations", total_designations)
                    m4.metric("On Leave / Inactive", on_leave_inactive)
                    
                    st.divider()
                    st.subheader("Firm Roster & Resource Allocation")
                    
                    try:
                        proj_response = supabase.table('projects').select('team_lead, status').execute()
                        projects_data_for_roster = proj_response.data
                    except Exception as e:
                        projects_data_for_roster = []

                    df_proj = pd.DataFrame(projects_data_for_roster) if projects_data_for_roster else pd.DataFrame(columns=['team_lead', 'status'])

                    if not df_proj.empty and 'team_lead' in df_proj.columns and 'status' in df_proj.columns:
                        active_projs = df_proj[df_proj['status'] == 'Active']
                        proj_counts = active_projs.groupby('team_lead').size().reset_index(name='Active Projects Assigned')
                    else:
                        proj_counts = pd.DataFrame(columns=['team_lead', 'Active Projects Assigned'])
                        
                    df_roster = pd.merge(df_team, proj_counts, left_on='id', right_on='team_lead', how='left')
                    df_roster['Active Projects Assigned'] = df_roster['Active Projects Assigned'].fillna(0).astype(int)
                    
                    roster_display_cols = {
                        'id': 'ID',
                        'full_name': 'Name',
                        'code_name': 'Code',
                        'role': 'Designation',
                        'status': 'Status',
                        'email': 'Email',
                        'phone': 'Phone',
                        'join_date': 'Join Date',
                        'Active Projects Assigned': 'Active Projects Assigned'
                    }
                    
                    df_roster_ui = df_roster[list(roster_display_cols.keys())].rename(columns=roster_display_cols)
                    
                    current_roster_key = f"roster_grid_{st.session_state.roster_key}"
                    
                    st.dataframe(
                        df_roster_ui.drop(columns=['ID']), 
                        use_container_width=True, 
                        hide_index=True,
                        selection_mode="single-row",
                        on_select="rerun",
                        key=current_roster_key
                    )
                    
                    if current_roster_key in st.session_state and len(st.session_state[current_roster_key]['selection']['rows']) > 0:
                        selected_idx = st.session_state[current_roster_key]['selection']['rows'][0]
                        st.session_state.admin_emp_id = df_roster_ui.iloc[selected_idx]['ID']
                        st.rerun()
                    
                    st.divider()
                    st.subheader("Onboard New Employee")
                    with st.form("onboard_form", clear_on_submit=True):
                        new_first = st.text_input("First Name")
                        new_father = st.text_input("Father's Name")
                        new_last = st.text_input("Last Name")
                        
                        new_email = st.text_input("Email")
                        new_phone = st.text_input("Phone")
                        new_join = st.date_input("Join Date", value=None)
                        new_role = st.selectbox("Designation", options=global_designations)
                        
                        if st.form_submit_button("Onboard Employee", type="primary"):
                            if not (new_first or "").strip() or not (new_last or "").strip():
                                st.error("First and Last name are required.")
                            else:
                                existing_codes = [m.get('code_name') for m in team_data if m.get('code_name')]
                                final_code = generate_code_name((new_first or "").strip(), (new_father or "").strip(), (new_last or "").strip(), existing_codes)
                                    
                                combined_name = f"{(new_first or '').strip()} {(new_last or '').strip()}"
                                
                                payload = {
                                    "first_name": (new_first or "").strip(),
                                    "father_name": (new_father or "").strip(),
                                    "last_name": (new_last or "").strip(),
                                    "full_name": combined_name,
                                    "code_name": final_code,
                                    "email": (new_email or "").strip(),
                                    "phone": (new_phone or "").strip(),
                                    "join_date": new_join.isoformat() if new_join else None,
                                    "role": new_role,
                                    "status": "Active",
                                    "profile_data": {}
                                }
                                try:
                                    supabase.table("team_members").insert(payload).execute()
                                    st.success(f"Employee {combined_name} onboarded with code {final_code}.")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")

            # --- TAB 3: MASTER PROJECT CONTROL ---
            with adm_tab3:
                try:
                    projects_response = supabase.table("projects").select("*").execute()
                    projects_data = projects_response.data
                except Exception as e:
                    st.error(f"Error loading projects: {e}")
                    projects_data = []

                st.subheader("Create New Project")
                with st.form("create_project_form", clear_on_submit=True):
                    st.write("Core Identity")
                    c1, c2 = st.columns(2)
                    p_code = c1.text_input("Project Code")
                    p_name = c2.text_input("Project Name")
                    
                    c3, c4, c5 = st.columns(3)
                    p_client = c3.text_input("Client Name")
                    p_lead = c4.selectbox("Assign Team Lead", options=list(name_to_id_map.keys()))
                    p_arch = c5.text_input("Architect")

                    st.write("Typology & Scale")
                    t1, t2, t3 = st.columns(3)
                    
                    if global_project_categories:
                        p_cat = t1.selectbox("Category", options=global_project_categories)
                    else:
                        p_cat = t1.text_input("Category")
                        
                    if global_project_sub_categories:
                        p_subcat = t2.selectbox("Sub-Category", options=global_project_sub_categories)
                    else:
                        p_subcat = t2.text_input("Sub-Category")
                        
                    p_scale = t3.text_input("Scale")
                    p_scope = st.text_area("Scope")

                    st.write("Geography")
                    g1, g2 = st.columns(2)
                    p_city = g1.text_input("City")
                    p_map = g2.text_input("Map Location")
                    p_address = st.text_area("Address")

                    st.write("Timeline")
                    d1, d2, d3 = st.columns(3)
                    p_1st_date = d1.date_input("Project 1st Date", value=None)
                    p_start_date = d2.date_input("Start Date", value=None)
                    p_comp_date = d3.date_input("Target Completion Date", value=None)
                    
                    if st.form_submit_button("Create Project", type="primary", use_container_width=True):
                        if not (p_code or "").strip() or not (p_name or "").strip():
                            st.error("Project Code and Name are required.")
                        else:
                            new_project_payload = {
                                "project_code": (p_code or "").strip(),
                                "project_name": (p_name or "").strip(),
                                "client_name": (p_client or "").strip(),
                                "team_lead": name_to_id_map.get(p_lead),
                                "architect": (p_arch or "").strip(),
                                "category": (p_cat or "").strip(),
                                "sub_category": (p_subcat or "").strip(),
                                "scale": (p_scale or "").strip(),
                                "scope": (p_scope or "").strip(),
                                "city": (p_city or "").strip(),
                                "map_location": (p_map or "").strip(),
                                "address": (p_address or "").strip(),
                                "project_1st_date": p_1st_date.isoformat() if p_1st_date else None,
                                "start_date": p_start_date.isoformat() if p_start_date else None,
                                "completion_date": p_comp_date.isoformat() if p_comp_date else None,
                                "status": "Active",
                                "current_stage": "Proposal",
                                "tracking_status": "On Track"
                            }
                            try:
                                supabase.table("projects").insert(new_project_payload).execute()
                                st.success(f"Project {(p_code or '').strip()} created successfully.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to create project: {e}")

                st.divider()
                st.subheader("Manage Existing Projects")
                if projects_data:
                    proj_update_options = {f"{p['project_code']} ({p.get('project_name', 'Unknown')})": p['project_code'] for p in projects_data}
                    
                    sel_col1, sel_col2 = st.columns([3, 1])
                    with sel_col1:
                        selected_proj_to_update = st.selectbox("Select Active Project", options=list(proj_update_options.keys()), label_visibility="collapsed")
                    with sel_col2:
                        if st.button("View Hub", use_container_width=True):
                            st.session_state.selected_project_code = proj_update_options[selected_proj_to_update]
                            st.rerun()
                    
                    actual_proj_code = proj_update_options[selected_proj_to_update]
                    selected_project_data = next((p for p in projects_data if p['project_code'] == actual_proj_code), {})
                    
                    current_lead_id = selected_project_data.get('team_lead')
                    current_lead_name = id_to_name_map.get(current_lead_id, list(name_to_id_map.keys())[0]) if current_lead_id else list(name_to_id_map.keys())[0]
                    current_stage_val = selected_project_data.get('current_stage')
                    current_status_val = selected_project_data.get('status', 'Active')
                    
                    stage_options = ["Proposal", "Working", "Services", "Detailing", "Execution", "Plantation", "Design Revision", "Finishing"]
                    main_status_options = ["Active", "On Hold", "Completed"]
                    
                    lead_idx = list(name_to_id_map.keys()).index(current_lead_name) if current_lead_name in name_to_id_map else 0
                    stage_idx = stage_options.index(current_stage_val) if current_stage_val in stage_options else 0
                    main_idx = main_status_options.index(current_status_val) if current_status_val in main_status_options else 0
                    
                    with st.form("admin_manage_project_form"):
                        st.write("Core Identity")
                        u_c1, u_c2 = st.columns(2)
                        u_code = u_c1.text_input("Project Code", value=selected_project_data.get('project_code', ''), disabled=True)
                        u_name = u_c2.text_input("Project Name", value=selected_project_data.get('project_name', ''))
                        
                        u_c3, u_c4, u_c5 = st.columns(3)
                        u_client = u_c3.text_input("Client Name", value=selected_project_data.get('client_name', ''))
                        u_lead = u_c4.selectbox("Reassign Team Lead", options=list(name_to_id_map.keys()), index=lead_idx)
                        u_arch = u_c5.text_input("Architect", value=selected_project_data.get('architect', ''))

                        st.write("Typology & Scale")
                        u_t1, u_t2, u_t3 = st.columns(3)
                        
                        c_cat = selected_project_data.get('category', '')
                        cat_opts = list(global_project_categories)
                        if c_cat and c_cat not in cat_opts: cat_opts.append(c_cat)
                        
                        c_subcat = selected_project_data.get('sub_category', '')
                        subcat_opts = list(global_project_sub_categories)
                        if c_subcat and c_subcat not in subcat_opts: subcat_opts.append(c_subcat)
                        
                        if cat_opts:
                            u_cat = u_t1.selectbox("Category", options=cat_opts, index=cat_opts.index(c_cat) if c_cat in cat_opts else 0)
                        else:
                            u_cat = u_t1.text_input("Category", value=c_cat)
                            
                        if subcat_opts:
                            u_subcat = u_t2.selectbox("Sub-Category", options=subcat_opts, index=subcat_opts.index(c_subcat) if c_subcat in subcat_opts else 0)
                        else:
                            u_subcat = u_t2.text_input("Sub-Category", value=c_subcat)
                            
                        u_scale = u_t3.text_input("Scale", value=selected_project_data.get('scale', ''))
                        u_scope = st.text_area("Scope", value=selected_project_data.get('scope', ''))

                        st.write("Geography")
                        u_g1, u_g2 = st.columns(2)
                        u_city = u_g1.text_input("City", value=selected_project_data.get('city', ''))
                        u_map = u_g2.text_input("Map Location", value=selected_project_data.get('map_location', ''))
                        u_address = st.text_area("Address", value=selected_project_data.get('address', ''))

                        st.write("Timeline & Status")
                        u_d1, u_d2, u_d3 = st.columns(3)
                        
                        def parse_date_safe(date_str):
                            if date_str:
                                try: return datetime.strptime(date_str, "%Y-%m-%d").date()
                                except: return None
                            return None
                            
                        u_1st_date = u_d1.date_input("Project 1st Date", value=parse_date_safe(selected_project_data.get('project_1st_date')))
                        u_start_date = u_d2.date_input("Start Date", value=parse_date_safe(selected_project_data.get('start_date')))
                        u_comp_date = u_d3.date_input("Target Completion Date", value=parse_date_safe(selected_project_data.get('completion_date')))
                        
                        u_s1, u_s2 = st.columns(2)
                        u_stage = u_s1.selectbox("Current Stage", options=stage_options, index=stage_idx)
                        u_status = u_s2.selectbox("Main Project Status", options=main_status_options, index=main_idx)
                        
                        if st.form_submit_button("Save Project Updates", type="primary", use_container_width=True):
                            update_payload = {
                                "project_name": (u_name or "").strip(),
                                "client_name": (u_client or "").strip(),
                                "team_lead": name_to_id_map.get(u_lead),
                                "architect": (u_arch or "").strip(),
                                "category": (u_cat or "").strip(),
                                "sub_category": (u_subcat or "").strip(),
                                "scale": (u_scale or "").strip(),
                                "scope": (u_scope or "").strip(),
                                "city": (u_city or "").strip(),
                                "map_location": (u_map or "").strip(),
                                "address": (u_address or "").strip(),
                                "project_1st_date": u_1st_date.isoformat() if u_1st_date else None,
                                "start_date": u_start_date.isoformat() if u_start_date else None,
                                "completion_date": u_comp_date.isoformat() if u_comp_date else None,
                                "current_stage": u_stage,
                                "status": u_status
                            }
                            try:
                                supabase.table("projects").update(update_payload).eq("project_code", actual_proj_code).execute()
                                st.success(f"Project {actual_proj_code} updated successfully.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to update project: {e}")
                else:
                    st.write("No projects available to manage.")
                    
            # --- TAB 4: TASK SOPs ---
            with adm_tab4:
                st.subheader("Manage Task Categories")
                with st.form("add_category_form"):
                    new_category = st.text_input("New Category Name")
                    if st.form_submit_button("Add Category", type="primary"):
                        if (new_category or "").strip() and (new_category or "").strip() not in taxonomy_map:
                            try:
                                supabase.table("task_taxonomy").insert({"category": (new_category or "").strip(), "deliverables": []}).execute()
                                st.success("Category added.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to add category: {e}")
                                
                st.divider()
                st.subheader("Manage Deliverables")
                if taxonomy_map:
                    selected_cat = st.selectbox("Select Category", options=list(taxonomy_map.keys()))
                    current_deliverables = taxonomy_map[selected_cat]
                    
                    with st.form("manage_deliverables_form"):
                        active_delivs = st.multiselect("Current Deliverables", options=current_deliverables, default=current_deliverables)
                        new_deliv = st.text_input("Add New Deliverable")
                        
                        if st.form_submit_button("Save Deliverables", type="primary"):
                            final_delivs = active_delivs.copy()
                            if (new_deliv or "").strip() and (new_deliv or "").strip() not in final_delivs:
                                final_delivs.append((new_deliv or "").strip())
                                
                            try:
                                supabase.table("task_taxonomy").update({"deliverables": final_delivs}).eq("category", selected_cat).execute()
                                st.success("Deliverables updated.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to update deliverables: {e}")
                else:
                    st.write("No task categories exist yet.")