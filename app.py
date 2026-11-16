import os
os.system("playwright install chromium")
import streamlit as st
import pandas as pd
from playwright.sync_api import sync_playwright
import re

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

st.set_page_config(page_title="포워딩 B/L & 양하조회 도우미", page_icon="🚢", layout="wide")

def load_contacts():
    if os.path.exists("contacts.csv"):
        try:
            df = pd.read_csv("contacts.csv", encoding="utf-8-sig")
        except:
            df = pd.read_csv("contacts.csv", encoding="cp949")
        
        if "업체명" in df.columns:
            df = df.drop_duplicates(subset=["업체명"]).reset_index(drop=True)
            
        return df
    return pd.DataFrame(columns=["키워드", "구분", "업체명", "홈페이지", "전화번호"])

def search_unipass(bl_no, bl_type):
    result = {
        "success": False,
        "error": "",
        "carrier": "확인 불가",
        "agency": "확인 불가",
        "terminal": "확인 불가",
        "containers": [],
        "screenshot_path": "unipass_screenshot.png",
        "raw_text": ""
    }
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage', '--disable-extensions']
            )
            
            # PC 와이드 해상도(1920x1080) 지정
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            
            # 1. 유니패스 메인 페이지로 이동
            page.goto("https://unipass.customs.go.kr/csp/index.do", timeout=30000, wait_until="domcontentloaded")
            
            # 2. 화물진행정보 영역의 'M B/L - H B/L' 라디오버튼 클릭
            try:
                page.click("label:has-text('M B/L - H B/L')", timeout=3000)
            except:
                try:
                    page.locator("input[value='MH']").click(force=True, timeout=3000)
                except:
                    pass
            
            page.wait_for_timeout(2000)

            # 3. M B/L 또는 H B/L 입력창에 번호 입력
            try:
                if bl_type == "M B/L":
                    page.locator("input[name*='mblNo'], input[id*='mblNo']").first.fill(bl_no)
                else:
                    page.locator("input[name*='hblNo'], input[id*='hblNo']").first.fill(bl_no)
            except Exception as input_err:
                if bl_type == "M B/L":
                    page.fill("input[name='mblNo']", bl_no)
                else:
                    page.fill("input[name='hblNo']", bl_no)
            
            # 4. 조회 버튼 클릭
            try:
                page.click("tr:has-text('M B/L') button, tr:has-text('B/L') button, #txtBlBtn, text='조회'", timeout=3000)
            except:
                page.keyboard.press("Enter")
            
            # 5. 검색 결과 페이지 로딩 대기
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
            
            # 6. M B/L인 경우 결과 목록에서 화물관리번호 링크 클릭하여 상세 페이지 진입
            if bl_type == "M B/L":
                try:
                    page.wait_for_selector("table tr td a", timeout=7000)
                    page.locator("table tr td a").first.click()
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                    page.wait_for_timeout(2000)
                except Exception as link_err:
                    print(f"화물관리번호 링크 클릭 중 예외 발생: {link_err}")
            
            # 7. 고화질 현재 화면 캡처 및 텍스트 추출
            page.screenshot(path=result["screenshot_path"])
            body_text = page.inner_text("body")
            result["raw_text"] = body_text

            if "조회된 내역이 없습니다" in body_text or "존재하지 않습니다" in body_text:
                result["error"] = "유니패스에서 해당 B/L 번호의 화물 진행 정보를 찾을 수 없습니다."
                browser.close()
                return result

            # 8. 상세 테이블 정보 파싱 (연락처 매칭용 데이터 수집)
            rows = page.locator("table tr").all()
            for row in rows:
                cells = [c.inner_text().strip() for c in row.locator("th, td").all()]
                for i, cell in enumerate(cells):
                    if "선사/항공사" in cell and i + 1 < len(cells):
                        if "확인 불가" in result["carrier"] or not result["carrier"]:
                            result["carrier"] = cells[i + 1]
                    elif "선박대리점" in cell and i + 1 < len(cells):
                        if "확인 불가" in result["agency"] or not result["agency"]:
                            result["agency"] = cells[i + 1]
                    elif ("터미널" in cell or "장치장" in cell) and i + 1 < len(cells):
                        val = cells[i + 1]
                        if val and "KG" not in val and "톤" not in val and len(val) < 30:
                            result["terminal"] = val
            
            found_containers = re.findall(r'[A-Z]{4}\d{7}', body_text)
            result["containers"] = list(set(found_containers))
                        
            browser.close()
            result["success"] = True
            
    except Exception as e:
        result["error"] = f"조회 중 오류가 발생했습니다: {e}"
        
    return result

# 메인 UI 화면 구성
st.title("🚢 포워딩 B/L & 양하조회 자동화 대시보드")
st.markdown("B/L 번호를 입력하면 유니패스를 자동 조회하여 선사/대리점/터미널 연락처와 컨테이너 번호를 보여줍니다.")

with st.sidebar:
    st.header("📋 등록된 선사/터미널 DB")
    
    uploaded_file = st.file_uploader("새로운 contacts.csv 파일 업로드", type=["csv"])
    if uploaded_file is not None:
        with open("contacts.csv", "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success("DB 파일이 성공적으로 업데이트되었습니다!")
        st.rerun()

    contacts_df = load_contacts()
    st.dataframe(contacts_df[["구분", "업체명", "전화번호"]], hide_index=True)
    st.info("💡 파일을 업로드하면 즉시 DB에 반영됩니다.")

col_type, col_input, col_btn = st.columns([1.2, 3, 1])
with col_type:
    bl_type = st.selectbox("B/L 구분", ["M B/L", "H B/L"])
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
            st.markdown("---")
            
            # 상단 거슬리던 메트릭 카드를 완전히 제거하고 바로 핵심 정보(연락처 및 컨테이너) 영역으로 연결합니다.
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
                with open(data["screenshot_path"], "rb") as file:
                    st.download_button(
                        label="📥 선명한 원본 캡처 이미지 다운로드 (.png)",
                        data=file,
                        file_name=f"UNIPASS_{bl_no}.png",
                        mime="image/png",
                        use_container_width=True
                    )
                st.image(data["screenshot_path"], use_container_width=True)
