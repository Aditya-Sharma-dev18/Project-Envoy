import streamlit as st
import psycopg2
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

st.set_page_config(page_title="Envoy Admin | HITL Review", layout="wide")
st.title("🏛️ Project Envoy - Human Review Queue")

# Initialize database connection
@st.cache_resource
def init_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

conn = init_connection()

def fetch_flagged_records():
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, first_name, last_name, raw_reply_text, 
                   current_company, current_designation, current_location
            FROM alumni 
            WHERE verification_status = 'NEEDS_HUMAN_REVIEW'
        """)
        return cur.fetchall()

def update_record(record_id, company, designation, location):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE alumni
            SET current_company = %s,
                current_designation = %s,
                current_location = %s,
                verification_status = 'COMPLETED',
                last_verified_at = NOW()
            WHERE id = %s
        """, (company, designation, location, record_id))
    conn.commit()

# Main UI
flagged_records = fetch_flagged_records()

if not flagged_records:
    st.success("🎉 Queue is empty! All alumni records are confidently parsed and updated.")
else:
    st.warning(f"Found {len(flagged_records)} records requiring human review due to low AI confidence or ambiguous replies.")
    
    for record in flagged_records:
        rec_id, fname, lname, raw_text, parsed_company, parsed_desig, parsed_loc = record
        
        with st.expander(f"Review: {fname} {lname}"):
            st.markdown(f"**Alumni's Raw Reply:**\n> *{raw_text}*")
            
            st.caption("Edit the extracted fields below based on the message above, then approve.")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                new_company = st.text_input("Company", value=parsed_company or "", key=f"comp_{rec_id}")
            with col2:
                new_desig = st.text_input("Designation", value=parsed_desig or "", key=f"desig_{rec_id}")
            with col3:
                new_loc = st.text_input("Location", value=parsed_loc or "", key=f"loc_{rec_id}")
                
            if st.button("Approve & Sync to DB", key=f"btn_{rec_id}", type="primary"):
                update_record(rec_id, new_company, new_desig, new_loc)
                st.success("Record updated successfully!")
                st.rerun()