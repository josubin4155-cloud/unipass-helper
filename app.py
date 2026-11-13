import os
os.system("playwright install chromium")
import streamlit as st
import streamlit as st

# --- 비밀번호 확인 기능 시작 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔒 팀 전용 B/L 조회 시스템")
        pwd = st.text_input("접속 비밀번호를 입력하세요", type="password")
        if st.button("확인"):
            if pwd == st.secrets["APP_PASSWORD"]:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
        st.stop()

check_password()
# --- 비밀번호 확인 기능 끝 ---
import pandas as pd
from playwright.sync_api import sync_playwright
import os
import re

st.set_page_config(page_title="포워딩 B/L & 양하조회 도우미", page_icon="🚢", layout="wide")

def load_contacts():
    if os.path.exists("contacts.csv"):
        try:
            return pd.read_csv("contacts.csv", encoding="utf-8-sig")
        except:
            return pd.read_csv("contacts.csv", encoding="cp949")
    return pd.DataFrame(columns=["키워드", "구분", "업체명", "홈페이지", "전화번호"])

def search_unipass(bl_no, bl_type):
    result = {
        "success": False,
        "error": "",
        "carrier": "확인 불가",
        "agency": "확인 불가",
        "terminal": "확인 불가",
        "containers": [],
        "screenshot_path": "unipass_result.png",
        "raw_text": ""
    }

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    )
    context = browser.new_context(viewport={"width": 1280, "height": 1000})
    page = context.new_page()
    try:
        page.goto("https://unipass.customs.go.kr/csp/index.do", timeout=30000)
        page.wait_for_timeout(1500)
    except Exception as e:
        st.error(f"브라우저 실행 중 오류 발생: {e}")
            
try:
        page.goto("https://unipass.customs.go.kr/csp/index.do", timeout=30000)
        page.wait_for_timeout(1500)

        if bl_type == "M B/L":
            page.locator("input[name='mblNo'], #mblNo, input[title*='M B/L']").first.fill(bl_no)
        else:
            page.locator("input[name='hblNo'], #hblNo, input[title*='H B/L']").first.fill(bl_no)

        page.keyboard.press("Enter")
        page.wait_for_timeout(3500)
except Exception as e:
            st.error(f"브라우저 실행 중 오류 발생: {e}")
            page.wait_for_timeout(3500)
            
            page.screenshot(path=result["screenshot_path"], full_page=True)
            body_text = page.inner_text("body")
            result["raw_text"] = body_text
            
            if "조회된 내역이 없습니다" in body_text or "존재하지 않습니다" in body_text:
                result["error"] = "유니패스에서 해당 B/L 번호의 화물 진행 정보를 찾을 수 없습니다."
                browser.close()
                return result

            rows = page.locator("table tr").all()
            for row in rows:
                cells = [c.inner_text().strip() for c in row.locator("th, td").all()]
                for i, cell in enumerate(cells):
                    if "선사/항공사" in cell and i + 1 < len(cells):
                        result["carrier"] = cells[i + 1]
                    elif "선박대리점" in cell and i + 1 < len(cells):
                        result["agency"] = cells[i + 1]
                    elif ("장치장" in cell or "반입장소" in cell) and i + 1 < len(cells):
                        if cells[i + 1] and result["terminal"] == "확인 불가":
                            result["terminal"] = cells[i + 1]

            cntr_matches = re.findall(r'\b[A-Z]{4}\d{7}\b', body_text)
            result["containers"] = list(dict.fromkeys(cntr_matches))
            result["success"] = True
            

except Exception as e:
        result["error"] = f"조회 중 오류가 발생했습니다: {e}"
        
finally:
        browser.close()
        
return result

st.title("🚢 포워딩 B/L & 양하조회 자동화 대시보드")
st.markdown("B/L 번호를 입력하면 유니패스를 자동 조회하여 선사/대리점/터미널 연락처와 컨테이너 번호를 보여줍니다.")

with st.sidebar:
    st.header("📋 등록된 선사/터미널 DB")
    contacts_df = load_contacts()
    st.dataframe(contacts_df[["구분", "업체명", "전화번호"]], hide_index=True)
    st.info("💡 `contacts.csv` 파일을 수정하면 선사 정보를 언제든 추가할 수 있습니다.")

col_type, col_input, col_btn = st.columns([1.2, 3, 1])
with col_type:
    bl_type = st.selectbox("B/L 구분", ["H B/L", "M B/L"])
with col_input:
    bl_no = st.text_input("B/L 번호 입력", placeholder="예: HDMU1234567").strip().upper()
with col_btn:
    st.write("")
    st.write("")
    search_clicked = st.button("🔍 유니패스 조회", type="primary", use_container_width=True)

st.divider()

if search_clicked:
    if not bl_no:
        st.warning("B/L 번호를 입력해 주세요!")
    else:
        with st.spinner(f"유니패스에서 [{bl_no}] 화물 정보를 조회 중입니다..."):
            data = search_unipass(bl_no, bl_type)
            
        if not data["success"]:
            st.error(data["error"])
            if os.path.exists(data["screenshot_path"]):
                st.image(data["screenshot_path"], caption="유니패스 조회 화면 캡처")
        else:
            st.success(f"✅ [{bl_no}] 조회가 완료되었습니다!")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("선사 / 항공사", data["carrier"])
            with c2:
                st.metric("선박대리점", data["agency"])
            with c3:
                st.metric("장치장 (터미널)", data["terminal"])
                
            st.markdown("---")
            
            left_col, right_col = st.columns([1.2, 1])
            
            with left_col:
                st.subheader("📞 매칭된 선사 및 터미널 연락처")
                search_target_text = f"{data['carrier']} {data['agency']} {data['terminal']} {data['raw_text']}"
                matched_rows = []
                seen_companies = set()
                
                for _, row in contacts_df.iterrows():
                    keyword = str(row["키워드"]).strip()
                    company = str(row["업체명"]).strip()
                    if keyword and keyword in search_target_text and company not in seen_companies:
                        matched_rows.append(row)
                        seen_companies.add(company)
                
                if matched_rows:
                    for item in matched_rows:
                        with st.container(border=True):
                            st.markdown(f"**[{item['구분']}] {item['업체명']}**")
                            st.write(f"☎️ **전화번호:** `{item['전화번호']}`")
                            if pd.notna(item['홈페이지']) and str(item['홈페이지']).startswith("http"):
                                st.link_button(f"🌐 {item['업체명']} 홈페이지 바로가기", item['홈페이지'])
                else:
                    st.info("등록된 선사/터미널 DB와 일치하는 업체가 없습니다.")

            with right_col:
                st.subheader("📦 컨테이너 번호 (클릭하여 복사)")
                if data["containers"]:
                    for cntr in data["containers"]:
                        st.code(cntr, language=None)
                else:
                    st.warning("표준 컨테이너 번호를 찾지 못했습니다.")
            
            st.markdown("---")
            st.subheader("📸 유니패스 조회 결과 캡처")
            if os.path.exists(data["screenshot_path"]):
                st.image(data["screenshot_path"], use_container_width=True)
